#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自然语言指挥雷达小车 —— LLM 指挥官节点

用户输入中文指令 → DeepSeek function calling 解析意图 → Nav2 导航执行 → 中文汇报

用法：
    ros2 run llm_nav_robot llm_commander          # 完整模式（等待 Nav2 就绪）
    ros2 run llm_nav_robot llm_commander --no-nav # 纯 LLM 意图解析测试（不连导航）
"""

import json
import queue
import sys
import threading
import time

import requests
import rclpy
import rclpy.executors
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from rclpy.duration import Duration
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener
from tf_transformations import quaternion_from_euler

from llm_nav_robot.api_config import get_deepseek_api_key

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是 ROS2 自动导航小车的「自然语言指挥官」。用户会用中文下达导航指令，你的职责：
1. 理解用户意图，调用合适的工具（函数）执行导航
2. 地图坐标系为 map，单位米。已知常用地点：
   - 原点/起点: (0, 0)
   - 点A: (1.0, 2.0)
   - 点B: (-4.5, 1.5)
   - 点C: (-8.0, -5.0)
   - 点D: (1.0, -5.0)
3. 工具选择规则：
   - 「去某地/到某坐标」→ go_to_pose
   - 「依次/按顺序/巡检/巡逻/转一圈」→ follow_waypoints（给出路点列表）
   - 「你在哪/当前位置」→ get_robot_pose
   - 「停下/别动/取消/紧急」→ stop_robot
4. 用户给了明确坐标就直用；只给地点名就按上面列表推断；两者都没有则先 get_robot_pose 了解情况或请用户补充
5. 工具执行结果会以 JSON 返回给你，根据结果汇报

【回复铁律】
- 简洁精准：一句话陈述事实与结果，不寒暄、不解释过程、不用感叹号堆砌
- 禁止表情符号（emoji）
- 禁止拟人化：不说「伙伴」「开心」「好的呀」等拟人表达，保持机器式冷静
- 示例：「已到达 (1.0, 2.0)」「巡检完成：3/3 路点」「当前位置 (0.12, -0.01)」「导航失败：目的地不可达」

注意：yaw 单位是弧度（0~2π），用户没提朝向就默认 0。"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "go_to_pose",
            "description": "导航到地图上的指定坐标点，可选朝向",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "目标点 x 坐标（米）"},
                    "y": {"type": "number", "description": "目标点 y 坐标（米）"},
                    "yaw": {"type": "number", "description": "到达后朝向（弧度，默认 0）"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "follow_waypoints",
            "description": "依次导航经过多个路点（巡检/巡逻），按列表顺序逐个到达",
            "parameters": {
                "type": "object",
                "properties": {
                    "waypoints": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number", "description": "路点 x 坐标（米）"},
                                "y": {"type": "number", "description": "路点 y 坐标（米）"},
                                "yaw": {"type": "number", "description": "到达朝向（弧度，默认 0）"}
                            },
                            "required": ["x", "y"]
                        },
                        "description": "路点列表，至少 1 个，按顺序依次到达"
                    }
                },
                "required": ["waypoints"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_robot_pose",
            "description": "获取机器人当前在地图上的位置坐标",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_robot",
            "description": "立即停止/取消当前的导航任务",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


class LLMCommander(BasicNavigator):
    """LLM 指挥官：继承 BasicNavigator，融合 LLM 意图解析与 Nav2 导航"""

    def __init__(self, node_name='llm_commander', nav_available=True):
        super().__init__(node_name)
        self.api_key = get_deepseek_api_key()
        self.buffer_ = Buffer()
        self.listener_ = TransformListener(self.buffer_, self)
        self._nav_available = nav_available
        # 话题接口：订阅指令 /llm_cmd，发布回复 /llm_reply（供 GUI 使用）
        self.cmd_queue = queue.Queue()
        self.cmd_sub = self.create_subscription(String, 'llm_cmd', self.cmd_callback, 10)
        self.reply_pub = self.create_publisher(String, 'llm_reply', 10)
        # ⚠️ 注意：spin 线程不在此启动。waitUntilNav2Active 内部用 rclpy.spin_once
        # 在主线程 spin 本节点，若提前启动独立 executor 会与其冲突导致回调失效。
        # 正确时机：waitUntilNav2Active 完成后在 run() 中启动。
        if nav_available:
            self.get_logger().info('LLM 指挥官节点初始化完成（导航模式）')
        else:
            self.get_logger().info('LLM 指挥官节点初始化完成（纯 LLM 测试模式）')

    def cmd_callback(self, msg):
        """话题指令回调：入队，由主循环处理"""
        self.get_logger().info(f'收到话题指令: {msg.data}')
        self.cmd_queue.put(msg.data)

    def publish_reply(self, text):
        self.reply_pub.publish(String(data=text))
        self.get_logger().info(f'汇报: {text}')

    # ---------- LLM 对话 ----------
    def chat_once(self, messages, tools=None):
        headers = {'Authorization': f'Bearer {self.api_key}',
                   'Content-Type': 'application/json'}
        payload = {'model': MODEL, 'messages': messages, 'temperature': 0.2}
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']

    # ---------- 主交互循环 ----------
    def run(self, wait_nav=True):
        if wait_nav:
            self.get_logger().info('等待 Nav2 导航系统就绪...')
            self.waitUntilNav2Active()
            self.get_logger().info('导航就绪，LLM 指挥官上线。终端输入或发布话题 /llm_cmd（exit 退出）')
        else:
            self.get_logger().info('纯 LLM 模式（不连接导航），输入 exit 退出')

        threading.Thread(target=self.stdin_reader, daemon=True).start()

        # ⚠️ 不能使用独立 spin 线程：导航同步调用（goToPose 内部 spin_until_future_complete）
        # 会临时占用 node 导致自建 executor 的订阅回调失效。
        # 正确做法：主循环用 spin_once 处理订阅回调，导航同步调用由 rclpy 内部自行等待。
        while rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.5)
            try:
                cmd = self.cmd_queue.get_nowait()
            except queue.Empty:
                continue
            if cmd.lower() in ('exit', 'quit', '退出'):
                break
            self.handle_command(cmd)

    def stdin_reader(self):
        """后台线程读取终端输入；非交互终端（GUI 驱动）时直接跳过"""
        if not sys.stdin.isatty():
            return
        while rclpy.ok():
            try:
                cmd = input('你 > ').strip()
            except EOFError:
                time.sleep(0.5)
                continue
            except KeyboardInterrupt:
                break
            if cmd:
                self.cmd_queue.put(cmd)

    def handle_command(self, cmd):
        """处理单条指令：LLM 意图解析 → 工具执行 → 汇报"""
        messages = [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': cmd},
        ]
        try:
            reply = self.process_command(messages)
            print(f'小车 > {reply}')
            self.publish_reply(reply)
        except Exception as e:
            self.get_logger().error(f'执行出错: {e}')
            err_msg = f'执行出错：{e}'
            print(f'小车 > {err_msg}')
            self.publish_reply(err_msg)

    def process_command(self, messages, max_rounds=6):
        """多轮 function calling：直到 LLM 不再请求工具"""
        for _ in range(max_rounds):
            msg = self.chat_once(messages, tools=TOOLS)
            tool_calls = msg.get('tool_calls')
            if not tool_calls:
                return msg.get('content') or '任务已完成。'
            messages.append({'role': 'assistant',
                             'content': msg.get('content'),
                             'tool_calls': tool_calls})
            for tc in tool_calls:
                fn_name = tc['function']['name']
                try:
                    fn_args = json.loads(tc['function']['arguments'] or '{}')
                except json.JSONDecodeError:
                    fn_args = {}
                self.get_logger().info(f'→ 调用工具 {fn_name}: {fn_args}')
                if not self.is_nav_available():
                    result = {'success': False, 'message': '导航系统未就绪（纯 LLM 测试模式，工具已被正确识别）'}
                else:
                    result = self.execute_tool(fn_name, fn_args)
                messages.append({'role': 'tool',
                                 'tool_call_id': tc['id'],
                                 'content': json.dumps(result, ensure_ascii=False)})
        return '指令处理轮次过多，已停止（请确认指令是否清晰）。'

    def is_nav_available(self):
        return self._nav_available

    # ---------- 工具执行 ----------
    def execute_tool(self, name, args):
        if name == 'go_to_pose':
            return self.tool_go_to_pose(args)
        if name == 'follow_waypoints':
            return self.tool_follow_waypoints(args)
        if name == 'get_robot_pose':
            return self.tool_get_robot_pose()
        if name == 'stop_robot':
            return self.tool_stop_robot()
        return {'success': False, 'message': f'未知工具 {name}'}

    def make_pose(self, x, y, yaw=0.0):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(x)
        pose.pose.position.y = float(y)
        q = quaternion_from_euler(0.0, 0.0, float(yaw))
        pose.pose.orientation.x = q[0]
        pose.pose.orientation.y = q[1]
        pose.pose.orientation.z = q[2]
        pose.pose.orientation.w = q[3]
        return pose

    def wait_nav_result(self, timeout=600.0):
        """等待导航结果。兼容单点导航（estimated_time_remaining）与
        路点导航（current_waypoint）的不同反馈字段；超时用墙钟计算。"""
        start = time.time()
        while not self.isTaskComplete():
            feedback = self.getFeedback()
            if feedback is not None:
                if hasattr(feedback, 'estimated_time_remaining'):
                    try:
                        remaining = Duration.from_msg(feedback.estimated_time_remaining).nanoseconds / 1e9
                        self.get_logger().info(f'预计 {remaining:.0f} 秒后到达')
                    except Exception:
                        pass
                if hasattr(feedback, 'current_waypoint'):
                    self.get_logger().info(f'当前路点: {feedback.current_waypoint}')
            if time.time() - start > timeout:
                self.cancelTask()
                return {'success': False, 'message': '导航超时，已取消'}
            time.sleep(0.2)  # 避免忙等刷屏
        result = self.getResult()
        if result == TaskResult.SUCCEEDED:
            return {'success': True, 'message': '导航成功'}
        if result == TaskResult.CANCELED:
            return {'success': False, 'message': '导航被取消'}
        return {'success': False, 'message': '导航失败'}

    def tool_go_to_pose(self, args):
        pose = self.make_pose(args.get('x', 0.0), args.get('y', 0.0), args.get('yaw', 0.0))
        self.get_logger().info(f'目标: ({args.get("x")}, {args.get("y")})')
        self.goToPose(pose)
        return self.wait_nav_result()

    def tool_follow_waypoints(self, args):
        waypoints = args.get('waypoints', [])
        poses = [self.make_pose(w.get('x', 0.0), w.get('y', 0.0), w.get('yaw', 0.0))
                 for w in waypoints]
        if not poses:
            return {'success': False, 'message': '路点列表为空'}
        self.get_logger().info(f'依次巡检 {len(poses)} 个路点')
        self.followWaypoints(poses)
        return self.wait_nav_result()

    def tool_get_robot_pose(self):
        try:
            t = self.buffer_.lookup_transform('map', 'base_link', rclpy.time.Time())
            x = t.transform.translation.x
            y = t.transform.translation.y
            return {'success': True, 'position': {'x': round(x, 2), 'y': round(y, 2)}}
        except Exception as e:
            return {'success': False, 'message': f'获取位姿失败: {e}'}

    def tool_stop_robot(self):
        self.cancelTask()
        return {'success': True, 'message': '已停止导航'}


def main(argv=None):
    rclpy.init(args=argv)
    wait_nav = '--no-nav' not in sys.argv
    node = LLMCommander(nav_available=wait_nav)
    try:
        node.run(wait_nav=wait_nav)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

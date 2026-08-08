# NL2NAV — 自然语言指挥雷达小车

> 用中文自然语言（文字 / 语音）指挥 ROS2 仿真小车自主导航
> 2026-08-08 创建 · 幽暗香 × 弗洛洛

---

## 📖 项目简介

基于 **ROS2 Humble + Navigation2 + Gazebo** 的仿真小车项目，核心是让用户**说人话就能指挥小车**：

```
「去 (1.0, 2.0)」      → 小车自动导航过去
「(3,3)->(3,-2)->(-5,-1)」 → 依次巡检三个路点
「你现在在哪里」      → 小车汇报实时位置
「停一下」            → 小车立即停止
```

小车由 **DeepSeek LLM（function calling）** 解析自然语言意图，映射为 Nav2 导航指令执行，并用**简洁精准**的语言汇报结果（无 emoji、无拟人化）。

---

## 🏗️ 系统架构

```
┌────────────┐    /llm_cmd     ┌───────────────────────────────┐
│ GUI 聊天窗口 │ ────────────→ │ llm_commander（ROS2 节点）      │
│ tkinter     │                │  ① DeepSeek function calling   │
│ 文字+语音输入│ ←──────────── │  ② 意图 → go_to_pose /         │
└────────────┘    /llm_reply   │     follow_waypoints / 等工具   │
                               │  ③ 调用 Nav2 执行导航           │
                               └───────────────┬───────────────┘
                                               │ Nav2 action
                                       ┌───────▼───────┐
                                       │ Gazebo 仿真小车 │
                                       │ (yax 模型)     │
                                       └───────────────┘
```

**通信**：话题 `llm_cmd`（指令）/ `llm_reply`（回复），标准 `std_msgs/String`

---

## ✨ 功能清单

| 功能 | 指令示例 | 实现 |
|---|---|---|
| 单点导航 | 去 (1.0, 2.0) / 去点A | `go_to_pose(x, y, yaw)` |
| 路点巡检 | (3,3)->(3,-2)->(-5,-1) | `follow_waypoints([...])` |
| 位置查询 | 你现在在哪里 | `get_robot_pose`（TF 查询） |
| 紧急停止 | 停一下 / 停下 | `stop_robot`（cancelTask） |
| 语音输入 | 单击「语音输入」→ 说话 → 再击「点击停止录音」 | sounddevice 录音 + vosk 离线中文识别 |
| 聊天记录 | 窗口内显示你与小车的完整对话 | tkinter ScrolledText |

**小车语言风格**：简洁、精准、只报事实——「已到达 (2.0, 2.0)」「巡检完成：3/3 路点」「当前位置 (0.88, 1.88)」。

---

## 📁 目录结构

```
/home/yax/NL2NAV/
├── start_gui.sh                 # 一键启动聊天窗口（含输入法环境）
├── models/                      # vosk 中文语音模型
│   └── vosk-model-small-cn-0.22/
└── nl2nav_ws/                   # ROS2 工作空间
    └── src/llm_nav_robot/
        ├── llm_nav_robot/
        │   ├── llm_commander.py # 主节点：LLM 意图解析 + Nav2 执行
        │   ├── llm_gui.py       # 聊天窗口（文字 + 语音输入）
        │   └── api_config.py    # DeepSeek Key（读 ~/桌面/API合集.md）
        └── launch/
            └── llm_nav.launch.py
```

---

## 🔧 依赖环境

| 依赖 | 说明 |
|---|---|
| Ubuntu 22.04 + ROS2 Humble | 基础环境 |
| Navigation2 / Gazebo | 导航与仿真（chapt7 已装） |
| yax 系列功能包 | 小车模型/导航配置，来自 `/home/yax/chapt7/chapt7_ws`（fishbot 更名版） |
| DeepSeek API | 意图解析，Key 存于 `~/桌面/API合集.md`（不硬编码） |
| Python: requests / sounddevice / vosk | LLM 调用 / 录音 / 离线识别 |
| tkinter | 系统自带 GUI 库 |

---

## 🚀 启动步骤

```bash
# 1️⃣ 启动仿真（Gazebo + 小车 + ros2_control）
cd /home/yax/chapt7/chapt7_ws && source install/setup.bash
ros2 launch yax_description gazebo_sim.launch.py

# 2️⃣ 启动导航（Nav2 + 地图 + RViz）——等 Gazebo 就绪后
ros2 launch yax_navigation2 navigarion2.launch.py

# 3️⃣ 启动 LLM 指挥官（等 Nav2 全部 active）
cd /home/yax/NL2NAV/nl2nav_ws && source install/setup.bash
ros2 run llm_nav_robot llm_commander

# 4️⃣ 打开聊天窗口（桌面）
bash ~/NL2NAV/start_gui.sh
```

**调试模式**：`ros2 run llm_nav_robot llm_commander --no-nav`（纯 LLM 意图解析测试，不连导航）

**地图已知地点**：原点 (0,0) · 点A (1.0,2.0) · 点B (-4.5,1.5) · 点C (-8.0,-5.0) · 点D (1.0,-5.0)

---

## ✅ 实测记录（2026-08-08）

| 指令 | 小车回复 |
|---|---|
| 去 (1.0, 2.0) | 已到达 (1.0, 2.0)。 |
| 去 2,2 | 已到达 (2.0, 2.0) |
| 你现在在哪里 | 当前位置 (0.88, 1.88) |
| (3,3)->(3,-2)->(-5,-1) | 巡检完成：3/3 路点，依次到达 (3,3)、(3,-2)、(-5,-1)。 |
| 停一下 | 已停止导航。 |

---

## ⚠️ 踩坑记录（血泪教训）

1. **rclpy spin 线程 vs Tk mainloop**：BasicNavigator 无内部 spin，但自建独立 spin 线程会与 Tk 布局冲突——pack 布局失效（bottom 塌陷 1x1 不可见）。**解法**：GUI 主线程用 `after(100ms)` 轮询 `rclpy.spin_once`，commander 主循环同样 spin_once。
2. **固定窗口尺寸 geometry + rclpy 轮询** → 同样触发布局崩溃。**解法**：窗口只设位置 `+x+y`，不设固定尺寸（自动大小）。
3. **waitUntilNav2Active 内部用 `rclpy.spin_once` 主线程 spin**：自建 executor 必须在它完成后才启动，否则订阅回调永久失效。
4. **tkinter 中文输入**：Tk 走 XIM，必须设置 `XMODIFIERS=@im=fcitx`（+ GTK/QT_IM_MODULE），否则只能打英文（粘贴中文正常）。见 `start_gui.sh`。
5. **FollowWaypoints_Feedback 无 `estimated_time_remaining`**（单点导航专用字段），需 `hasattr` 分支兼容，超时用墙钟。
6. **pkill -f 自杀坑**：`pkill -f "ros2 run xx"` 会匹配自身命令行，用 `[x]` 正则技巧或精确 PID。
7. **Wayland rootless 截图**：`mss`/`xwd -root` 截根窗口为黑屏，`xwd -id <窗口ID>` + ImageMagick 可用。
8. **Nav2 心跳丢失**：虚拟机负载高时 lifecycle_manager 可能判定节点 DOWN 自我关闭，重启 Nav2 launch 即可（Gazebo 侧通常无恙）。

---

## 🔗 关联

- 小车本体与导航配置：`/home/yax/chapt7/chapt7_ws`（yax_description / yax_navigation2 / yax_application）
- 学习项目文档：`~/桌面/ROS2雷达小车项目.md`、`~/桌面/ROS2项目日志.md`

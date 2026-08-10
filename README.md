# 🚗 ChatNav — 自然语言指挥雷达小车

> 说人话，车就走。用中文自然语言（文字 / 语音）指挥 ROS2 仿真小车自主导航。

`ROS2 Humble` · `Navigation2` · `Gazebo` · `DeepSeek LLM` · `Vosk 语音识别`

---

## ✨ 功能特性

- **自然语言导航**：DeepSeek function calling 解析中文指令，自动映射为 Nav2 导航动作
- **语音指挥**：一键录音 + vosk 中文离线识别，说句话就能开车（无需联网）
- **多目标巡检**：支持单点导航与多路点依次巡检
- **实时位置查询**：随时询问小车当前位置（TF 坐标变换）
- **紧急停止**：随时喊停，立即取消当前导航任务
- **简洁汇报**：小车只报事实——「已到达 (2.0, 2.0)」「巡检完成：3/3 路点」

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
                                       │ (chatnav 模型) │
                                       └───────────────┘
```

**通信**：话题 `llm_cmd`（指令）/ `llm_reply`（回复），标准 `std_msgs/String`

---

## 🚀 快速开始

### 环境要求

| 依赖 | 说明 |
|---|---|
| Ubuntu 22.04 + ROS2 Humble | 基础环境 |
| Navigation2 / Gazebo | 导航与仿真 |
| Python: requests / sounddevice / vosk / tkinter | LLM 调用 / 录音 / 离线识别 / GUI |
| DeepSeek API Key | 意图解析（见下方「配置 API Key」） |

### 配置 API Key

ChatNav 使用 DeepSeek API 解析自然语言指令，使用前需配置你的 Key（二选一）：

**方式一：环境变量（推荐）**

```bash
export DEEPSEEK_API_KEY=sk-你的key
```

**方式二：本地文件**

在用户目录创建配置文件（推荐位置，跨安装/源码模式均稳定）：

```bash
mkdir -p ~/.chatnav
echo "sk-你的key" > ~/.chatnav/api_key.txt
```

也可以在与 `api_config.py` 同目录下创建 `api_key.txt`（仅源码运行模式）：

```
sk-你的key
```

> ⚠️ 以上文件均不会被 git 跟踪；请勿将 Key 写入任何将被提交的文件。

### 一键启动

```bash
# 1️⃣ 构建工作空间
cd chatnav_ws && source /opt/ros/humble/setup.bash
colcon build && source install/setup.bash

# 2️⃣ 启动全部：Gazebo 小车 + Nav2 导航 + LLM 指挥官
bash ~/ChatNav/start_chatnav.sh

# 3️⃣ 打开聊天窗口（另开终端）
bash ~/ChatNav/start_gui.sh
```

### 手动分步启动（调试用）

```bash
# ① 启动仿真（Gazebo + 小车 + ros2_control）
ros2 launch chatnav_description gazebo_sim.launch.py

# ② 启动导航（Nav2 + 地图 + RViz）——等 Gazebo 就绪后
ros2 launch chatnav_navigation2 navigarion2.launch.py

# ③ 启动 LLM 指挥官（等 Nav2 全部 active）
ros2 run llm_nav_robot llm_commander

# ④ 打开聊天窗口
bash ~/ChatNav/start_gui.sh
```

**调试模式**：`ros2 run llm_nav_robot llm_commander --no-nav`（纯 LLM 意图解析测试，不连导航）

---

## 📖 使用示例

地图已知地点：原点 (0,0) · 点A (1.0,2.0) · 点B (-4.5,1.5) · 点C (-8.0,-5.0) · 点D (1.0,-5.0)

| 指令 | 小车回复 |
|---|---|
| 去 (1.0, 2.0) | 已到达 (1.0, 2.0)。 |
| 去 2,2 | 已到达 (2.0, 2.0) |
| 你现在在哪里 | 当前位置 (0.88, 1.88) |
| (3,3)->(3,-2)->(-5,-1) | 巡检完成：3/3 路点，依次到达 (3,3)、(3,-2)、(-5,-1)。 |
| 停一下 | 已停止导航。 |
| （语音）去点A | 已到达 (1.0, 2.0)。 |

---

## 📁 项目结构

```
ChatNav/
├── start_chatnav.sh              # 一键启动：Gazebo + Nav2 + LLM 指挥官
├── start_gui.sh                  # 启动聊天窗口（含输入法环境）
├── models/                       # vosk 中文语音模型
│   └── vosk-model-small-cn-0.22/
└── chatnav_ws/                   # ROS2 工作空间
    └── src/
        ├── chatnav_description/  # 小车本体：URDF/Xacro 模型 + Gazebo 仿真 + ros2_control
        ├── chatnav_navigation2/  # 导航配置：Nav2 参数 + SLAM 地图
        └── llm_nav_robot/        # LLM 指挥官：意图解析 + 导航执行 + 聊天窗口
```

### 功能包说明

| 功能包 | 职责 |
|---|---|
| `chatnav_description` | 小车 URDF/Xacro 模型（底盘/激光雷达/相机/IMU）、Gazebo 仿真、ros2_control 双轮差速控制 |
| `chatnav_navigation2` | Nav2 参数配置、SLAM 地图（room.yaml）、导航 launch |
| `llm_nav_robot` | `llm_commander`（DeepSeek 意图解析 → Nav2 执行）、`llm_gui`（tkinter 聊天窗口 + 语音输入） |

---

## 🔗 参考文档

- **ROS2 官方文档（Humble）**：https://docs.ros.org/en/humble/
- **Navigation2 文档**：https://docs.nav2.org/
- **Navigation2 源码**：https://github.com/ros-navigation/navigation2
- **Gazebo 仿真**：https://gazebosim.org/
- **pluginlib（插件机制）**：https://docs.ros.org/en/humble/p/pluginlib/
- **tf2（坐标变换）**：https://docs.ros.org/en/humble/Concepts/About-Tf2.html
- **DeepSeek API**：https://platform.deepseek.com/
- **Vosk 离线语音识别**：https://alphacephei.com/vosk/

---

## 📄 许可证

[Apache License 2.0](LICENSE)

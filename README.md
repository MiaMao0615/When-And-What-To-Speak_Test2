# 聊天Agent实验平台 (test2)

双系统聊天实验平台，支持LoRA和ChatGPT两种后端实现，用于多人对话场景下的AI Agent意愿预测与插话生成实验。

## 🎯 项目简介

本项目是一个完整的**多人聊天实验平台**，包含两个独立的实验系统，支持双盲测试、实验数据收集和问卷功能。系统能够实时预测AI Agent的对话意愿（Willingness），当意愿值超过阈值时自动生成插话内容。

### 核心特性

- ✅ **双系统架构**：LoRA本地模型系统 + ChatGPT API系统
- ✅ **多人聊天室**：支持多客户端同时加入同一房间
- ✅ **双盲测试**：用户和Agent使用随机编号（1-100），隐藏真实身份
- ✅ **实时意愿预测**：基于Persona/Scene/Topic三个维度的意愿值计算
- ✅ **智能插话生成**：当意愿值超过阈值时自动生成插话
- ✅ **实验数据自动记录**：所有对话和推理结果保存到CSV文件
- ✅ **问卷功能**：实验结束后用户评分其他参与者是Agent的可能性
- ✅ **实验统计**：自动生成实验统计结果和数据分析

## 📁 项目结构

```
test2/
├── backend/                          # 后端代码
│   ├── Websocket.py                  # LoRA系统WebSocket服务器
│   ├── WebsocketChatgpty.py          # ChatGPT系统WebSocket服务器
│   ├── Core.py                       # LoRA推理核心
│   └── CoreChatgpt.py                # ChatGPT推理核心
│
├── my-chat-app2/                     # LoRA系统前端
│   ├── src/                          # React源代码
│   │   ├── App.jsx                   # 主应用组件
│   │   ├── ChatRoom.css              # 聊天室样式
│   │   └── main.jsx                  # 入口文件
│   ├── package.json                  # 依赖配置
│   ├── vite.config.js                # Vite配置
│   ├── 启动后端.bat                  # 快速启动后端
│   ├── 构建前端.bat                  # 快速构建前端
│   ├── 启动前端服务.bat              # 快速启动前端服务
│   ├── 完整启动指南.md               # 详细启动说明
│   ├── 问卷功能说明.md               # 问卷功能文档
│   └── TEST_GUIDE.md                 # 测试指南
│
├── my-chat-app2ChatgptTest/          # ChatGPT系统前端
│   ├── src/                          # React源代码
│   ├── package.json                  # 依赖配置
│   └── 启动指南.md                   # 启动说明
│
└── experiment_logs/                  # 实验日志目录（自动生成）
    ├── lora_experiment_*.csv         # LoRA系统实验数据
    └── chatgpt_experiment_*.csv      # ChatGPT系统实验数据
```

## 🚀 快速开始

### 前置要求

#### LoRA系统要求
- **Python 3.8+**
- **CUDA支持的GPU**（推荐16GB+显存，也可使用CPU）
- **PyTorch** 和 **CUDA工具包**
- **Node.js 16+** 和 **npm**

#### ChatGPT系统要求
- **Python 3.8+**
- **Node.js 16+** 和 **npm**
- **OpenAI API Key**（需要配置环境变量）

### 安装依赖

#### 后端依赖（Python）

```bash
pip install torch transformers peft websockets openai
```

#### 前端依赖（Node.js）

**LoRA系统前端：**
```bash
cd my-chat-app2
npm install
```

**ChatGPT系统前端：**
```bash
cd my-chat-app2ChatgptTest
npm install
```

### 配置模型路径（LoRA系统）

编辑 `backend/Core.py`，修改以下路径：

```python
BASE_MODEL = r"D:\LLM\Qwen2.5-7B-Instruct"

PERSONA_LORA = r"D:\Task_design\personality\FinTune\outputs\qwen7b-lora-persona-will_full\checkpoint-32899"
SCENE_LORA   = r"D:\Task_design\Scene\outputs\qwen7b-lora-will_half_fp16_v2\checkpoint-35821"
TOPIC_LORA   = r"D:\Task_design\Topic\willingness_train\outputs\qwen7b-lora-topic_willingness\checkpoint-2500"
```

### 配置OpenAI API（ChatGPT系统）

设置环境变量：

```bash
# Windows
set OPENAI_API_KEY=your_api_key_here

# Linux/Mac
export OPENAI_API_KEY=your_api_key_here
```

或在代码中直接配置：

```python
# backend/CoreChatgpt.py
client = OpenAI(api_key="your_api_key")
```

## 📖 详细使用指南

### LoRA系统启动流程

#### 方法1：使用批处理文件（推荐）

1. **构建前端**
   ```bash
   cd my-chat-app2
   # 双击运行：构建前端.bat
   # 或手动运行：npm run build
   ```

2. **启动后端**
   ```bash
   # 双击运行：启动后端.bat
   # 或手动运行：python backend/Websocket.py
   ```

3. **启动前端服务**
   ```bash
   # 双击运行：启动前端服务.bat
   # 或手动运行：npx serve dist -l 5173 --cors
   ```

4. **访问应用**
   - 浏览器打开：`http://localhost:5173`
   - 或使用网络IP（多设备访问）：`http://192.168.x.x:5173`

#### 方法2：手动命令行启动

```bash
# 终端1：启动后端
cd test2
python backend/Websocket.py

# 终端2：构建并启动前端
cd my-chat-app2
npm run build
npx serve dist -l 5173 --cors
```

详细步骤请参考 `my-chat-app2/完整启动指南.md`

### ChatGPT系统启动流程

1. **构建前端**
   ```bash
   cd my-chat-app2ChatgptTest
   npm run build
   ```

2. **启动后端**
   ```bash
   cd test2
   python backend/WebsocketChatgpty.py
   ```

3. **启动前端服务**
   ```bash
   cd my-chat-app2ChatgptTest
   npx serve dist -l 5174 --cors
   ```

4. **访问应用**
   - 浏览器打开：`http://localhost:5174`

## 🔧 系统功能说明

### 1. 用户加入流程

1. **填写个人信息**
   - 昵称（Nickname）
   - 简介（Introduction）
   - 人格特征（Persona Profile）

2. **加入聊天室**
   - 系统随机分配编号（1-100）
   - 显示：`您的编号：#42`
   - 所有用户和Agent都使用编号标识

3. **开始对话**
   - 用户发送消息，系统实时计算意愿值
   - 当 `final_willingness > threshold` 时，Agent自动插话

### 2. 意愿预测机制

系统使用三个LoRA模型分别计算意愿值：

- **Persona Willingness**: 基于用户人格特征
- **Scene Willingness**: 基于对话场景
- **Topic Willingness**: 基于对话话题

最终意愿值计算公式：
```
final_willingness = (w_p * p_val + w_s * s_val + w_t * t_val) / (w_p + w_s + w_t)
```

### 3. 插话生成策略

当 `final_willingness > 0.60`（LoRA系统）或超过ChatGPT判断阈值时：

- **LoRA系统**：调用ChatGPT生成插话（不加载Strategy分类模型）
- **ChatGPT系统**：直接使用ChatGPT判断并生成插话

插话要求：
- 简短自然，不超过80 tokens
- 不重复用户原话
- 不包含疑问句
- 符合对话场景

### 4. 实验数据记录

系统自动将所有数据记录到CSV文件：

**LoRA系统CSV格式：**
```csv
房间ID,时间戳,序号,发言者类型,编号,用户ID,说话内容,
最终Willingness,Persona分数,Scene分数,Topic分数,
是否触发插话,Agent策略,Agent插话内容,Agent编号
```

**ChatGPT系统CSV格式：**
```csv
房间ID,时间戳,序号,发言者类型,编号,用户ID,说话内容,
Agent判断分数,是否触发插话,Agent策略,Agent插话内容,Agent编号
```

### 5. 问卷功能

实验结束后自动进入问卷阶段：

1. **问卷触发**：主持人点击"结束实验"按钮
2. **评分界面**：用户对其他所有参与者评分（1-10分）
   - 1分 = 非常确定不是Agent
   - 10分 = 非常确定是Agent
3. **问卷进度**：显示完成进度（已完成人数/总人数）
4. **统计结果**：所有用户完成后显示实验统计

### 6. 多设备访问

支持同一WiFi网络下的多设备同时访问：

1. **获取服务器IP**
   ```bash
   ipconfig  # Windows
   ifconfig  # Linux/Mac
   ```

2. **在其他设备访问**
   - 确保设备连接到同一WiFi
   - 浏览器访问：`http://192.168.x.x:5173`（LoRA系统）
   - 或：`http://192.168.x.x:5174`（ChatGPT系统）

## ⚙️ 配置参数

### LoRA系统配置 (`backend/Core.py`)

```python
MAX_LENGTH = 256              # 文本最大长度
THRESHOLD = 0.60              # 意愿值阈值（超过此值触发插话）
HISTORY_N = 12                # 上下文历史句子数
GPU_QUEUE_MAX = 300           # 推理队列上限
```

### WebSocket配置 (`backend/Websocket.py`)

```python
WS_LOG = True                 # 服务端日志开关
HISTORY_N = 12                # 最近N句作为上下文
MAX_HISTORY = 100             # 历史最多保留
```

### ChatGPT系统配置 (`backend/CoreChatgpt.py`)

```python
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"  # 使用的模型
TEMPERATURE = 0.7             # 生成温度
MAX_TOKENS = 80               # 最大token数
```

## 📊 WebSocket协议

### 客户端 → 服务器

#### 1. 加入房间 (join)
```json
{
  "type": "join",
  "nickname": "张三",
  "intro": "我是一个喜欢帮助别人的人",
  "persona_profile": {
    "background": "...",
    "personality_traits": ["empathetic", "supportive"],
    "speaking_style": "gentle",
    "values": "honesty"
  },
  "user_number": 42
}
```

#### 2. 发送消息 (chat_line)
```json
{
  "type": "chat_line",
  "text": "大家好！"
}
```

#### 3. 设置场景 (scene_fields)
```json
{
  "type": "scene_fields",
  "fields": {
    "time_of_day": "深夜",
    "formality": "非正式",
    "domain": "情感交流",
    "relationship": "朋友",
    "topic_sensitivity": "中等",
    "participants": "3-5人",
    "ai_preference": "支持型",
    "platform": "卧室"
  }
}
```

#### 4. 设置话题 (topic)
```json
{
  "type": "topic",
  "topic": "work_stress"
}
```

#### 5. 提交问卷 (questionnaire_answer)
```json
{
  "type": "questionnaire_answer",
  "answers": {
    "17": 8.0,
    "58": 9.0,
    "33": 3.0
  }
}
```

### 服务器 → 客户端

#### 1. 聊天确认 (chat_ack)
```json
{
  "type": "chat_ack",
  "seq": 1,
  "status": "queued"
}
```

#### 2. 消息更新 (chat_update)
```json
{
  "type": "chat_update",
  "seq": 1,
  "status": "done",
  "text": "大家好！",
  "user_id": "u_abc123",
  "nickname": "张三",
  "display_number": 42,
  "final_willingness": 0.72,
  "triggered": true,
  "agent_text": "很高兴认识大家！",
  "agent_strategy": "comforting",
  "agent_number": 58
}
```

#### 3. 实验统计 (experiment_stats)
```json
{
  "type": "experiment_stats",
  "room_id": "room_20240117_220000",
  "csv_path": "D:\\Task_design\\experiment_logs\\lora_experiment_*.csv",
  "total_messages": 150,
  "agent_responses": 23,
  "participants": [
    {"number": 42, "messages": 25},
    {"number": 17, "messages": 30}
  ]
}
```

## 🐛 故障排除

### 问题1：模型加载失败

**症状**：后端启动时报错，无法加载LoRA模型

**解决方案**：
- 检查模型路径是否正确
- 确认LoRA检查点文件完整
- 验证CUDA/PyTorch版本兼容性
- 检查GPU显存是否足够

### 问题2：WebSocket连接失败

**症状**：前端显示"连接失败"或无法接收消息

**解决方案**：
- 确认后端服务器正在运行
- 检查防火墙设置（端口8765需要开放）
- 确认前端访问地址正确
- 查看浏览器控制台（F12）错误信息

### 问题3：OpenAI API调用失败

**症状**：ChatGPT系统无法生成插话

**解决方案**：
- 检查环境变量 `OPENAI_API_KEY` 是否设置
- 验证API密钥有效性
- 确认网络连接正常
- 检查API额度是否充足

### 问题4：多设备无法访问

**症状**：其他设备无法打开前端页面

**解决方案**：
- 确认所有设备在同一WiFi网络
- 检查防火墙是否阻止端口5173/5174
- 验证服务器IP地址是否正确
- 尝试使用 `0.0.0.0` 而不是 `localhost` 启动服务

### 问题5：问卷功能异常

**症状**：问卷无法提交或进度不更新

**解决方案**：
- 确认所有用户已完成"加入房间"步骤
- 检查后端日志查看问卷状态
- 确认用户编号正确记录
- 刷新页面重新加入

## 📝 开发说明

### 代码架构

**后端架构：**
- `Websocket.py` / `WebsocketChatgpty.py`：WebSocket服务器，处理连接和消息路由
- `Core.py` / `CoreChatgpt.py`：推理核心，执行意愿预测和插话生成

**前端架构：**
- React + Vite构建
- WebSocket客户端实时通信
- 状态管理：聊天历史、用户信息、实验状态

### 扩展建议

- 支持更多策略类型
- 添加历史对话上下文管理
- 实现多轮对话意图识别
- 添加性能监控和统计图表
- 支持实验配置导出/导入

## 📄 相关文档

- `my-chat-app2/完整启动指南.md` - LoRA系统详细启动说明
- `my-chat-app2/问卷功能说明.md` - 问卷功能详细文档
- `my-chat-app2/TEST_GUIDE.md` - 多窗口测试指南
- `my-chat-app2ChatgptTest/启动指南.md` - ChatGPT系统启动说明

## 📄 许可证

（待添加）

## 👥 贡献者

（待添加）

## 📞 联系方式

如有问题或建议，请提交Issue或联系项目维护者。

---

**注意**：本项目用于学术研究目的，请确保遵守相关伦理规范和隐私保护要求。
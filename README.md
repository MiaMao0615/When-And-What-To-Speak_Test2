# Chat Agent Experiment Platform (test2)

A dual-system chat experiment platform supporting LoRA and ChatGPT backend implementations for multi-user dialogue scenarios with AI Agent willingness prediction and insertion generation experiments.

## 🎯 Project Overview

This project is a complete **multi-user chat experiment platform** with two independent experimental systems, supporting double-blind testing, experimental data collection, and questionnaire functionality. The system can predict AI Agent dialogue willingness (Willingness) in real-time and automatically generate insertions when willingness exceeds the threshold.

### Core Features

- ✅ **Dual System Architecture**: LoRA local model system + ChatGPT API system
- ✅ **Multi-user Chat Room**: Supports multiple clients joining the same room simultaneously
- ✅ **Double-blind Testing**: Users and Agents use random numbers (1-100) to hide real identities
- ✅ **Real-time Willingness Prediction**: Calculates willingness values based on Persona/Scene/Topic dimensions
- ✅ **Intelligent Insertion Generation**: Automatically generates insertions when willingness exceeds threshold
- ✅ **Automatic Experimental Data Recording**: All conversations and inference results saved to CSV files
- ✅ **Questionnaire Function**: After experiments, users rate the likelihood of other participants being Agents
- ✅ **Experiment Statistics**: Automatically generates experiment statistics and data analysis

## 📁 Project Structure

```
test2/
├── backend/                          # Backend code
│   ├── Websocket.py                  # LoRA system WebSocket server
│   ├── WebsocketChatgpty.py          # ChatGPT system WebSocket server
│   ├── Core.py                       # LoRA inference core
│   └── CoreChatgpt.py                # ChatGPT inference core
│
├── my-chat-app2/                     # LoRA system frontend
│   ├── src/                          # React source code
│   │   ├── App.jsx                   # Main application component
│   │   ├── ChatRoom.css              # Chat room styles
│   │   └── main.jsx                  # Entry file
│   ├── package.json                  # Dependencies configuration
│   ├── vite.config.js                # Vite configuration
│   ├── 启动后端.bat                  # Quick start backend (batch file)
│   ├── 构建前端.bat                  # Quick build frontend (batch file)
│   ├── 启动前端服务.bat              # Quick start frontend service (batch file)
│   ├── 完整启动指南.md               # Detailed startup guide
│   ├── 问卷功能说明.md               # Questionnaire documentation
│   └── TEST_GUIDE.md                 # Test guide
│
├── my-chat-app2ChatgptTest/          # ChatGPT system frontend
│   ├── src/                          # React source code
│   ├── package.json                  # Dependencies configuration
│   └── 启动指南.md                   # Startup guide
│
└── experiment_logs/                  # Experiment logs directory (auto-generated)
    ├── lora_experiment_*.csv         # LoRA system experiment data
    └── chatgpt_experiment_*.csv      # ChatGPT system experiment data
```

## 🚀 Quick Start

### Prerequisites

#### LoRA System Requirements
- **Python 3.8+**
- **CUDA-enabled GPU** (16GB+ VRAM recommended, CPU also supported)
- **PyTorch** and **CUDA toolkit**
- **Node.js 16+** and **npm**

#### ChatGPT System Requirements
- **Python 3.8+**
- **Node.js 16+** and **npm**
- **OpenAI API Key** (needs to be configured as environment variable)

### Installation

#### Backend Dependencies (Python)

```bash
pip install torch transformers peft websockets openai
```

#### Frontend Dependencies (Node.js)

**LoRA System Frontend:**
```bash
cd my-chat-app2
npm install
```

**ChatGPT System Frontend:**
```bash
cd my-chat-app2ChatgptTest
npm install
```

### Configure Model Paths (LoRA System)

Models have been uploaded to Hugging Face and can be used directly:

**Hugging Face Model Repository:** [MiaMao/Autonomous-Insert-LoRA](https://huggingface.co/MiaMao/Autonomous-Insert-LoRA)

**Related Resources:**
- **Training Dataset:** [MiaMao/Autonomous-Insert-Data](https://huggingface.co/datasets/MiaMao/Autonomous-Insert-Data)
- **Full Runtime Code:** [Autonomous-Insert-Agent](https://github.com/MiaMao0615/Autonomous-Insert-Agent)

Edit `backend/Core.py` to use Hugging Face model paths:

```python
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"  # Or use local path

# Load LoRA adapters from Hugging Face
PERSONA_LORA = "MiaMao/Autonomous-Insert-LoRA"  # Or use local path
SCENE_LORA   = "MiaMao/Autonomous-Insert-LoRA"  # Or use local path
TOPIC_LORA   = "MiaMao/Autonomous-Insert-LoRA"  # Or use local path
```

**Note:** If using local paths, ensure model files are downloaded locally.

### Configure OpenAI API (ChatGPT System)

Set environment variables:

```bash
# Windows
set OPENAI_API_KEY=your_api_key_here

# Linux/Mac
export OPENAI_API_KEY=your_api_key_here
```

Or configure directly in code:

```python
# backend/CoreChatgpt.py
client = OpenAI(api_key="your_api_key")
```

## 📖 Detailed Usage Guide

### LoRA System Startup Process

#### Method 1: Using Batch Files (Recommended)

1. **Build Frontend**
   ```bash
   cd my-chat-app2
   # Double-click: 构建前端.bat
   # Or manually run: npm run build
   ```

2. **Start Backend**
   ```bash
   # Double-click: 启动后端.bat
   # Or manually run: python backend/Websocket.py
   ```

3. **Start Frontend Service**
   ```bash
   # Double-click: 启动前端服务.bat
   # Or manually run: npx serve dist -l 5173 --cors
   ```

4. **Access Application**
   - Open browser: `http://localhost:5173`
   - Or use network IP (for multi-device access): `http://192.168.x.x:5173`

#### Method 2: Manual Command Line Startup

```bash
# Terminal 1: Start backend
cd test2
python backend/Websocket.py

# Terminal 2: Build and start frontend
cd my-chat-app2
npm run build
npx serve dist -l 5173 --cors
```

For detailed steps, refer to `my-chat-app2/完整启动指南.md`

### ChatGPT System Startup Process

1. **Build Frontend**
   ```bash
   cd my-chat-app2ChatgptTest
   npm run build
   ```

2. **Start Backend**
   ```bash
   cd test2
   python backend/WebsocketChatgpty.py
   ```

3. **Start Frontend Service**
   ```bash
   cd my-chat-app2ChatgptTest
   npx serve dist -l 5174 --cors
   ```

4. **Access Application**
   - Open browser: `http://localhost:5174`

## 🔧 System Features

### 1. User Join Process

1. **Fill Personal Information**
   - Nickname
   - Introduction
   - Persona Profile

2. **Join Chat Room**
   - System randomly assigns a number (1-100)
   - Display: `Your Number: #42`
   - All users and Agents are identified by numbers

3. **Start Conversation**
   - Users send messages, system calculates willingness values in real-time
   - When `final_willingness > threshold`, Agent automatically inserts

### 2. Willingness Prediction Mechanism

The system uses three LoRA models to calculate willingness values separately:

- **Persona Willingness**: Based on user personality traits
- **Scene Willingness**: Based on dialogue scenario
- **Topic Willingness**: Based on dialogue topic

Final willingness calculation formula:
```
final_willingness = (w_p * p_val + w_s * s_val + w_t * t_val) / (w_p + w_s + w_t)
```

### 3. Insertion Generation Strategy

When `final_willingness > 0.60` (LoRA system) or exceeds ChatGPT judgment threshold:

- **LoRA System**: Calls ChatGPT to generate insertion (does not load Strategy classification model)
- **ChatGPT System**: Directly uses ChatGPT to judge and generate insertion

Insertion requirements:
- Short and natural, no more than 80 tokens
- Does not repeat user's original words
- Does not contain interrogative sentences
- Fits dialogue scenario

### 4. Experimental Data Recording

System automatically records all data to CSV files:

**LoRA System CSV Format:**
```csv
Room ID,Timestamp,Sequence,Speaker Type,Number,User ID,Content,
Final Willingness,Persona Score,Scene Score,Topic Score,
Triggered,Agent Strategy,Agent Insertion,Agent Number
```

**ChatGPT System CSV Format:**
```csv
Room ID,Timestamp,Sequence,Speaker Type,Number,User ID,Content,
Agent Judgment Score,Triggered,Agent Strategy,Agent Insertion,Agent Number
```

### 5. Questionnaire Function

Automatically enters questionnaire phase after experiment ends:

1. **Questionnaire Trigger**: Host clicks "End Experiment" button
2. **Rating Interface**: Users rate all other participants (1-10 points)
   - 1 point = Very certain not an Agent
   - 10 points = Very certain is an Agent
3. **Questionnaire Progress**: Shows completion progress (completed/total)
4. **Statistics Results**: Shows experiment statistics after all users complete

### 6. Multi-device Access

Supports simultaneous access from multiple devices on the same WiFi network:

1. **Get Server IP**
   ```bash
   ipconfig  # Windows
   ifconfig  # Linux/Mac
   ```

2. **Access from Other Devices**
   - Ensure devices are connected to the same WiFi
   - Browser access: `http://192.168.x.x:5173` (LoRA system)
   - Or: `http://192.168.x.x:5174` (ChatGPT system)

## ⚙️ Configuration Parameters

### LoRA System Configuration (`backend/Core.py`)

```python
MAX_LENGTH = 256              # Maximum text length
THRESHOLD = 0.60              # Willingness threshold (triggers insertion when exceeded)
HISTORY_N = 12                # Context history sentence count
GPU_QUEUE_MAX = 300           # Inference queue limit
```

### WebSocket Configuration (`backend/Websocket.py`)

```python
WS_LOG = True                 # Server log switch
HISTORY_N = 12                # Recent N sentences as context
MAX_HISTORY = 100             # Maximum history retention
```

### ChatGPT System Configuration (`backend/CoreChatgpt.py`)

```python
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"  # Model used
TEMPERATURE = 0.7             # Generation temperature
MAX_TOKENS = 80               # Maximum token count
```

## 📊 WebSocket Protocol

### Client → Server

#### 1. Join Room (join)
```json
{
  "type": "join",
  "nickname": "Alice",
  "intro": "I am someone who likes to help others",
  "persona_profile": {
    "background": "...",
    "personality_traits": ["empathetic", "supportive"],
    "speaking_style": "gentle",
    "values": "honesty"
  },
  "user_number": 42
}
```

#### 2. Send Message (chat_line)
```json
{
  "type": "chat_line",
  "text": "Hello everyone!"
}
```

#### 3. Set Scene (scene_fields)
```json
{
  "type": "scene_fields",
  "fields": {
    "time_of_day": "late night",
    "formality": "informal",
    "domain": "emotional exchange",
    "relationship": "friends",
    "topic_sensitivity": "medium",
    "participants": "3-5 people",
    "ai_preference": "supportive",
    "platform": "bedroom"
  }
}
```

#### 4. Set Topic (topic)
```json
{
  "type": "topic",
  "topic": "work_stress"
}
```

#### 5. Submit Questionnaire (questionnaire_answer)
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

### Server → Client

#### 1. Chat Acknowledgment (chat_ack)
```json
{
  "type": "chat_ack",
  "seq": 1,
  "status": "queued"
}
```

#### 2. Message Update (chat_update)
```json
{
  "type": "chat_update",
  "seq": 1,
  "status": "done",
  "text": "Hello everyone!",
  "user_id": "u_abc123",
  "nickname": "Alice",
  "display_number": 42,
  "final_willingness": 0.72,
  "triggered": true,
  "agent_text": "Nice to meet everyone!",
  "agent_strategy": "comforting",
  "agent_number": 58
}
```

#### 3. Experiment Statistics (experiment_stats)
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

## 🐛 Troubleshooting

### Issue 1: Model Loading Failure

**Symptoms**: Backend startup error, unable to load LoRA model

**Solutions**:
- Check if model paths are correct
- Verify LoRA checkpoint files are complete
- Verify CUDA/PyTorch version compatibility
- Check if GPU memory is sufficient

### Issue 2: WebSocket Connection Failure

**Symptoms**: Frontend shows "Connection failed" or cannot receive messages

**Solutions**:
- Confirm backend server is running
- Check firewall settings (port 8765 needs to be open)
- Verify frontend access address is correct
- Check browser console (F12) for error messages

### Issue 3: OpenAI API Call Failure

**Symptoms**: ChatGPT system cannot generate insertions

**Solutions**:
- Check if environment variable `OPENAI_API_KEY` is set
- Verify API key validity
- Confirm network connection is normal
- Check if API quota is sufficient

### Issue 4: Multi-device Access Failure

**Symptoms**: Other devices cannot open frontend page

**Solutions**:
- Ensure all devices are on the same WiFi network
- Check if firewall is blocking ports 5173/5174
- Verify server IP address is correct
- Try using `0.0.0.0` instead of `localhost` to start service

### Issue 5: Questionnaire Function Anomaly

**Symptoms**: Questionnaire cannot be submitted or progress does not update

**Solutions**:
- Ensure all users have completed the "Join Room" step
- Check backend logs for questionnaire status
- Verify user numbers are correctly recorded
- Refresh page and rejoin

## 📝 Development Notes

### Code Architecture

**Backend Architecture:**
- `Websocket.py` / `WebsocketChatgpty.py`: WebSocket server, handles connections and message routing
- `Core.py` / `CoreChatgpt.py`: Inference core, performs willingness prediction and insertion generation

**Frontend Architecture:**
- Built with React + Vite
- Real-time WebSocket client communication
- State management: chat history, user information, experiment status

### Extension Suggestions

- Support more strategy types
- Add historical dialogue context management
- Implement multi-turn dialogue intent recognition
- Add performance monitoring and statistics charts
- Support experiment configuration export/import

## 📄 Related Documentation

- `my-chat-app2/完整启动指南.md` - LoRA system detailed startup guide
- `my-chat-app2/问卷功能说明.md` - Questionnaire function documentation
- `my-chat-app2/TEST_GUIDE.md` - Multi-window testing guide
- `my-chat-app2ChatgptTest/启动指南.md` - ChatGPT system startup guide

## 📞 Contact

For questions or suggestions, please submit an Issue or contact: **18611980615@88.com**

---

**Note**: This project is for academic research purposes. Please ensure compliance with relevant ethical standards and privacy protection requirements.
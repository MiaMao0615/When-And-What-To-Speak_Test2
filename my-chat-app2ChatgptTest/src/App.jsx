import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import "./ChatRoom.css";

// ChatGPT 系统使用端口 8766
const WS_URL = `ws://${window.location.hostname}:8766`;

// 清理后的纯中文选项
const SCENE_OPTIONS = {
  time_of_day: ["早晨", "中午", "下午", "傍晚", "夜晚", "深夜"],
  formality: ["正式场合", "半正式", "非正式场合"],
  domain: ["工作或职场", "学习/课堂", "家庭日常", "语音开黑", "社交聚会", "公共场所", "单人独处"],
  relationship: ["陌生人", "同事", "朋友", "恋人", "上下级", "师生", "亲子"],
  topic_sensitivity: ["较低", "中等", "较高"],
  participants: ["1 人", "2 人", "3 人", "4 人及以上"],
  ai_preference: ["更克制", "适度参与", "更主动"],
  platform: ["文字群聊", "语音通话", "视频通话", "线下面对面", "游戏语音", "论坛/评论区"],
};

function App() {
  // 个人信息表单
  const [personaProfile, setPersonaProfile] = useState({
    nickname: "",
    intro: "",
    personality_traits: "",
    speaking_style: "",
    values: "",
  });

  const [joined, setJoined] = useState(false);
  const [self, setSelf] = useState({ user_id: "", nickname: "" });
  const [messages, setMessages] = useState([]);
  const [currentInput, setCurrentInput] = useState("");

  // 数字ID分配系统 (1-100 随机分配)
  const [userIdToNumber, setUserIdToNumber] = useState({}); // user_id -> number
  const [numberToUserId, setNumberToUserId] = useState({}); // number -> user_id
  const [myNumber, setMyNumber] = useState(null); // 自己的数字ID
  const [agentNumber, setAgentNumber] = useState(null); // Agent的数字ID

  const [topicDraft, setTopicDraft] = useState("自由交谈");
  const [sceneFields, setSceneFields] = useState({
    time_of_day: "早晨", formality: "非正式场合", domain: "社交聚会",
    relationship: "朋友", topic_sensitivity: "较低", participants: "2 人",
    ai_preference: "适度参与", platform: "文字群聊", extra: "",
  });

  const [roomState, setRoomState] = useState({ topic_en: "", scene_system: "" });
  const [experimentEnded, setExperimentEnded] = useState(false);
  const [experimentStats, setExperimentStats] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [questionnaireStarted, setQuestionnaireStarted] = useState(false);
  const [questionnaireCompleted, setQuestionnaireCompleted] = useState(false);
  const [participants, setParticipants] = useState([]); // 所有参与者列表
  const [questionnaireAnswers, setQuestionnaireAnswers] = useState({}); // 问卷答案 {target_number: score}
  const [questionnaireProgress, setQuestionnaireProgress] = useState({ completed: 0, total: 0 }); // 问卷进度
  const [roomId, setRoomId] = useState(""); // 当前实验的房间ID
  const [showRoomIdInput, setShowRoomIdInput] = useState(false); // 是否显示房间ID输入框
  const socketRef = useRef(null);
  const userIdToNumberRef = useRef({});
  const usedNumbersRef = useRef(new Set()); // 已使用的数字集合

  // 分配随机数字ID（1-100），避免重复
  const assignNumber = useCallback((userId) => {
    if (userIdToNumberRef.current[userId]) {
      return userIdToNumberRef.current[userId];
    }
    
    // 如果所有数字都用完了，返回 null
    if (usedNumbersRef.current.size >= 100) {
      return null;
    }
    
    // 随机生成一个 1-100 之间的数字，直到找到一个未使用的
    let num;
    let attempts = 0;
    do {
      num = Math.floor(Math.random() * 100) + 1; // 1-100
      attempts++;
      // 防止无限循环（理论上不可能，但保险起见）
      if (attempts > 1000) {
        return null;
      }
    } while (usedNumbersRef.current.has(num));
    
    // 标记为已使用
    usedNumbersRef.current.add(num);
    userIdToNumberRef.current[userId] = num;
    setUserIdToNumber(prev => ({ ...prev, [userId]: num }));
    setNumberToUserId(prev => ({ ...prev, [num]: userId }));
    
    return num;
  }, []);

  // 获取显示用的数字ID
  const getDisplayNumber = useCallback((userId) => {
    if (!userId) return null;
    return userIdToNumberRef.current[userId] || assignNumber(userId);
  }, [assignNumber]);

  const sendToBackend = (data) => {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
  };

  useEffect(() => {
    if (!joined) return;

    const ws = new WebSocket(WS_URL);
    socketRef.current = ws;

    ws.onopen = () => {
      // 只发送个人信息给后端，不发送场景设置
      // 注意：用户编号在join时可能还未分配，会在chat_line时发送
      sendToBackend({
        type: "join",
        nickname: personaProfile.nickname.trim() || "匿名用户",
        intro: personaProfile.intro.trim(),
        personality_traits: personaProfile.personality_traits
          .split(",")
          .map(s => s.trim())
          .filter(Boolean),
        speaking_style: personaProfile.speaking_style.trim(),
        values: personaProfile.values.trim(),
        user_number: myNumber, // 如果已经分配了编号，发送给后端
      });
    };

    ws.onmessage = (event) => {
      let data = JSON.parse(event.data);
      
      // join_ok: 分配自己的数字ID
      if (data.type === "join_ok") {
        const user_id = data.user_id;
        setSelf({ user_id, nickname: data.nickname });
        // 保存到 ref 以便在消息处理中使用
        if (socketRef.current) {
          socketRef.current._selfUserId = user_id;
        }
        const myNum = assignNumber(user_id);
        setMyNumber(myNum);
        // 发送用户编号给后端（如果已经分配）
        if (myNum) {
          sendToBackend({
            type: "user_number",
            user_id: user_id,
            user_number: myNum
          });
        }
      }
      
      // state_update: 更新房间状态（从服务器同步场景设置）
      if (data.type === "state_update") {
        setRoomState({ topic_en: data.topic_en, scene_system: data.scene_system });
        // 同步服务器返回的场景字段到本地状态（如果有）
        if (data.scene_fields && Object.keys(data.scene_fields).length > 0) {
          setSceneFields(prev => ({ ...prev, ...data.scene_fields }));
        }
        if (data.topic_en) {
          setTopicDraft(data.topic_en);
        }
        // 同步实验结束状态
        if (data.experiment_ended) {
          setExperimentEnded(true);
        }
      }
      
      // experiment_ended: 实验结束
      if (data.type === "experiment_ended") {
        setExperimentEnded(true);
        setExperimentStats(data.stats);
        console.log("[experiment] 实验已结束", data.stats);
      }
      
      // chat_ack: 用户消息，使用数字ID显示
      if (data.type === "chat_ack") {
        const user_id = data.user?.user_id;
        const displayNum = getDisplayNumber(user_id);
        // 使用 ref 获取最新的 self.user_id
        const currentSelfUserId = socketRef.current?._selfUserId;
        setMessages((prev) => [...prev, {
          id: `u-${data.seq}`,
          user_id: user_id,
          displayNumber: displayNum,
          text: data.text,
          isMe: user_id === currentSelfUserId
        }]);
      }
      
      // chat_update: Agent消息，分配Agent的数字ID
      if (data.type === "chat_update") {
        const agent = data.agent;
        if (agent?.type === "agent_utterance" && agent.text) {
          // Agent使用固定的特殊标识，分配一个数字ID
          const agentUserId = "agent";
          const agentDisplayNum = getDisplayNumber(agentUserId);
          // 更新 agentNumber state（用于显示）
          if (agentDisplayNum) {
            setAgentNumber(prev => prev || agentDisplayNum);
            // 通知后端Agent的编号
            sendToBackend({
              type: "agent_number",
              agent_number: agentDisplayNum,
              seq: data.seq
            });
          }
          setMessages((prev) => [...prev, {
            id: `a-${data.seq}`,
            user_id: agentUserId,
            displayNumber: agentDisplayNum,
            text: agent.text,
            isMe: false
          }]);
        }
      }
    };
    return () => ws.close();
  }, [joined, getDisplayNumber, assignNumber]);

  const handleSendMessage = () => {
    if (!currentInput.trim()) return;
    // 发送消息时包含用户编号
    sendToBackend({ 
      type: "chat_line", 
      text: currentInput,
      user_number: myNumber // 包含用户编号
    });
    setCurrentInput("");
  };

  // 未加入时显示个人信息填写界面
  if (!joined) {
    return (
      <div className="page" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '20px' }}>
        <div className="setup-card" style={{ maxWidth: '600px', width: '100%' }}>
          <h2 className="setup-title">双盲测试：个人信息</h2>
          <p className="hint" style={{ marginBottom: '20px' }}>
            请填写您的基本信息。这些信息将用于后端处理，但在聊天界面中将使用数字ID显示（不显示真实昵称）。
          </p>
          
          <div className="settings-block" style={{ marginBottom: '15px' }}>
            <label className="settings-label">昵称（后端使用）</label>
            <input 
              className="settings-input" 
              value={personaProfile.nickname} 
              onChange={e => setPersonaProfile(prev => ({...prev, nickname: e.target.value}))} 
              placeholder="例如：张三"
            />
          </div>

          <div className="settings-block" style={{ marginBottom: '15px' }}>
            <label className="settings-label">个人简介（必填）</label>
            <textarea 
              className="settings-input" 
              value={personaProfile.intro} 
              onChange={e => setPersonaProfile(prev => ({...prev, intro: e.target.value}))} 
              placeholder="例如：我是一个传播学的大四学生，正在准备申研，最近压力很大..."
              style={{ minHeight: '80px' }}
            />
          </div>

          <div className="settings-block" style={{ marginBottom: '15px' }}>
            <label className="settings-label">性格特质（可选，逗号分隔）</label>
            <input 
              className="settings-input" 
              value={personaProfile.personality_traits} 
              onChange={e => setPersonaProfile(prev => ({...prev, personality_traits: e.target.value}))} 
              placeholder="例如：消极, 悲伤, 劳累"
            />
          </div>

          <div className="settings-block" style={{ marginBottom: '15px' }}>
            <label className="settings-label">说话风格（可选）</label>
            <input 
              className="settings-input" 
              value={personaProfile.speaking_style} 
              onChange={e => setPersonaProfile(prev => ({...prev, speaking_style: e.target.value}))} 
              placeholder="例如：有礼貌但悲观"
            />
          </div>

          <div className="settings-block" style={{ marginBottom: '20px' }}>
            <label className="settings-label">核心价值观（可选）</label>
            <input 
              className="settings-input" 
              value={personaProfile.values} 
              onChange={e => setPersonaProfile(prev => ({...prev, values: e.target.value}))} 
              placeholder="例如：好好学习 天天向上"
            />
          </div>

          <button 
            className="primary-btn" 
            onClick={() => {
              if (!personaProfile.intro.trim()) {
                alert("请至少填写个人简介");
                return;
              }
              // 直接进入聊天室，不设置场景
              setJoined(true);
            }}
          >
            进入聊天室
          </button>
        </div>
      </div>
    );
  }


  // 聊天界面
  return (
    <div className="page">
      <div className="layout">
        <div className="chat">
          <div className="chat-header">
            <div className="chat-topic">话题：<strong>{roomState.topic_en || topicDraft}</strong></div>
            <div className="chat-topic">您的编号：<strong>#{myNumber || "等待分配"}</strong></div>
          </div>
          <div className="messages">
            {messages.map((m) => (
              <div key={m.id} className={`msg-row ${m.isMe ? "user2" : "user1"}`}>
                <div className="avatar">{m.displayNumber || "?"}</div>
                <div className="bubble">
                  <div className="sender">#{m.displayNumber || "?"}</div>
                  <div className="text">{m.text}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="composer">
            <input 
              className="input" 
              value={currentInput} 
              onChange={(e) => setCurrentInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !experimentEnded && handleSendMessage()} 
              placeholder={experimentEnded ? "实验已结束，无法发言" : "输入消息..."}
              disabled={experimentEnded}
              style={{ opacity: experimentEnded ? 0.5 : 1 }}
            />
            <button 
              className="send" 
              onClick={handleSendMessage}
              disabled={experimentEnded}
            >
              发送
            </button>
          </div>
        </div>

        <div className="agent">
          <div className="agent-card">
            <div className="agent-title" style={{ fontWeight: 900, marginBottom: '10px' }}>实时场景调整</div>
            <div className="settings">
              <div className="settings-block">
                <label className="settings-label">修改话题</label>
                <div className="settings-row">
                  <input className="settings-input" value={topicDraft} onChange={e => setTopicDraft(e.target.value)} />
                  <button className="settings-btn" onClick={() => sendToBackend({type:"topic", topic: topicDraft})}>更新</button>
                </div>
              </div>
              <div className="settings-grid">
                {Object.keys(SCENE_OPTIONS).map(key => (
                  <div key={key} className="field">
                    <label className="field-label">{key}</label>
                    <select className="settings-input" value={sceneFields[key]} 
                      onChange={e => setSceneFields(prev => ({...prev, [key]: e.target.value}))}>
                      {SCENE_OPTIONS[key].map(opt => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <button className="primary-btn" style={{marginTop: '10px'}} onClick={() => sendToBackend({type: "scene_fields", fields: sceneFields})}>
                同步更新场景
              </button>
              
              {/* 实验结束按钮和统计 */}
              <div style={{marginTop: '20px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)'}}>
                {!experimentEnded ? (
                  <>
                    {!showRoomIdInput ? (
                      <button 
                        className="primary-btn" 
                        style={{
                          background: 'rgba(220, 38, 38, 0.8)',
                          marginBottom: '10px',
                          width: '100%'
                        }}
                        onClick={() => {
                          setShowRoomIdInput(true);
                        }}
                      >
                        结束实验
                      </button>
                    ) : (
                      <div style={{marginBottom: '10px', padding: '15px', background: 'rgba(220, 38, 38, 0.1)', borderRadius: '8px'}}>
                        <label className="settings-label" style={{marginBottom: '8px', display: 'block'}}>
                          请输入房间ID（必填）：
                        </label>
                        <input 
                          className="settings-input" 
                          value={roomId}
                          onChange={(e) => setRoomId(e.target.value)}
                          placeholder="例如：room_001、实验组A等"
                          style={{marginBottom: '10px'}}
                        />
                        <div style={{display: 'flex', gap: '10px'}}>
                          <button 
                            className="primary-btn" 
                            style={{
                              background: 'rgba(220, 38, 38, 0.8)',
                              flex: 1
                            }}
                            onClick={() => {
                              if (!roomId.trim()) {
                                alert("请输入房间ID");
                                return;
                              }
                              if (window.confirm(`确定要结束实验吗？房间ID: ${roomId}\n实验结束后将无法继续发言。`)) {
                                sendToBackend({ type: "end_experiment", room_id: roomId.trim() });
                                setShowRoomIdInput(false);
                              }
                            }}
                          >
                            确认结束
                          </button>
                          <button 
                            className="settings-btn" 
                            onClick={() => {
                              setShowRoomIdInput(false);
                              setRoomId("");
                            }}
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{marginBottom: '10px'}}>
                    <div style={{padding: '10px', background: 'rgba(220, 38, 38, 0.1)', borderRadius: '8px', textAlign: 'center', marginBottom: '10px'}}>
                      <div style={{color: '#ef4444', fontWeight: 'bold', marginBottom: '5px'}}>实验已结束</div>
                      {roomId && (
                        <div style={{fontSize: '12px', color: 'rgba(255,255,255,0.7)', marginBottom: '5px'}}>
                          房间ID: {roomId}
                        </div>
                      )}
                      <button 
                        className="primary-btn" 
                        style={{
                          background: 'rgba(56, 189, 248, 0.92)',
                          marginTop: '10px'
                        }}
                        onClick={() => setShowStats(!showStats)}
                      >
                        {showStats ? '隐藏统计' : '查看统计'}
                      </button>
                    </div>
                    
                    {/* 重置实验按钮（主持人使用） */}
                    {questionnaireCompleted && (
                      <button 
                        className="primary-btn" 
                        style={{
                          background: 'rgba(34, 197, 94, 0.8)',
                          width: '100%',
                          marginTop: '10px'
                        }}
                        onClick={() => {
                          if (window.confirm("确定要重置实验吗？这将清空当前实验数据，允许开始新的实验。")) {
                            sendToBackend({ type: "reset_experiment" });
                          }
                        }}
                      >
                        重置实验（开始新一轮）
                      </button>
                    )}
                  </div>
                )}
                
                {/* 统计信息面板 */}
                {showStats && experimentStats && (
                  <div style={{
                    marginTop: '15px',
                    padding: '15px',
                    background: 'rgba(0,0,0,0.3)',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }}>
                    <div style={{fontWeight: 'bold', marginBottom: '10px', fontSize: '14px'}}>实验统计</div>
                    <div style={{lineHeight: '1.8'}}>
                      <div>总用户数：{experimentStats.total_users || 0}</div>
                      <div>总消息数：{experimentStats.total_messages || 0}</div>
                      <div>Agent响应次数：{experimentStats.agent_responses || 0}</div>
                      <div>平均意愿分数：{(experimentStats.average_willingness || 0).toFixed(4)}</div>
                      <div>触发率：{((experimentStats.agent_trigger_rate || 0) * 100).toFixed(2)}%</div>
                      {roomId && (
                        <div style={{marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.1)'}}>
                          <div style={{fontSize: '12px', fontWeight: 'bold'}}>房间ID：{roomId}</div>
                        </div>
                      )}
                      {experimentStats.experiment_duration && (
                        <div style={{marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.1)'}}>
                          实验时长：{experimentStats.experiment_duration}
                        </div>
                      )}
                      {experimentStats.csv_file && (
                        <div style={{marginTop: '10px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.1)'}}>
                          <div style={{fontSize: '11px', color: 'rgba(255,255,255,0.6)', wordBreak: 'break-all'}}>
                            CSV文件：{experimentStats.csv_file?.split(/[\\/]/).pop() || ''}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
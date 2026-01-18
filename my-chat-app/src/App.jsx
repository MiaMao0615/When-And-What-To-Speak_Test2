import React, { useEffect, useMemo, useRef, useState } from "react";
import "./ChatRoom.css";

/**
 * ✅ 协议保持不变：
 * - chat_line -> chat_ack(seq, queued) -> chat_update(seq, agent)
 * ✅ 关键改动：
 * - chat_update 时，如果 agent.text 有内容，就“追加一条新的 AI 消息气泡”
 * - 不再在用户消息 bubble 内嵌 AI 评估/插话文本
 */

const WS_URL = `ws://${window.location.hostname}:8765`;
const DEFAULT_THRESHOLD = 0.6;

const SCENE_OPTIONS = {
  time_of_day: ["早晨", "中午", "下午", "傍晚", "夜晚", "深夜"],
  formality: ["正式场合", "半正式", "非正式场合"],
  domain: ["工作或职场", "学习/课堂", "家庭日常", "游戏或语音开黑场景", "社交聚会", "公共场所", "单人独处"],
  relationship: ["陌生人", "同事", "朋友", "恋人或暧昧关系之间", "上下级", "师生", "亲子"],
  topic_sensitivity: ["较低", "中等", "较高"],
  participants: ["1 人（单人场景）", "2 人", "3 人", "4 人及以上"],
  ai_preference: ["希望 AI 更克制", "希望 AI 适度参与", "希望 AI 更主动参与和说话"],
  platform: ["文字群聊（如 QQ/微信群）", "语音通话", "视频通话", "线下面对面", "游戏内语音", "论坛/评论区"],
};

function App() {
  // ===== Join / Persona =====
  const [joinForm, setJoinForm] = useState({
    nickname: "",
    intro: "",
    personalityTraits: "",
    speakingStyle: "",
    values: "",
  });
  const [joined, setJoined] = useState(false);
  const [self, setSelf] = useState({ user_id: "", nickname: "" });

  // ===== Chat =====
  // message schema:
  // { id, seq, kind: "user"|"agent", user?, text, status, agent_meta?, ts }
  const [messages, setMessages] = useState([]);
  const [currentInput, setCurrentInput] = useState("");

  // ===== Room state =====
  const [topicDraft, setTopicDraft] = useState("");
  const [sceneFields, setSceneFields] = useState({
    time_of_day: "早晨",
    formality: "正式场合",
    domain: "游戏或语音开黑场景",
    relationship: "恋人或暧昧关系之间",
    topic_sensitivity: "较低",
    participants: "1 人（单人场景）",
    ai_preference: "希望 AI 更主动参与和说话",
    platform: "文字群聊（如 QQ/微信群）",
    extra: "",
  });

  const [roomState, setRoomState] = useState({
    topic_en: "",
    scene_system: "",
    scene_user: "",
    scene_fields: {},
  });

  // ===== Agent monitor =====
  const [connStatus, setConnStatus] = useState("idle");
  const [lastPayload, setLastPayload] = useState(null);
  const [lastAgentPayload, setLastAgentPayload] = useState(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [loraInputs, setLoraInputs] = useState({ persona_text: "", scene_text: "", topic_text: "", history_ctx: "" });
  const [onlineUsers, setOnlineUsers] = useState([]);

  const socketRef = useRef(null);

  const statusLabel = useMemo(() => {
    if (connStatus === "connected") return { text: "Connected", cls: "ok" };
    if (connStatus === "connecting") return { text: "Connecting", cls: "warn" };
    if (connStatus === "closed") return { text: "Closed", cls: "bad" };
    if (connStatus === "error") return { text: "Error", cls: "bad" };
    return { text: "Idle", cls: "muted" };
  }, [connStatus]);

  const sendToBackend = (data) => {
    const ws = socketRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(data));
  };

  const showAgentPopup = (text) => {
    const popup = document.getElementById("agent-popup");
    if (!popup) return;
    popup.innerText = text;
    popup.style.display = "block";
    setTimeout(() => {
      popup.style.display = "none";
    }, 3500);
  };

  // ===== connect WS after joined =====
  useEffect(() => {
    if (!joined) return;

    setConnStatus("connecting");
    const ws = new WebSocket(WS_URL);
    socketRef.current = ws;

    ws.onopen = () => {
      setConnStatus("connected");
      sendToBackend({
        type: "join",
        nickname: joinForm.nickname.trim(),
        intro: joinForm.intro.trim(),
        personality_traits: joinForm.personalityTraits
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        speaking_style: joinForm.speakingStyle.trim(),
        values: joinForm.values.trim(),
      });
    };

    ws.onerror = () => setConnStatus("error");
    ws.onclose = () => setConnStatus("closed");

    ws.onmessage = (event) => {
      let data = null;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      setLastPayload(data);

      // ===== join result =====
      if (data.type === "join_ok") {
        setSelf({ user_id: data.user_id || "", nickname: data.nickname || joinForm.nickname.trim() });
        return;
      }
      if (data.type === "join_fail") {
        alert(data.msg || "join 失败：请检查 nickname / intro");
        try { ws.close(); } catch {}
        setJoined(false);
        return;
      }

      // ===== presence =====
      if (data.type === "presence") {
        if (Array.isArray(data.online)) setOnlineUsers(data.online);
        return;
      }

      // ===== state_update =====
      if (data.type === "state_update") {
        const nextTopic = data.topic_en ?? "";
        const nextScene = data.scene_system ?? "";
        const nextSceneUser = data.scene_user ?? "";
        const nextFields = data.scene_fields ?? {};

        setTopicDraft(nextTopic);
        if (nextFields && typeof nextFields === "object") {
          setSceneFields((prev) => ({ ...prev, ...nextFields }));
        }

        setRoomState({
          topic_en: nextTopic,
          scene_system: nextScene,
          scene_user: nextSceneUser,
          scene_fields: nextFields,
        });
        return;
      }

      // ===== chat ack: 先把用户消息显示出来 =====
      if (data.type === "chat_ack") {
        const seq = data.seq;
        const user = data.user || {};
        const text = String(data.text || "");
        const status = data.status || "queued";

        setMessages((prev) => [
          ...prev,
          {
            id: `u-${seq}`,
            seq,
            kind: "user",
            user,
            text,
            status,
            agent_meta: null,
            ts: data.ts || Date.now(),
          },
        ]);
        return;
      }

      // ===== chat update: 回填状态 + 如果有 agent.text -> 追加 AI 消息气泡 =====
      if (data.type === "chat_update") {
        const seq = data.seq;
        const agent = data.agent || null;

        // 1) 回填 user 消息状态 + 存一份 agent_meta（可用于 debug，不渲染到用户 bubble 里）
        setMessages((prev) =>
          prev.map((m) =>
            m.kind === "user" && m.seq === seq
              ? { ...m, status: "done", agent_meta: agent || null }
              : m
          )
        );

        // 2) 若 agent 有插话文本：单独追加一条 AI 消息（这就是你要的“拆分气泡”）
        if (agent && agent.type === "agent_utterance") {
          setLastAgentPayload(agent);

          if (agent.debug_inputs && typeof agent.debug_inputs === "object") {
            setLoraInputs((prev) => ({ ...prev, ...agent.debug_inputs }));
          }

          const insertText = String(agent.text || "").trim();
          if (insertText.length > 0) {
            // popup 可保留
            showAgentPopup(insertText);

            setMessages((prev) => [
              ...prev,
              {
                id: `a-${seq}`,
                seq,
                kind: "agent",
                user: { user_id: "agent", nickname: "AI" },
                text: insertText,
                status: "done",
                agent_meta: agent, // 给右侧面板显示 final/strategy 用
                ts: data.ts || Date.now(),
              },
            ]);
          }
        }
        return;
      }

      // ===== fallback: 直接 agent_utterance（兼容老后端）=====
      if (data.type === "agent_utterance") {
        setLastAgentPayload(data);
        if (data.debug_inputs && typeof data.debug_inputs === "object") {
          setLoraInputs((prev) => ({ ...prev, ...data.debug_inputs }));
        }
      }
    };

    return () => {
      try {
        ws.close();
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined]);

  // ===== handlers =====
  const handleJoinSubmit = (e) => {
    e.preventDefault();
    const nickname = joinForm.nickname.trim();
    const intro = joinForm.intro.trim();
    if (!nickname || !intro) {
      alert("必须填写：昵称 + 简介");
      return;
    }
    setJoined(true);
  };

  const handleSendMessage = () => {
    const text = currentInput.trim();
    if (!text) return;
    setCurrentInput("");
    sendToBackend({ type: "chat_line", text });
  };

  const handleUpdateTopic = () => {
    const t = (topicDraft || "").trim();
    sendToBackend({ type: "topic", topic: t });
  };

  const handleUpdateSceneFields = () => {
    sendToBackend({ type: "scene_fields", fields: { ...sceneFields } });
  };

  const updateField = (key, value) => {
    setSceneFields((prev) => ({ ...prev, [key]: value }));
  };

  // agent monitor derived
  const agentWillingness = Number.isFinite(Number(lastAgentPayload?.final_willingness))
    ? Number(lastAgentPayload.final_willingness)
    : 0;
  const threshold = Number.isFinite(Number(lastAgentPayload?.threshold))
    ? Number(lastAgentPayload.threshold)
    : DEFAULT_THRESHOLD;

  const agentActive = agentWillingness > threshold;

  // ===== Join page =====
  if (!joined) {
    return (
      <div className="page">
        <div className="setup-card">
          <div className="setup-title">进入公共聊天室</div>

          <form onSubmit={handleJoinSubmit} className="setup-form">
            <label>
              昵称 必填
              <input
                type="text"
                value={joinForm.nickname}
                onChange={(e) => setJoinForm((p) => ({ ...p, nickname: e.target.value }))}
                placeholder="例如：mao"
              />
            </label>

            <label>
              简介 必填
              <textarea
                value={joinForm.intro}
                onChange={(e) => setJoinForm((p) => ({ ...p, intro: e.target.value }))}
                placeholder="例如：我是一个传播学的大四学生，正在准备申研，最近压力很大..."
              />
            </label>

            <label>
              性格特质 可选 逗号分隔
              <input
                type="text"
                value={joinForm.personalityTraits}
                onChange={(e) => setJoinForm((p) => ({ ...p, personalityTraits: e.target.value }))}
                placeholder="例如：消极, 悲伤, 劳累"
              />
            </label>

            <label>
              说话风格 可选
              <input
                type="text"
                value={joinForm.speakingStyle}
                onChange={(e) => setJoinForm((p) => ({ ...p, speakingStyle: e.target.value }))}
                placeholder="例如：有礼貌但悲观"
              />
            </label>

            <label>
              核心价值观 可选
              <input
                type="text"
                value={joinForm.values}
                onChange={(e) => setJoinForm((p) => ({ ...p, values: e.target.value }))}
                placeholder="例如：好好学习 天天向上"
              />
            </label>

            <button type="submit" className="primary-btn">
              提交并连接
            </button>
          </form>

          <div className="hint">
            连接到 <span className="mono">{WS_URL}</span>；连接成功后会自动发送 <span className="mono">join</span>：nickname+intro。
          </div>
        </div>
      </div>
    );
  }

  // ===== Main chat =====
  return (
    <div className="page">
      <div className="layout">
        {/* Left: Chat */}
        <div className="chat">
          <div className="chat-header">
            <div className="chat-topic">
              💬 话题: <strong>{roomState.topic_en || "未设置"}</strong>
            </div>
            <div className="chat-topic">
              👤 我：<strong>{self.nickname || joinForm.nickname.trim() || "未 join_ok"}</strong>
            </div>
          </div>

          <div className="messages">
            {messages.map((m) => {
              // agent 独立气泡
              if (m.kind === "agent") {
                return (
                  <div key={m.id} className="msg-row agent">
                    <div className={`avatar ${agentActive ? "hot" : ""}`}>AI</div>
                    <div className="bubble">
                      <div className="sender">
                        AI <span className="mono">#{m.seq}</span> <span className="tag muted">{m.status}</span>
                      </div>
                      <div className="text">{m.text}</div>

                      {/* 可选：在 AI bubble 里展示简短 meta（不展示用户 utterance） */}
                      {m.agent_meta ? (
                        <div className="meta">
                          <span className="tag">final: {Number(m.agent_meta.final_willingness ?? 0).toFixed(2)}</span>
                          <span className="tag">thr: {Number(m.agent_meta.threshold ?? DEFAULT_THRESHOLD).toFixed(2)}</span>
                          <span className="tag mono">{m.agent_meta.strategy || "disabled"}</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              }

              // user bubble
              const isMe =
                m.user?.user_id && self.user_id
                  ? m.user.user_id === self.user_id
                  : m.user?.nickname === self.nickname;

              const roleClass = isMe ? "user2" : "user1"; // user2 = right bubble
              const displayName = m.user?.nickname || "Unknown";

              return (
                <div key={m.id} className={`msg-row ${roleClass}`}>
                  <div className="avatar">{displayName.slice(0, 1).toUpperCase()}</div>

                  <div className="bubble">
                    <div className="sender">
                      {displayName} <span className="mono">#{m.seq}</span> <span className="tag muted">{m.status}</span>
                    </div>
                    <div className="text">{m.text}</div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="composer">
            <input
              className="input"
              type="text"
              value={currentInput}
              onChange={(e) => setCurrentInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              placeholder="输入一句话…"
            />
            <button className="send" onClick={handleSendMessage}>
              发送
            </button>
          </div>
        </div>

        {/* Right: Agent Monitor */}
        <div className="agent">
          <div className="agent-card">
            <div className="agent-top">
              <div className={`agent-avatar ${agentActive ? "hot" : ""}`}>AI</div>
              <div className="agent-title">
                <div className="agent-name">分析助手</div>
                <div className={`status ${statusLabel.cls}`}>
                  <span className="dot" /> {statusLabel.text}
                </div>
              </div>
            </div>

            <div className="metric">
              <div className="metric-row">
                <div className="metric-label">Last final_willingness</div>
                <div className="metric-value">{agentWillingness.toFixed(2)}</div>
              </div>

              <div className="bar">
                <div
                  className="bar-fill"
                  style={{
                    width: `${Math.max(0, Math.min(1, agentWillingness)) * 100}%`,
                  }}
                />
              </div>

              <div className="threshold">
                <span className="tag">threshold: {threshold.toFixed(2)}</span>
                {agentActive ? <span className="tag hot">插话触发</span> : <span className="tag muted">未触发</span>}
              </div>

              <div className="metric-row" style={{ marginTop: 10 }}>
                <div className="metric-label">Last strategy</div>
                <div className="metric-value mono">{lastAgentPayload?.strategy || "-"}</div>
              </div>

              <div className="metric-row">
                <div className="metric-label">Last text</div>
                <div className="metric-value mono">{lastAgentPayload?.text ? "✓" : "-"}</div>
              </div>
            </div>

            <div id="agent-popup" className="agent-popup"></div>

            {/* Settings Panel */}
            <div className="settings">
              <div className="settings-title">Room Settings (sync)</div>

              {/* Topic */}
              <div className="settings-block">
                <div className="settings-label">Topic</div>
                <div className="settings-row">
                  <input
                    className="settings-input"
                    value={topicDraft}
                    onChange={(e) => setTopicDraft(e.target.value)}
                    placeholder="Set topic..."
                  />
                  <button className="settings-btn" onClick={handleUpdateTopic}>
                    Update
                  </button>
                </div>
              </div>

              {/* Scene Fields */}
              <div className="settings-block">
                <div className="settings-label">Scene (structured)</div>

                <div className="settings-grid">
                  <div className="field">
                    <div className="field-label">时间</div>
                    <select
                      className="settings-input"
                      value={sceneFields.time_of_day}
                      onChange={(e) => updateField("time_of_day", e.target.value)}
                    >
                      {SCENE_OPTIONS.time_of_day.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">正式程度</div>
                    <select
                      className="settings-input"
                      value={sceneFields.formality}
                      onChange={(e) => updateField("formality", e.target.value)}
                    >
                      {SCENE_OPTIONS.formality.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">场景领域</div>
                    <select
                      className="settings-input"
                      value={sceneFields.domain}
                      onChange={(e) => updateField("domain", e.target.value)}
                    >
                      {SCENE_OPTIONS.domain.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">参与者关系</div>
                    <select
                      className="settings-input"
                      value={sceneFields.relationship}
                      onChange={(e) => updateField("relationship", e.target.value)}
                    >
                      {SCENE_OPTIONS.relationship.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">话题敏感度</div>
                    <select
                      className="settings-input"
                      value={sceneFields.topic_sensitivity}
                      onChange={(e) => updateField("topic_sensitivity", e.target.value)}
                    >
                      {SCENE_OPTIONS.topic_sensitivity.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">对话人数</div>
                    <select
                      className="settings-input"
                      value={sceneFields.participants}
                      onChange={(e) => updateField("participants", e.target.value)}
                    >
                      {SCENE_OPTIONS.participants.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">用户对 AI 偏好</div>
                    <select
                      className="settings-input"
                      value={sceneFields.ai_preference}
                      onChange={(e) => updateField("ai_preference", e.target.value)}
                    >
                      {SCENE_OPTIONS.ai_preference.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <div className="field-label">地点/平台</div>
                    <select
                      className="settings-input"
                      value={sceneFields.platform}
                      onChange={(e) => updateField("platform", e.target.value)}
                    >
                      {SCENE_OPTIONS.platform.map((x) => (
                        <option key={x} value={x}>{x}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="settings-label" style={{ marginTop: 8 }}>
                  补充 可选
                </div>
                <textarea
                  className="settings-textarea"
                  value={sceneFields.extra}
                  onChange={(e) => updateField("extra", e.target.value)}
                  placeholder="你想额外补充的场景信息..."
                />

                <button className="settings-btn full" onClick={handleUpdateSceneFields}>
                  Update Scene (Fields)
                </button>

                <div className="settings-hint">
                  下方是后端当前用于推理的 scene_system。字段由后端拼接，Core 会自动追加固定问句。
                </div>
                <pre className="scene-preview">{roomState.scene_system || "后端尚未设置"}</pre>
              </div>

              <div className="settings-hint">
                在线用户：{" "}
                <span className="mono">
                  {onlineUsers.map((u) => u.nickname).filter(Boolean).join(", ") || "无"}
                </span>
              </div>
            </div>

            <button className="debug-toggle" onClick={() => setDebugOpen((v) => !v)}>
              {debugOpen ? "隐藏调试信息" : "显示调试信息"}
            </button>

            {debugOpen && (
              <div className="debug-wrap">
                <pre className="debug">
{JSON.stringify(
  {
    roomState,
    self,
    onlineUsers,
    lastPayload,
    lastAgentPayload,
    loraInputs,
  },
  null,
  2
)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

# CoreChatgpt.py
# -*- coding: utf-8 -*-

"""
完全使用 ChatGPT 来判断插入意愿和生成插话内容：
- willingness 判断：使用 ChatGPT，输入场景信息、个人信息、话题、当前发言
- ChatGPT 返回 0-1 之间的数值表示插入意愿
- 如果意愿 > 0.6，调用 ChatGPT 生成插话内容
- 使用相同的 prompt 内容进行插话生成
"""

import json
import time
import re
from openai import OpenAI

# ================== 配置 ==================
THRESHOLD = 0.60

# ChatGPT 模型
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"
client = OpenAI()

# ===== Debug 控制 =====
DEBUG_LOG = True           # True 才打印控制台日志
EMIT_DEBUG_INPUTS = True   # True 才把 debug_inputs 发给前端
DEBUG_INPUT_TRUNC = 1200

# ================== scene_fields -> scene_prompt 的构造（供 Websocket 使用） ==================
SCENE_FIELD_ORDER = [
    ("time_of_day", "时间"),
    ("formality", "正式程度"),
    ("domain", "场景领域"),
    ("relationship", "参与者关系"),
    ("topic_sensitivity", "话题敏感度"),
    ("participants", "对话人数"),
    ("ai_preference", "用户对 AI 的偏好"),
    ("platform", "地点"),
]

def _norm_str(x) -> str:
    if x is None:
        return ""
    return str(x).strip()

def build_scene_prompt_from_fields(fields: dict) -> str:
    """
    Websocket 收到 type="scene_fields" 时会调用它。
    注意：这只是把字段拼成 scene_system 文本，不参与 LoRA 的“调用方式对齐”部分。
    """
    if not isinstance(fields, dict):
        fields = {}

    parts = []
    for k, label in SCENE_FIELD_ORDER:
        v = _norm_str(fields.get(k, ""))
        if v:
            parts.append(f"{label}：{v}")

    extra = _norm_str(fields.get("extra", ""))
    if extra:
        parts.append(f"补充：{extra}")

    head = "；".join(parts).strip()
    if head:
        head += "。"
    return head


# ================== 工具函数 ==================
def _now_ms() -> float:
    return time.perf_counter() * 1000.0

def init_models():
    """
    空函数，保留接口兼容性（不再加载模型）
    """
    if DEBUG_LOG:
        print("[init_models] ChatGPT-only mode, no local models needed")
    pass


# ================== ChatGPT willingness 判断 ==================
def _extract_number(text: str) -> float:
    """从文本中提取 0-1 之间的数值"""
    if not text:
        return 0.0
    text = text.strip()
    # 尝试提取数字
    matches = re.findall(r'0?\.\d+|1\.0*|[01]', text)
    if matches:
        try:
            val = float(matches[0])
            return max(0.0, min(1.0, val))
        except:
            pass
    # 如果没有找到，尝试解析 JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            val = data.get("willingness", data.get("value", data.get("score", 0.0)))
            return max(0.0, min(1.0, float(val)))
        return max(0.0, min(1.0, float(data)))
    except:
        pass
    return 0.0

def ask_chatgpt_for_willingness(
    persona_profile: dict,
    topic_en: str,
    utterance: str,
    scene_system: str,
    scene_user: str,
) -> float:
    """
    使用 ChatGPT 判断插入意愿
    输入：场景信息、个人信息、话题、当前发言
    返回：0-1 之间的数值
    """
    system_msg = """你是一个判断 AI 助手是否应该在多人对话中插话的系统。

你需要评估：在当前场景、话题、用户发言和对话历史的背景下，
AI 助手主动插话的"意愿"应该是多少？

评估标准：
- 0.0-0.3：不应该插话（对话正常进行，插话会打断）
- 0.3-0.6：可以考虑插话（对话有些停滞或需要澄清）
- 0.6-1.0：应该插话（对话陷入僵局、需要引导、需要澄清误解等）

只返回一个 0 到 1 之间的小数，不需要其他解释。
例如：0.65 或 0.23"""
    
    user_msg = f"""
场景信息（Scene）：
{scene_system or ''}

对话历史（Recent conversation）：
{scene_user or ''}

话题（Topic）：
{topic_en or ''}

个人信息（Persona Profile）：
{json.dumps(persona_profile or {}, ensure_ascii=False, indent=2)}

最新发言（Latest utterance）：
{utterance or ''}

请评估 AI 助手在这个时刻主动插话的意愿（0.0-1.0），只返回数字：
""".strip()

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=20,
        )
        raw = (resp.choices[0].message.content or "").strip()
        willingness = _extract_number(raw)
        if DEBUG_LOG:
            print(f"[willingness] ChatGPT returned: {raw} -> {willingness}")
        return willingness
    except Exception as e:
        if DEBUG_LOG:
            print(f"[willingness] ChatGPT error: {repr(e)}")
        return 0.0


# ================== ChatGPT strategy + insert ==================
def _extract_json_block(s: str):
    if not s:
        return None
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.S)
    if m:
        s = m.group(1).strip()
    m2 = re.search(r"(\{.*\})", s, flags=re.S)
    if m2:
        s = m2.group(1).strip()
    try:
        return json.loads(s)
    except Exception:
        return None

def _sanitize_insert(insert: str, utterance: str) -> str:
    """
    ✅ 核心兜底：防止 insert 复述/引用用户 utterance，避免“AI 气泡里出现用户原话”。
    策略（够稳、简单、可控）：
    - 去掉常见引用符号
    - 如果包含完整 utterance：直接剔除
    - 如果包含“你说/你刚说/你提到”等复述引导：删除该片段后半句
    - 最终太短则返回空串
    """
    insert = (insert or "").strip()
    utt = (utterance or "").strip()
    if not insert:
        return ""

    # 去掉常见引用符号/书名号
    for ch in ['“', '”', '"', "‘", "’", "'", "「", "」", "『", "』", "《", "》"]:
        insert = insert.replace(ch, "")

    # 直接移除完整 utterance
    if utt and utt in insert:
        insert = insert.replace(utt, "").strip()

    # 删除“复述引导”后半句（粗暴但有效）
    bad_markers = ["你刚说", "你说", "你刚刚说", "你提到", "如你所说", "你刚才说"]
    for bm in bad_markers:
        if bm in insert:
            insert = insert.split(bm)[0].strip()

    # 避免出现很长的重复片段（简单做法：若含连续大量相同字符或太短则判无效）
    if len(insert) < 6:
        return ""

    # 不要以顿号/逗号结尾（避免残句）
    insert = insert.rstrip("，,、;；:：")

    if len(insert) < 6:
        return ""
    return insert

def ask_chatgpt_for_insert_and_strategy(
    persona_profile: dict,
    topic_en: str,
    utterance: str,
    scene_system: str,
    scene_user: str,
) -> dict:
    system_msg = (
        "You are speaking because the system has already decided that intervening is necessary.\n\n"

        "You are not a chatbot, assistant, or moderator.\n"
        "You are a real participant in a multi-person conversation.\n\n"

        "Your responsibility is NOT to be polite or emotionally supportive.\n"
        "Your responsibility is to improve the quality of the discussion.\n\n"

        "When you speak, you should aim to do at least one of the following:\n"
        "- Clarify what the conversation is actually about\n"
        "- Point out a hidden problem, assumption, or misalignment\n"
        "- Reframe the situation at a higher, more useful level\n"
        "- Propose a concrete direction or next step\n\n"

        "You are allowed to step back from the last message and judge the situation as a whole.\n"
        "You may ignore emotional or personal details if they do not help move the discussion forward.\n\n"

        "Avoid generic empathy, reassurance, or vague encouragement.\n"
        "Do not repeat or summarize what others have said.\n\n"

        "Be concise, natural, and slightly opinionated.\n"
        "Sound like a thoughtful human, not a system.\n\n"

        "Output MUST be valid JSON only."
    )
    user_msg = f"""
Scene (system context):
{(scene_system or '')[:800]}

Recent conversation (for reference only):
{(scene_user or '')[:800]}

Persona profile (JSON):
{json.dumps(persona_profile or {}, ensure_ascii=False)[:1200]}

Topic (English):
{topic_en or ''}

Latest utterance:
{utterance or ''}

Quality requirements (VERY IMPORTANT):
- You are speaking because staying silent would reduce the quality of the discussion
- Do NOT respond sentence-by-sentence to the last utterance
- Introduce a new perspective, clarification, or direction
- Reduce confusion or stagnation in the conversation
- Prefer concrete guidance over emotional commentary
- If no substantial value can be added, keep the message short and direct

Constraints:
- Return JSON only: {{"strategy":"...","insert":"..."}}
- "strategy": one short phrase describing the intent
- "insert": ONE Chinese sentence
- Do NOT quote, repeat, or paraphrase the user's utterance
- Do NOT include any consecutive 8+ characters copied from the user's utterance
- Do not ask questions
- Do not use '?' or '？'
- Keep insert concise (<= 25 Chinese characters preferred)

Return JSON only:
{{"strategy":"...","insert":"..."}}
""".strip()

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=140,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = _extract_json_block(raw) or {}

    strategy = str(data.get("strategy", "")).strip() or "unspecified"
    insert = str(data.get("insert", "")).strip()

    # ✅ 强制清洗，避免复述用户 utterance
    insert = _sanitize_insert(insert, utterance)

    if not insert:
        insert = "我理解你现在压力很大，我们先把最紧急的一件事拆小一点来处理。"

    return {"strategy": strategy, "insert": insert, "raw": raw}


# ================== 主推理：infer_once ==================
def infer_once(
    persona_profile: dict,
    topic_en: str,
    scene_system: str,
    scene_user: str,
    utterance: str,
) -> dict:
    """
    完全使用 ChatGPT 来判断插入意愿和生成插话内容：
    1) 使用 ChatGPT 判断插入意愿（输入：场景、个人信息、话题、发言、历史）
    2) 如果意愿 > 0.6，调用 ChatGPT 生成插话内容和策略
    3) 使用相同的 prompt 内容进行插话生成
    """
    t0 = _now_ms()
    init_models()
    t_after_init = _now_ms()

    utterance = (utterance or "").strip()
    topic_en = topic_en or ""
    scene_system = scene_system or ""
    history_ctx = (scene_user or "").strip()

    # ===== 使用 ChatGPT 判断插入意愿 =====
    t_willingness0 = _now_ms()
    final_willingness = ask_chatgpt_for_willingness(
        persona_profile=persona_profile,
        topic_en=topic_en,
        utterance=utterance,
        scene_system=scene_system,
        scene_user=history_ctx,
    )
    t_willingness1 = _now_ms()

    # ===== debug inputs =====
    debug_inputs = None
    if EMIT_DEBUG_INPUTS:
        debug_inputs = {
            "persona_profile": json.dumps(persona_profile or {}, ensure_ascii=False)[:DEBUG_INPUT_TRUNC],
            "scene_system": scene_system[:DEBUG_INPUT_TRUNC],
            "topic_en": topic_en[:DEBUG_INPUT_TRUNC],
            "utterance": utterance[:DEBUG_INPUT_TRUNC],
            "history_ctx": history_ctx[:DEBUG_INPUT_TRUNC],
        }

    # ===== only when triggered, call ChatGPT for insert =====
    did_strategy = False
    strategy = "disabled"
    insert_text = ""
    ms_strategy = 0.0

    if final_willingness > THRESHOLD:
        did_strategy = True
        ts0 = _now_ms()
        try:
            res = ask_chatgpt_for_insert_and_strategy(
                persona_profile=persona_profile,
                topic_en=topic_en,
                utterance=utterance,
                scene_system=scene_system,
                scene_user=history_ctx,
            )
            strategy = res.get("strategy", "unspecified")
            insert_text = res.get("insert", "")
        except Exception as e:
            if DEBUG_LOG:
                print("[agent_core] ChatGPT insert generation failed:", repr(e))
            strategy = "fallback"
            insert_text = "我理解你现在很难受，我们先稳住情绪，再把事情按优先级一点点推进。"
        ts1 = _now_ms()
        ms_strategy = ts1 - ts0

    t_end = _now_ms()

    debug_timing = {
        "ms_total": round(t_end - t0, 2),
        "ms_init_models": round(t_after_init - t0, 2),
        "ms_willingness": round(t_willingness1 - t_willingness0, 2),
        "triggered_strategy": did_strategy,
        "ms_strategy": round(ms_strategy, 2),
        "model": OPENAI_MODEL,
    }

    return {
        "type": "agent_utterance",
        "final_willingness": float(final_willingness),
        "threshold": THRESHOLD,
        "topic_en": topic_en,
        "strategy": strategy,
        "text": insert_text if did_strategy else "",
        "sub_scores": {
            "persona": 0.0,  # 不再使用，保留兼容性
            "scene": 0.0,    # 不再使用，保留兼容性
            "topic": 0.0,    # 不再使用，保留兼容性
        },
        "debug_timing": debug_timing,
        "debug_inputs": debug_inputs,
    }
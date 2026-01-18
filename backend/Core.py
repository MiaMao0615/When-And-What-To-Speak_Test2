# Core.py
# -*- coding: utf-8 -*-

"""
✅ 与 Connection2Unity1203.py 的 LoRA 调用方式完全一致（关键点）：
- tokenizer = AutoTokenizer.from_pretrained
- base_model = AutoModelForSequenceClassification(num_labels=1, fp16)
- reg_model = PeftModel.from_pretrained(base_model, PERSONA_LORA, adapter_name="persona")
- reg_model.load_adapter(scene/topic)
- willingness 推理：logits.squeeze(-1).item() -> clamp 到 [0,1]（不做 sigmoid）

本文件额外提供：
- build_scene_prompt_from_fields：给 Websocket 的 scene_fields 消息用（不会影响 LoRA 计算）
- infer_once：跑 persona/scene/topic 三路 willingness，final>THRESHOLD 时调用 ChatGPT 给 strategy + insert（不加载第二个 7B）
- debug_inputs 回传给前端（方便你在 UI 里看三路 LoRA 实际吃到的文本）
"""

import json
import time
import re
import torch

from transformers import AutoTokenizer, AutoModelForSequenceClassification
from peft import PeftModel
from openai import OpenAI

# ================== 路径配置（按你项目实际路径） ==================
BASE_MODEL = r"D:\LLM\Qwen2.5-7B-Instruct"

PERSONA_LORA = r"D:\Task_design\personality\FinTune\outputs\qwen7b-lora-persona-will_full\checkpoint-32899"
SCENE_LORA   = r"D:\Task_design\Scene\outputs\qwen7b-lora-will_half_fp16_v2\checkpoint-35821"
TOPIC_LORA   = r"D:\Task_design\Topic\willingness_train\outputs\qwen7b-lora-topic_willingness\checkpoint-2500"

MAX_LENGTH = 256
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
THRESHOLD = 0.60

# ChatGPT 侧模型
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"
client = OpenAI()

# ===== Debug 控制 =====
DEBUG_LOG = False          # True 才打印控制台日志
EMIT_DEBUG_INPUTS = True   # True 才把 debug_inputs 发给前端
DEBUG_INPUT_TRUNC = 1200

SCENE_WILLINGNESS_SUFFIX = (
    "在上述场景中，AI 助手主动插话的“意愿”应该是多少？"
    "请给出一个 0 到 1 之间的小数（例如 0.23），只输出数字即可。"
)

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


# ================== 模型（只加载一次） ==================
tokenizer = None
reg_model = None  # PeftModel with adapters: persona/scene/topic

def _now_ms() -> float:
    return time.perf_counter() * 1000.0

def init_models():
    """
    ✅ 与 Connection2Unity1203.py 完全一致的加载流程。
    """
    global tokenizer, reg_model
    if tokenizer is not None and reg_model is not None:
        return

    if DEBUG_LOG:
        print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if DEBUG_LOG:
        print("Loading base regression model...")
    base_model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=1,
        torch_dtype=torch.float16 if DEVICE.type == "cuda" else torch.float32,
    )
    base_model.config.pad_token_id = tokenizer.pad_token_id

    if DEBUG_LOG:
        print("Loading persona LoRA...")
    reg_model = PeftModel.from_pretrained(
        base_model,
        PERSONA_LORA,
        adapter_name="persona",
    )

    if DEBUG_LOG:
        print("Loading scene LoRA...")
    reg_model.load_adapter(
        SCENE_LORA,
        adapter_name="scene",
    )

    if DEBUG_LOG:
        print("Loading topic LoRA...")
    reg_model.load_adapter(
        TOPIC_LORA,
        adapter_name="topic",
    )

    reg_model.to(DEVICE)
    reg_model.eval()

    if DEVICE.type == "cuda":
        assert next(reg_model.parameters()).is_cuda, "[device_check] reg_model not on CUDA"

    if DEBUG_LOG:
        print("Regression model with 3 LoRA heads loaded on:", DEVICE)

@torch.inference_mode()
def _encode(text: str) -> dict:
    enc = tokenizer(
        text,
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=MAX_LENGTH,
    )
    enc = {k: v.to(DEVICE) for k, v in enc.items()}
    if DEVICE.type == "cuda":
        assert enc["input_ids"].is_cuda and enc["attention_mask"].is_cuda, "[device_check] inputs not on CUDA"
    return enc

@torch.inference_mode()
def _run_willingness(adapter_name: str, text: str) -> float:
    """
    ✅ 与 Connection2Unity1203.py 的 run_willingness_with_logs 对齐：
    logits = reg_model(**enc).logits.squeeze(-1).item()
    val = clamp(logits, 0, 1)
    
    修复：使用sigmoid激活，避免极端值（0/1摇摆）
    """
    text = (text or "").strip()
    if not text:
        return 0.0

    reg_model.set_adapter(adapter_name)
    enc = _encode(text)

    logits = reg_model(**enc).logits.squeeze(-1).item()
    
    # 修复：使用sigmoid将logits映射到(0,1)，避免极端值
    # 这样可以将任意范围的logits平滑映射到(0,1)区间
    logits_tensor = torch.tensor(logits)
    val = torch.sigmoid(logits_tensor).item()
    
    # 确保在[0,1]范围内（sigmoid已经保证，但加上更安全）
    val = max(0.0, min(1.0, val))
    
    if DEBUG_LOG:
        print(f"[{adapter_name}] logits={logits:.4f} -> sigmoid={val:.4f}")
    
    return val


# ================== 输入拼接（对齐 Connection2Unity1203.py） ==================
def build_persona_text(persona_raw: str, profile_json, utterance: str) -> str:
    persona_raw = (persona_raw or "").strip()
    utterance = (utterance or "").strip()

    profile = ""
    if isinstance(profile_json, dict):
        profile = json.dumps(profile_json, ensure_ascii=False)
    else:
        profile = (str(profile_json or "")).strip()
        try:
            profile_obj = json.loads(profile)
            profile = json.dumps(profile_obj, ensure_ascii=False)
        except Exception:
            pass

    parts = []
    if persona_raw:
        parts.append(f"[PERSONA_RAW] {persona_raw}")
    if profile:
        parts.append(f"[PROFILE] {profile}")
    if utterance:
        parts.append(f"[UTTERANCE] {utterance}")
    return "\n\n".join(parts)

def build_scene_text(scene_system: str, scene_user: str) -> str:
    sys = (scene_system or "").strip()
    usr = (scene_user or "").strip()

    # ✅ 确保 suffix 一定存在（且不会重复）
    if sys and SCENE_WILLINGNESS_SUFFIX not in sys:
        sys = sys + "\n\n" + SCENE_WILLINGNESS_SUFFIX

    if usr:
        return sys + "\n\n" + usr
    else:
        return sys

def build_topic_text(topic_en: str, utterance: str) -> str:
    """
    构建topic输入文本，格式与训练时完全一致。
    注意：topic_en应该足够详细（类似训练数据），否则模型可能无法准确判断。
    """
    topic_en = (topic_en or "").strip()
    utterance = (utterance or "").strip()
    
    # 如果topic太短，提示需要更详细的描述（但不自动增强，保持格式一致性）
    if topic_en and len(topic_en) < 30:
        if DEBUG_LOG:
            print(f"[WARN] Topic描述较短 ({len(topic_en)} chars)，建议提供更详细的上下文描述")
    
    parts = []
    if topic_en:
        parts.append(f"[TOPIC_EN] {topic_en}")
    if utterance:
        parts.append(f"[UTTERANCE] {utterance}")
    return "\n\n".join(parts)


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
    ✅ 关键行为（按你的要求）：
    1) 三路 LoRA willingness 计算时：只使用“固定场景 scene_system”，不引入对话历史
       - scene 头输入：scene_system + 固定问句（suffix）
       - persona/topic 头也不拼 history，只用当前 utterance + persona/topic
    2) 只有当 final > THRESHOLD 需要 agent 响应时，才把对话历史 scene_user 传给 ChatGPT 作为参考
       （history 不会影响 LoRA willingness）
    """
    t0 = _now_ms()
    init_models()
    t_after_init = _now_ms()

    utterance = (utterance or "").strip()
    topic_en = topic_en or ""
    scene_system = scene_system or ""
    history_ctx = (scene_user or "").strip()  # ✅ 仅供 ChatGPT 参考，不参与 LoRA 评分

    # ===== build inputs (LoRA heads) =====
    t_build0 = _now_ms()

    persona_text = build_persona_text("", persona_profile, utterance)

    # ✅ scene 头：不吃历史
    scene_text_for_heads = build_scene_text(scene_system, "")

    # ✅ topic 头：不吃历史（只看 topic + 当前 utterance）
    topic_text = build_topic_text(topic_en, utterance)

    t_build1 = _now_ms()

    # ===== debug inputs =====
    debug_inputs = None
    if EMIT_DEBUG_INPUTS:
        debug_inputs = {
            "persona_text": persona_text[:DEBUG_INPUT_TRUNC],
            "scene_text": scene_text_for_heads[:DEBUG_INPUT_TRUNC],   # ✅ 固定不变（除非你手动更新 scene_fields）
            "topic_text": topic_text[:DEBUG_INPUT_TRUNC],
            "history_ctx": history_ctx[:DEBUG_INPUT_TRUNC],           # ✅ 仅展示，不进 heads
        }

    # ===== persona / scene / topic =====
    t_p0 = _now_ms()
    p_val = _run_willingness("persona", persona_text)
    t_p1 = _now_ms()

    t_s0 = _now_ms()
    s_val = _run_willingness("scene", scene_text_for_heads)
    t_s1 = _now_ms()

    t_t0 = _now_ms()
    t_val = _run_willingness("topic", topic_text)
    t_t1 = _now_ms()

    final = (p_val + s_val + t_val) / 3.0

    # ===== only when triggered, call ChatGPT with history =====
    did_strategy = False
    strategy = "update"
    insert_text = ""
    ms_strategy = 0.0

    if final > THRESHOLD:
        did_strategy = True
        ts0 = _now_ms()
        try:
            res = ask_chatgpt_for_insert_and_strategy(
                persona_profile=persona_profile,
                topic_en=topic_en,
                utterance=utterance,
                scene_system=scene_system,
                scene_user=history_ctx,  # ✅ 仅此处传历史
            )
            strategy = res.get("strategy", "unspecified")
            insert_text = res.get("insert", "")
        except Exception as e:
            if DEBUG_LOG:
                print("[agent_core] ChatGPT failed:", repr(e))
            strategy = "fallback"
            insert_text = "我理解你现在很难受，我们先稳住情绪，再把事情按优先级一点点推进。"
        ts1 = _now_ms()
        ms_strategy = ts1 - ts0

    t_end = _now_ms()

    debug_timing = {
        "ms_total": round(t_end - t0, 2),
        "ms_init_models": round(t_after_init - t0, 2),
        "ms_build_inputs": round(t_build1 - t_build0, 2),
        "ms_persona": round(t_p1 - t_p0, 2),
        "ms_scene": round(t_s1 - t_s0, 2),
        "ms_topic": round(t_t1 - t_t0, 2),
        "triggered_strategy": did_strategy,
        "ms_strategy": round(ms_strategy, 2),
        "device_reg": str(DEVICE),
        "max_length": MAX_LENGTH,
    }

    return {
        "type": "agent_utterance",
        "final_willingness": float(final),
        "threshold": THRESHOLD,
        "topic_en": topic_en,
        "strategy": strategy if did_strategy else "disabled",
        "text": insert_text if did_strategy else "",
        "sub_scores": {
            "persona": float(p_val),
            "scene": float(s_val),
            "topic": float(t_val),
        },
        "debug_timing": debug_timing,
        "debug_inputs": debug_inputs,
    }
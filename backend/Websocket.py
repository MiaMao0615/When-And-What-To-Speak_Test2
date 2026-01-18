# Websocket.py
# -*- coding: utf-8 -*-

"""
公共房间多人版本（无 room_id）：
- 多客户端加入同一房间
- 必须先 join（nickname + intro），否则不允许发言
- 每个用户独立 persona_profile（不共享）
- chat_line：先广播 chat_ack(queued)，再串行推理，最后广播 chat_update(done)
- 推理上下文：最近 N 句历史拼成 scene_user
- 多人并发不抢 GPU：asyncio.Queue + 单 worker 串行 infer_once()
"""

import json
import time
import uuid
import asyncio
import websockets
import csv
import os
from datetime import datetime

from Core import infer_once, build_scene_prompt_from_fields, init_models

# ========= 参数 =========
WS_LOG = True            # 服务端日志（建议 True，便于你看到 join / enqueue / done）
HISTORY_N = 12           # 最近 N 句作为上下文
MAX_HISTORY = 100        # 历史最多保留
GPU_QUEUE_MAX = 300      # 推理队列上限（并发多时先排队）

# ========= 单公共房间状态 =========
STATE = {
    "topic_en": "",
    "scene_system": "",
    "scene_user": "",
    "scene_fields": {},
    "experiment_ended": False,  # 实验是否已结束
    "end_time": None,  # 实验结束时间
    "start_time": int(time.time()),  # 实验开始时间
    "questionnaire_started": False,  # 问卷是否已开始
    "questionnaire_completed": False,  # 问卷是否已全部完成
}

# 问卷相关
QUESTIONNAIRE_ANSWERS = {}  # user_id -> {target_number: score} 每个用户对其他用户的评分
QUESTIONNAIRE_COMPLETED = set()  # 已完成问卷的用户ID集合
PARTICIPANT_NUMBERS = {}  # user_id -> display_number 所有参与者的编号映射

USERS = {}        # user_id -> {"nickname": str, "persona_profile": dict}
CONN2UID = {}     # websocket -> user_id
CONNS = set()     # all connections

HISTORY = []      # [{seq,user_id,nickname,text,ts}]
AGENT_RESPONSES = []  # [{seq,final_willingness,triggered,strategy,text,ts}] - 记录Agent响应

SEQ = 0
SEQ_LOCK = asyncio.Lock()

# ========= 实验日志 CSV =========
LOG_DIR = "experiment_logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_CSV = None  # 当前实验的CSV文件路径（根据房间ID动态生成）
CURRENT_ROOM_ID = None  # 当前实验的房间ID
LOG_FILE_LOCK = asyncio.Lock()
USER_NUMBER_MAP = {}  # user_id -> display_number (前端传来的编号)
AGENT_NUMBER_MAP = {}  # seq -> agent_number (记录Agent编号，通过seq关联)

# 初始化CSV文件（写入表头）
def init_csv_log(room_id: str = None):
    """初始化CSV日志文件，写入表头（包含房间ID和LoRA子分数）"""
    global LOG_CSV, CURRENT_ROOM_ID
    
    if not room_id:
        room_id = f"room_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    CURRENT_ROOM_ID = room_id
    # CSV文件名包含房间ID
    LOG_CSV = os.path.join(LOG_DIR, f"lora_experiment_{room_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    
    try:
        with open(LOG_CSV, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            # 表头第一列是房间ID
            writer.writerow([
                '房间ID', '时间戳', '序号', '发言者类型', '编号', '用户ID', '说话内容',
                '最终Willingness', 'Persona分数', 'Scene分数', 'Topic分数',
                '是否触发插话', 'Agent策略', 'Agent插话内容', 'Agent编号'
            ])
            # 写入房间ID信息行
            writer.writerow([
                room_id,  # 房间ID
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "ROOM_INFO",
                '房间信息',
                "",
                "system",
                f"实验房间ID: {room_id}",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ])
        if WS_LOG:
            print(f"[log] CSV日志文件已创建: {LOG_CSV} (房间ID: {room_id})")
    except Exception as e:
        print(f"[log] 创建CSV文件失败: {repr(e)}")

async def write_csv_log(row_data: list):
    """异步写入CSV日志（自动添加房间ID）"""
    async with LOG_FILE_LOCK:
        try:
            if LOG_CSV and os.path.exists(LOG_CSV):
                # 在行数据前添加房间ID
                row_with_room = [CURRENT_ROOM_ID or ""] + row_data
                with open(LOG_CSV, 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(row_with_room)
        except Exception as e:
            if WS_LOG:
                print(f"[log] 写入CSV失败: {repr(e)}")

# 注意：不再自动初始化CSV，等收到房间ID后再初始化

# ========= GPU 串行队列 =========
GPU_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=GPU_QUEUE_MAX)

async def gpu_worker():
    if WS_LOG:
        print("[gpu_worker] started")
    while True:
        job = await GPU_QUEUE.get()
        fut = job["future"]
        try:
            if WS_LOG:
                print(f"[gpu_worker] run seq={job.get('seq')}")
            result = infer_once(
                persona_profile=job["persona_profile"],
                topic_en=job["topic_en"],
                scene_system=job["scene_system"],
                scene_user=job["scene_user"],
                utterance=job["utterance"],
            )
            if not fut.cancelled():
                fut.set_result(result)
        except Exception as e:
            if not fut.cancelled():
                fut.set_exception(e)
        finally:
            GPU_QUEUE.task_done()

async def submit_infer_job(job: dict) -> dict:
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    job["future"] = fut
    try:
        GPU_QUEUE.put_nowait(job)
        if WS_LOG:
            print(f"[queue] enqueue seq={job.get('seq')} qsize={GPU_QUEUE.qsize()}")
    except asyncio.QueueFull:
        if WS_LOG:
            print("[queue] FULL -> drop")
        return {
            "type": "agent_utterance",
            "final_willingness": 0.0,
            "threshold": 0.60,
            "topic_en": job.get("topic_en", ""),
            "strategy": "disabled",
            "text": "",
            "sub_scores": {"persona": 0.0, "scene": 0.0, "topic": 0.0},
            "debug_timing": {"error": "gpu_queue_full"},
            "debug_inputs": None,
        }
    return await fut

# ========= 工具 =========
async def _safe_send(ws, payload: dict):
    try:
        await ws.send(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        if WS_LOG:
            print("[send] failed:", repr(e))

async def _broadcast(payload: dict):
    msg = json.dumps(payload, ensure_ascii=False)
    dead = []
    for ws in list(CONNS):
        try:
            await ws.send(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CONNS.discard(ws)
        CONN2UID.pop(ws, None)

def _build_state_payload() -> dict:
    return {
        "type": "state_update",
        "topic_en": STATE["topic_en"],
        "scene_system": STATE["scene_system"],
        "scene_user": STATE["scene_user"],
        "scene_fields": STATE["scene_fields"],
        "experiment_ended": STATE.get("experiment_ended", False),
    }

# ========= 实验统计功能 =========
def generate_experiment_statistics() -> dict:
    """生成实验统计数据（LoRA系统版本）"""
    try:
        stats = {
            "total_users": len(USERS),
            "total_messages": len(HISTORY),
            "agent_responses": 0,
            "agent_trigger_rate": 0.0,
            "average_willingness": 0.0,
            "average_persona_score": 0.0,
            "average_scene_score": 0.0,
            "average_topic_score": 0.0,
            "experiment_duration": None,
        }
        
        # 计算实验持续时间
        if STATE.get("end_time") and STATE.get("start_time"):
            duration_seconds = STATE["end_time"] - STATE["start_time"]
            duration_minutes = duration_seconds / 60
            stats["experiment_duration"] = f"{duration_minutes:.1f}分钟"
        
        # 统计Agent响应次数和意愿分数
        if AGENT_RESPONSES:
            triggered_count = sum(1 for r in AGENT_RESPONSES if r.get("triggered", False))
            stats["agent_responses"] = triggered_count
            
            # 计算平均意愿分数（所有响应的final_willingness）
            all_willingness = [r.get("final_willingness", 0.0) for r in AGENT_RESPONSES if r.get("final_willingness") is not None]
            if all_willingness:
                stats["average_willingness"] = sum(all_willingness) / len(all_willingness)
            
            # 计算触发率（触发次数 / 总评估次数）
            if len(AGENT_RESPONSES) > 0:
                stats["agent_trigger_rate"] = triggered_count / len(AGENT_RESPONSES)
            
            # 计算子分数平均值（persona/scene/topic）
            persona_scores = []
            scene_scores = []
            topic_scores = []
            for r in AGENT_RESPONSES:
                sub_scores = r.get("sub_scores", {})
                if sub_scores.get("persona") is not None:
                    persona_scores.append(sub_scores["persona"])
                if sub_scores.get("scene") is not None:
                    scene_scores.append(sub_scores["scene"])
                if sub_scores.get("topic") is not None:
                    topic_scores.append(sub_scores["topic"])
            
            if persona_scores:
                stats["average_persona_score"] = sum(persona_scores) / len(persona_scores)
            if scene_scores:
                stats["average_scene_score"] = sum(scene_scores) / len(scene_scores)
            if topic_scores:
                stats["average_topic_score"] = sum(topic_scores) / len(topic_scores)
        
        return stats
    except Exception as e:
        if WS_LOG:
            print(f"[stats] 生成统计失败: {repr(e)}")
        return {}

def _online_users():
    return [{"user_id": uid, "nickname": u["nickname"]} for uid, u in USERS.items()]

def _format_history(n: int) -> str:
    if not HISTORY:
        return ""
    tail = HISTORY[-n:]
    lines = ["[HISTORY]"]
    for it in tail:
        lines.append(f'{it.get("nickname","anon")}: {it.get("text","")}')
    return "\n".join(lines)

# ========= handler =========
async def handler(ws):
    # 声明全局变量（需要在函数开始处声明，不能在中间声明）
    global PARTICIPANT_NUMBERS, QUESTIONNAIRE_ANSWERS, QUESTIONNAIRE_COMPLETED
    
    peer = getattr(ws, "remote_address", None)
    CONNS.add(ws)
    if WS_LOG:
        print("[conn] client connected:", peer)

    await _safe_send(ws, {"type": "status", "connected": True})
    await _safe_send(ws, _build_state_payload())
    # 如果实验已结束，发送结束状态
    if STATE.get("experiment_ended"):
        if STATE.get("questionnaire_completed"):
            # 问卷已完成，发送统计结果
            stats = generate_experiment_statistics()
            await _safe_send(ws, {
                "type": "experiment_ended",
                "end_time": STATE.get("end_time"),
                "room_id": CURRENT_ROOM_ID or "",
                "stats": stats,
                "csv_file": LOG_CSV,
            })
        elif STATE.get("questionnaire_started"):
            # 问卷进行中，发送问卷状态
            participants = []
            for uid, number in PARTICIPANT_NUMBERS.items():
                participants.append({
                    "user_id": uid,
                    "number": number,
                    "nickname": USERS[uid]["nickname"]
                })
            await _safe_send(ws, {
                "type": "experiment_ended",
                "end_time": STATE.get("end_time"),
                "room_id": CURRENT_ROOM_ID or "",
                "questionnaire_started": True,
                "participants": participants,
                "stats": None,
                "csv_file": None,
            })

    try:
        async for message in ws:
            if WS_LOG:
                print("[recv]", message)

            try:
                data = json.loads(message)
            except Exception:
                await _safe_send(ws, {"type": "error", "msg": "invalid json"})
                continue

            dtype = data.get("type", "")

            # ===== join：必须 nickname + intro =====
            if dtype == "join":
                nickname = (data.get("nickname") or "").strip()
                intro = (data.get("intro") or "").strip()
                if not nickname or not intro:
                    await _safe_send(ws, {"type": "join_fail", "msg": "nickname 和 intro 必填"})
                    continue

                uid = "u_" + uuid.uuid4().hex[:8]
                CONN2UID[ws] = uid

                persona_profile = {
                    "background": intro,
                    "personality_traits": data.get("personality_traits", []),
                    "speaking_style": data.get("speaking_style", ""),
                    "values": data.get("values", ""),
                }
                USERS[uid] = {"nickname": nickname, "persona_profile": persona_profile}

                if WS_LOG:
                    print(f"[join] ok uid={uid} nickname={nickname}")

                await _safe_send(ws, {"type": "join_ok", "user_id": uid, "nickname": nickname})
                await _broadcast({
                    "type": "presence",
                    "event": "join",
                    "user": {"user_id": uid, "nickname": nickname},
                    "online": _online_users(),
                    "ts": int(time.time()),
                })
                continue

            # join 后才能继续
            uid = CONN2UID.get(ws)
            if not uid:
                await _safe_send(ws, {"type": "error", "msg": "请先 join（nickname+intro）"})
                continue

            # ===== 公共状态：topic/scene =====
            if dtype == "topic":
                STATE["topic_en"] = data.get("topic", "") or ""
                await _broadcast(_build_state_payload())
                continue

            if dtype == "scene_prompt":
                STATE["scene_system"] = data.get("prompt", "") or ""
                STATE["scene_user"] = ""
                STATE["scene_fields"] = {}
                await _broadcast(_build_state_payload())
                continue

            if dtype == "scene_fields":
                fields = data.get("fields", {}) or {}
                if not isinstance(fields, dict):
                    fields = {}
                STATE["scene_fields"] = fields
                STATE["scene_system"] = build_scene_prompt_from_fields(fields)
                STATE["scene_user"] = ""
                await _broadcast(_build_state_payload())
                continue

            # ===== 更新自己的 persona（可选）=====
            if dtype == "persona_profile":
                persona = {
                    "background": data.get("background", USERS[uid]["persona_profile"].get("background", "")),
                    "personality_traits": data.get("personality_traits", USERS[uid]["persona_profile"].get("personality_traits", [])),
                    "speaking_style": data.get("speaking_style", USERS[uid]["persona_profile"].get("speaking_style", "")),
                    "values": data.get("values", USERS[uid]["persona_profile"].get("values", "")),
                }
                USERS[uid]["persona_profile"] = persona
                await _broadcast({
                    "type": "presence",
                    "event": "persona_updated",
                    "user": {"user_id": uid, "nickname": USERS[uid]["nickname"]},
                    "ts": int(time.time()),
                })
                continue

            # ===== 记录用户编号（前端发送）=====
            if dtype == "user_number":
                user_num = data.get("user_number")
                user_id_from_data = data.get("user_id")
                if user_num and user_id_from_data:
                    # 更新用户编号映射（用于问卷阶段）
                    USER_NUMBER_MAP[user_id_from_data] = user_num
                    if WS_LOG:
                        print(f"[log] 用户编号已记录: user_id={user_id_from_data} number={user_num}")
                continue

            # ===== 记录Agent编号（前端发送）=====
            if dtype == "agent_number":
                agent_num = data.get("agent_number")
                agent_seq = data.get("seq")
                if agent_num and agent_seq:
                    # 保存Agent编号映射
                    AGENT_NUMBER_MAP[agent_seq] = agent_num
                    # 记录Agent编号信息到CSV
                    await write_csv_log([
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        f"{agent_seq}-agent-number",
                        'Agent编号',
                        str(agent_num),
                        "agent",
                        f"Agent编号: {agent_num} (对应消息seq: {agent_seq})",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        str(agent_num),
                    ])
                    if WS_LOG:
                        print(f"[log] Agent编号已记录: seq={agent_seq} number={agent_num}")
                continue

            # ===== 结束实验（主持人操作，需要提供房间ID）=====
            if dtype == "end_experiment":
                if STATE["experiment_ended"]:
                    await _safe_send(ws, {"type": "error", "msg": "实验已经结束，请先重置实验"})
                    continue
                
                # 获取房间ID（必填）
                room_id = (data.get("room_id") or "").strip()
                if not room_id:
                    await _safe_send(ws, {"type": "error", "msg": "请提供房间ID"})
                    continue
                
                # 初始化CSV文件（使用房间ID）
                init_csv_log(room_id)
                
                STATE["experiment_ended"] = True
                STATE["end_time"] = int(time.time())
                
                # 收集所有参与者的编号映射
                PARTICIPANT_NUMBERS = {}
                for uid, user_info in USERS.items():
                    if uid in USER_NUMBER_MAP:
                        PARTICIPANT_NUMBERS[uid] = USER_NUMBER_MAP[uid]
                    else:
                        # 如果没有编号，使用默认值
                        PARTICIPANT_NUMBERS[uid] = "未知"
                
                # 记录实验结束到CSV
                await write_csv_log([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "EXPERIMENT_END",
                    '实验结束',
                    "",
                    "system",
                    f"实验已结束 (房间ID: {room_id})",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ])
                
                # 初始化问卷状态（不显示结果，先显示问卷）
                STATE["questionnaire_started"] = True
                QUESTIONNAIRE_ANSWERS = {}
                QUESTIONNAIRE_COMPLETED = set()
                
                if WS_LOG:
                    print(f"[experiment] 实验已结束，开始问卷阶段")
                    print(f"[questionnaire] 参与者编号: {PARTICIPANT_NUMBERS}")
                
                # 构建参与者列表（包含编号）
                participants = []
                for uid, number in PARTICIPANT_NUMBERS.items():
                    participants.append({
                        "user_id": uid,
                        "number": number,
                        "nickname": USERS[uid]["nickname"]
                    })
                
                # 广播实验结束消息，进入问卷阶段（不显示统计结果）
                await _broadcast({
                    "type": "experiment_ended",
                    "end_time": STATE["end_time"],
                    "questionnaire_started": True,
                    "participants": participants,  # 发送所有参与者列表
                    "stats": None,  # 不发送统计结果，等问卷完成后再发送
                    "csv_file": None,  # 不发送CSV路径，等问卷完成后再发送
                })
                continue

            # ===== 提交问卷答案 =====
            if dtype == "submit_questionnaire":
                if not STATE.get("questionnaire_started"):
                    await _safe_send(ws, {"type": "error", "msg": "问卷尚未开始"})
                    continue
                
                if uid in QUESTIONNAIRE_COMPLETED:
                    await _safe_send(ws, {"type": "error", "msg": "你已经提交过问卷"})
                    continue
                
                # 获取用户的问卷答案 {target_number: score}
                answers = data.get("answers", {})
                if not isinstance(answers, dict):
                    answers = {}
                
                # 验证答案格式：应该是 {number: score}，score 在 1-10 之间
                validated_answers = {}
                for target_number, score in answers.items():
                    try:
                        score_num = float(score)
                        if 1 <= score_num <= 10:
                            validated_answers[str(target_number)] = score_num
                    except:
                        pass
                
                # 保存问卷答案
                QUESTIONNAIRE_ANSWERS[uid] = validated_answers
                QUESTIONNAIRE_COMPLETED.add(uid)
                
                if WS_LOG:
                    print(f"[questionnaire] 用户 {uid} 提交问卷: {validated_answers}")
                    print(f"[questionnaire] 完成进度: {len(QUESTIONNAIRE_COMPLETED)}/{len(USERS)}")
                
                # 检查是否所有用户都已完成问卷
                all_users_completed = len(QUESTIONNAIRE_COMPLETED) >= len(USERS)
                
                if all_users_completed:
                    # 所有用户完成，生成统计并显示结果
                    STATE["questionnaire_completed"] = True
                    stats = generate_experiment_statistics()
                    
                    # 记录问卷答案到CSV（在实验结束记录之后）
                    for user_id, answers_dict in QUESTIONNAIRE_ANSWERS.items():
                        user_number = PARTICIPANT_NUMBERS.get(user_id, "未知")
                        for target_number, score in answers_dict.items():
                            await write_csv_log([
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                f"QUESTIONNAIRE-{user_id}",
                                '问卷答案',
                                str(user_number),
                                user_id,
                                f"对编号#{target_number}的Agent评分: {score}/10",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                            ])
                    
                    if WS_LOG:
                        print(f"[questionnaire] 所有用户已完成问卷")
                        print(f"[questionnaire] 问卷答案: {QUESTIONNAIRE_ANSWERS}")
                        print(f"[experiment] 统计数据: {stats}")
                        print(f"[log] CSV日志已保存到: {LOG_CSV}")
                    
                    # 广播问卷完成，显示统计结果
                    await _broadcast({
                        "type": "questionnaire_completed",
                        "room_id": CURRENT_ROOM_ID or "",
                        "stats": stats,
                        "csv_file": LOG_CSV,
                        "questionnaire_answers": QUESTIONNAIRE_ANSWERS,  # 问卷答案（可选，用于前端显示）
                    })
                else:
                    # 部分用户完成，告知所有用户进度
                    remaining_count = len(USERS) - len(QUESTIONNAIRE_COMPLETED)
                    await _broadcast({
                        "type": "questionnaire_progress",
                        "completed_count": len(QUESTIONNAIRE_COMPLETED),
                        "total_count": len(USERS),
                        "remaining_count": remaining_count,
                    })
                    
                    # 告知提交用户成功
                    await _safe_send(ws, {
                        "type": "questionnaire_submitted",
                        "remaining_count": remaining_count,
                    })
                continue

            # ===== 发言：先 ack，再推理，再 update =====
            if dtype == "chat_line":
                # 检查实验是否已结束
                if STATE["experiment_ended"]:
                    await _safe_send(ws, {"type": "error", "msg": "实验已结束，无法继续发言"})
                    continue
                    
                text = (data.get("text", "") or "").strip()
                if not text:
                    continue

                nickname = USERS[uid]["nickname"]
                user_number = data.get("user_number") or USER_NUMBER_MAP.get(uid, "未知")

                # 更新用户编号映射
                if data.get("user_number"):
                    USER_NUMBER_MAP[uid] = data.get("user_number")

                global SEQ
                async with SEQ_LOCK:
                    SEQ += 1
                    seq = SEQ

                if WS_LOG:
                    print(f"[chat] seq={seq} from={nickname} (编号:{user_number}): {text}")

                # 写入历史（用于后续 history_ctx）
                HISTORY.append({"seq": seq, "user_id": uid, "nickname": nickname, "text": text, "ts": int(time.time())})
                if len(HISTORY) > MAX_HISTORY:
                    del HISTORY[:-MAX_HISTORY]

                # 先广播 ack：UI 立即显示（queued）
                await _broadcast({
                    "type": "chat_ack",
                    "seq": seq,
                    "user": {"user_id": uid, "nickname": nickname},
                    "text": text,
                    "ts": int(time.time()),
                    "status": "queued",
                    "queue_size": GPU_QUEUE.qsize(),
                })

                history_ctx = _format_history(HISTORY_N)
                persona_profile = USERS[uid]["persona_profile"]

                # 串行推理（不会抢 GPU）
                try:
                    agent_payload = await submit_infer_job({
                        "seq": seq,
                        "persona_profile": persona_profile,
                        "topic_en": STATE["topic_en"],
                        "scene_system": STATE["scene_system"],
                        "scene_user": history_ctx,
                        "utterance": text,
                    })
                except Exception as e:
                    agent_payload = {
                        "type": "agent_utterance",
                        "final_willingness": 0.0,
                        "threshold": 0.60,
                        "topic_en": STATE["topic_en"],
                        "strategy": "disabled",
                        "text": "",
                        "sub_scores": {"persona": 0.0, "scene": 0.0, "topic": 0.0},
                        "debug_timing": {"error": repr(e)},
                        "debug_inputs": None,
                    }

                final_willingness = agent_payload.get("final_willingness", 0.0)
                did_trigger = final_willingness > agent_payload.get("threshold", 0.6)
                
                # 获取LoRA子分数
                sub_scores = agent_payload.get("sub_scores", {})
                persona_score = sub_scores.get("persona", 0.0)
                scene_score = sub_scores.get("scene", 0.0)
                topic_score = sub_scores.get("topic", 0.0)
                agent_strategy = agent_payload.get("strategy", "disabled")
                agent_text = agent_payload.get("text", "")
                
                if WS_LOG:
                    print(f"[done] seq={seq} final={final_willingness} triggered={did_trigger}")
                    print(f"[lora_scores] persona={persona_score:.4f} scene={scene_score:.4f} topic={topic_score:.4f}")

                # 记录Agent响应到统计列表
                AGENT_RESPONSES.append({
                    "seq": seq,
                    "final_willingness": final_willingness,
                    "triggered": did_trigger,
                    "strategy": agent_strategy,
                    "text": agent_text,
                    "sub_scores": sub_scores,
                    "ts": int(time.time()),
                })
                
                # 只保留最近N条Agent响应记录（避免内存溢出）
                MAX_AGENT_RESPONSES = 1000
                if len(AGENT_RESPONSES) > MAX_AGENT_RESPONSES:
                    AGENT_RESPONSES[:] = AGENT_RESPONSES[-MAX_AGENT_RESPONSES:]

                # 记录用户消息到CSV（包含LoRA子分数）
                await write_csv_log([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    seq,
                    '用户',
                    str(user_number),
                    uid,
                    text,
                    f"{final_willingness:.4f}",  # 最终Willingness
                    f"{persona_score:.4f}",  # Persona分数
                    f"{scene_score:.4f}",  # Scene分数
                    f"{topic_score:.4f}",  # Topic分数
                    "是" if did_trigger else "否",  # 是否触发插话
                    agent_strategy if did_trigger else "",  # Agent策略
                    agent_text if did_trigger else "",  # Agent插话内容
                    "",  # Agent编号（待前端补充）
                ])

                # 推理完成：广播 update（用 seq 对齐 ack）
                await _broadcast({
                    "type": "chat_update",
                    "seq": seq,
                    "agent": agent_payload,
                    "status": "done",
                    "ts": int(time.time()),
                })

                # 如果Agent有插话，记录Agent消息到CSV
                # Agent编号可能会稍后由前端通过 agent_number 消息补充
                agent_number = AGENT_NUMBER_MAP.get(seq, "")
                if did_trigger and agent_text:
                    await write_csv_log([
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        f"{seq}-agent",
                        'Agent',
                        str(agent_number) if agent_number else "",  # Agent编号
                        "agent",
                        agent_text,
                        f"{final_willingness:.4f}",  # 最终Willingness
                        f"{persona_score:.4f}",  # Persona分数
                        f"{scene_score:.4f}",  # Scene分数
                        f"{topic_score:.4f}",  # Topic分数
                        "是",
                        agent_strategy,
                        agent_text,
                        str(agent_number) if agent_number else "",  # Agent编号
                    ])
                continue

            # 兜底：回显
            await _safe_send(ws, {"type": "debug", "received": data})

    except Exception as e:
        if WS_LOG:
            print("[handler] error:", repr(e))
    finally:
        CONNS.discard(ws)
        uid = CONN2UID.pop(ws, None)
        if uid and uid in USERS:
            if WS_LOG:
                print(f"[leave] uid={uid} nickname={USERS[uid]['nickname']}")
            await _broadcast({
                "type": "presence",
                "event": "leave",
                "user": {"user_id": uid, "nickname": USERS[uid]["nickname"]},
                "online": _online_users(),
                "ts": int(time.time()),
            })
        if WS_LOG:
            print("[conn] client disconnected:", peer)

# ========= main =========
async def main():
    print("[server_ws] starting ws://0.0.0.0:8765")
    print(f"[log] 实验日志将保存到: {LOG_CSV}")

    # 预热：只加载 7B + 3 个 LoRA adapter（与你当前 Core 的加载一致）
    init_models()

    # 单 worker：GPU 串行
    asyncio.create_task(gpu_worker())

    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        print("[server_ws] booting...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[server_ws] stopped by user (Ctrl+C)")
    except Exception as e:
        import traceback
        print("[server_ws] FATAL:", repr(e))
        traceback.print_exc()
        raise

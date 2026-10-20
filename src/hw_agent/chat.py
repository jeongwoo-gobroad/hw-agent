from datetime import date as calendar_date, timedelta
import json
import re
import threading
import time
import uuid
import httpx
from fastapi import HTTPException
from . import db, indexing, smartthings
from .config import LLM_URL, LLM_HEADERS

generation_lock = threading.Lock()


def explicit_filters(message, plan):
    # 날짜와 확장자가 명시됐으면 모델이 빠뜨려도 검색 조건을 지킨다.
    plan = dict(plan)
    match = re.search(r"(?i)(?<![a-z0-9])(pdf|docx|hwpx|hwp|txt|heic|heif|mov|mp4|jpg|png)(?![a-z0-9])", message)
    if match:
        plan["ext"] = match.group(1).lower()
    today = calendar_date.today()
    if "지난달" in message or "지난 달" in message:
        end = today.replace(day=1) - timedelta(days=1)
        plan.update(after=end.replace(day=1).isoformat(), before=end.isoformat())
    elif "이번달" in message or "이번 달" in message:
        plan.update(after=today.replace(day=1).isoformat(), before=today.isoformat())
    elif "어제" in message:
        value=(today-timedelta(days=1)).isoformat(); plan.update(after=value,before=value)
    elif "오늘" in message:
        plan.update(after=today.isoformat(),before=today.isoformat())
    return plan


def create(title="새 대화"):
    identifier = uuid.uuid4().hex
    with db.connect() as conn:
        conn.execute("INSERT INTO sessions VALUES(?,?,?)", (identifier, title[:120], time.time()))
    return {"id": identifier, "title": title}


def respond(session_id, message):
    if not db.rows("SELECT id FROM sessions WHERE id=?", (session_id,)):
        raise HTTPException(404, "대화를 찾을 수 없습니다.")
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(429, "다른 답변을 생성 중입니다.")
    try:
        history = db.rows("SELECT role,content FROM messages WHERE session=? ORDER BY id DESC LIMIT 8", (session_id,))[::-1]
        for item in history:
            if item["role"] == "assistant":
                try:
                    item["content"] = json.loads(item["content"])["text"]
                except (ValueError, KeyError):
                    pass
            item["content"] = item["content"][-250:]
        query, mode = message, "keyword"
        plan = {}
        available = False
        try:
            available = httpx.get(LLM_URL + "/health", headers=LLM_HEADERS, timeout=2).is_success
        except httpx.HTTPError:
            pass
        if available:
            flow_options = db.rows("SELECT id,name FROM flows")[:12] if re.search(r"flow|플로|자동화",message,re.I) else []
            device_options = []
            try:
                device_options = [{"id":d["deviceId"],"name":d.get("label",d["name"])} for d in smartthings.devices() if any(x["id"]=="switch" for c in d["components"] for x in c["capabilities"])]
                device_options = [d for d in device_options if d["name"] in message][:8]
            except HTTPException:
                pass
            prompt = ('너는 한국어 개인 도우미 얼터다. 사용자 요청에 JSON으로 답하라. '
                      '출력: {"intent":"search 또는 chat 또는 flow 또는 device","answer":"한국어 답변",'
                      '"query":"핵심 검색어","ext":"","after":null,"before":null,"flow_id":null,'
                      '"device_id":null,"command":null}. '
                      '파일 찾기는 search, 일상 대화나 설명은 chat, 등록된 자동화 실행 요청은 flow다. '
                      'ext는 점 없는 확장자, after/before는 YYYY-MM-DD 또는 null. JSON만 출력. '
                      '실제 파일이나 기기를 변경했다고 말하지 마라. Flow는 확인 버튼을 제안한다. '
                      '기기 켜기/끄기는 device, command는 on/off. '
                      '등록 Flow: ' + json.dumps(flow_options, ensure_ascii=False) +
                      '. 등록 기기: ' + json.dumps(device_options, ensure_ascii=False) +
                      '. 현재 날짜: ' + time.strftime("%Y-%m-%d"))
            try:
                r = httpx.post(LLM_URL + "/v1/chat/completions", headers=LLM_HEADERS, json={
                    "model": "local", "messages": [{"role": "system", "content": prompt}] +
                    history[-2:] + [{"role": "user", "content": message[:1200]}],
                    "max_tokens": 300, "temperature": 0.1,
                    "chat_template_kwargs": {"enable_thinking": False},
                    "response_format": {"type": "json_object"}}, timeout=180)
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                plan = json.loads(content)
                if not isinstance(plan, dict):
                    raise ValueError("Expected object")
                if plan.get("intent") not in {"search", "chat", "flow", "device", None}:
                    raise ValueError("Unknown intent")
                query = str(plan.get("query", message))[:300]
                mode = "local_llm"
            except (httpx.HTTPError, ValueError, KeyError):
                mode = "keyword_fallback"
                plan = {}
        def date(value, end=False):
            if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                try:
                    return time.mktime(time.strptime(value, "%Y-%m-%d")) + (86399 if end else 0)
                except ValueError:
                    pass
            return None
        intent = plan.get("intent") or "search"
        if intent == "search":
            plan = explicit_filters(message, plan)
        matches = indexing.search(query, ext=str(plan.get("ext") or "")[:20],
                                  after=date(plan.get("after")), before=date(plan.get("before"), True)) if intent == "search" else []
        answer = {"text": f"‘{query}’ 검색 결과 {len(matches)}개를 찾았습니다." if matches else
                  f"‘{query}’에 해당하는 색인 결과가 없습니다. 검색어나 대상 폴더를 확인하세요.",
                  "query": query, "mode": mode, "filters": plan, "files": matches[:8]}
        if intent == "chat":
            answer["text"] = str(plan.get("answer") or "무엇을 도와드릴까요?")[:4000]
        elif intent == "flow":
            candidate = next((f for f in db.rows("SELECT id,name FROM flows") if f["id"] == plan.get("flow_id")), None)
            answer["text"] = "실행할 Flow를 확인해 주세요." if candidate else "일치하는 Flow를 찾지 못했습니다."
            answer["proposed_flow"] = candidate
        elif intent == "device":
            candidate = next((d for d in device_options if d["id"] == plan.get("device_id")), None)
            command = plan.get("command")
            if candidate and command in {"on", "off"}:
                answer["text"] = candidate["name"] + (" 켜기" if command == "on" else " 끄기") + "를 확인해 주세요."
                answer["proposed_command"] = {"device_id": candidate["id"], "capability": "switch", "command": command}
            else:
                answer["text"] = "연결된 기기 또는 실행할 동작을 확인할 수 없습니다."
        with db.connect() as conn:
            conn.execute("INSERT INTO messages(session,role,content,created) VALUES(?,?,?,?)",
                         (session_id, "user", message, time.time()))
            conn.execute("INSERT INTO messages(session,role,content,created) VALUES(?,?,?,?)",
                         (session_id, "assistant", json.dumps(answer, ensure_ascii=False), time.time()))
        return answer
    finally:
        generation_lock.release()

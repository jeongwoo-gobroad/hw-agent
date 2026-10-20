"""Read llama.cpp token events without exposing the internal routing JSON."""
import json
import re
import time
import httpx
from fastapi import HTTPException
from .config import LLM_URL, LLM_HEADERS


def partial_string(text, key):
    match = re.search(r'"' + re.escape(key) + r'"\s*:\s*"', text)
    if not match:
        return ""
    body = text[match.end():]
    decoded = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == '"':
            break
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            break
        width = 6 if body[index + 1] == "u" else 2
        if index + width > len(body):
            break
        try:
            decoded.append(json.loads('"' + body[index:index + width] + '"'))
        except ValueError:
            break
        index += width
    return "".join(decoded)


def stream_completion(payload, on_delta, cancelled):
    content, last = "", ""
    started = time.monotonic()
    with httpx.stream("POST", LLM_URL + "/v1/chat/completions",
                      headers=LLM_HEADERS, json={**payload, "stream": True},
                      timeout=httpx.Timeout(180, connect=10)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if cancelled.is_set():
                raise HTTPException(499, "응답 생성을 중단했습니다.")
            if time.monotonic() - started > 180:
                raise httpx.ReadTimeout("Generation deadline exceeded")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            choices = event.get("choices", [])
            if not choices:
                continue
            content += choices[0].get("delta", {}).get("content") or ""
            if len(content) > 16000:
                raise ValueError("Oversized model response")
            # 실행에 쓰는 JSON은 끝까지 검증하고, 화면에는 답변 문장만 보낸다.
            visible = partial_string(content, "answer")
            if not visible:
                query = partial_string(content, "query")
                visible = "검색어를 정리하고 있어요: " + query if query else ""
            if visible and visible != last:
                on_delta({"type": "delta", "text": visible})
                last = visible
    return content

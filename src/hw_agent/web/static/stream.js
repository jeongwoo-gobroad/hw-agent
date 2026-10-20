async function streamAnswer(session, message, csrfToken, signal, update) {
  const response = await fetch(`/api/sessions/${session}/messages/stream`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken},
    body: JSON.stringify({message}),
    signal
  });
  if (!response.ok) {
    if (response.status === 401) location.href = "/login";
    const error = await response.json();
    throw new Error(typeof error.detail === "string" ? error.detail : "요청을 처리하지 못했습니다.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", result;
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const event = JSON.parse(line.slice(5));
          if (event.type === "error") throw new Error(event.message);
          if (event.type === "result") result = event.result;
          else update(event);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
  if (!result) throw new Error("응답 연결이 끊겼습니다. 다시 시도하세요.");
  return result;
}

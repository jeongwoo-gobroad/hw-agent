/* Touch controls share the dashboard's authenticated APIs and chat history. */
(() => {
  if (location.pathname !== "/panel") return;
  document.body.classList.add("touch-panel");
  const input = document.querySelector('#chat-form input');
  input.inputMode = "none";
  let keyboardInput=input;
  const account=document.querySelector('#oauth-status').closest('.card');
  const details=document.createElement('details');details.className='panel-account';
  const summary=document.createElement('summary');summary.textContent='삼성 계정 연결 관리';details.append(summary);account.replaceWith(details);details.append(account);
  const dock = document.createElement("nav");
  dock.className = "panel-dock";
  dock.setAttribute("aria-label", "터치 패널 메뉴");
  dock.innerHTML = '<button data-view="home">우리 집</button><button data-view="chat">챗봇</button><button id="panel-voice">음성 입력</button><button id="panel-wake" aria-pressed="false">얼터 호출 대기</button><a href="/">대시보드</a>';
  document.body.append(dock);
  const historyButton = document.createElement("button"); historyButton.textContent = "대화 목록";
  historyButton.onclick = () => {document.body.classList.toggle("panel-history");showKeyboard(false);};
  document.querySelector("#chat .section-head > div").prepend(historyButton);
  const popup = document.createElement("section");
  popup.id = "touch-keyboard"; popup.hidden = true;
  popup.setAttribute("aria-label", "팝업 키보드");
  popup.innerHTML = '<div class="keyboard-head"><strong>얼터에게 물어보세요</strong><button id="panel-new-chat" class="ghost">새 대화</button><label class="voice-file">음성 파일<input id="voice-file" type="file" accept="audio/*" aria-label="음성 파일로 입력"></label><span id="voice-feedback" role="status">한글 · 두벌식</span><button id="keyboard-close" class="ghost">키보드 닫기</button></div><div class="simple-keyboard"></div>';
  document.body.append(popup);
  let korean = true, shift = false, listening = false, wake = false, microphone = null, recorder = null, timer = null, cancelled = false, running = false;
  const feedback = text => { document.querySelector("#voice-feedback").textContent = text; notify(text); };
  const layouts = {
    ko: ["ㅂ ㅈ ㄷ ㄱ ㅅ ㅛ ㅕ ㅑ ㅐ ㅔ", "ㅁ ㄴ ㅇ ㄹ ㅎ ㅗ ㅓ ㅏ ㅣ", "{shift} ㅋ ㅌ ㅊ ㅍ ㅠ ㅜ ㅡ {bksp}", "{lang} {space} . ? {enter}"],
    koShift: ["ㅃ ㅉ ㄸ ㄲ ㅆ ㅛ ㅕ ㅑ ㅒ ㅖ", "ㅁ ㄴ ㅇ ㄹ ㅎ ㅗ ㅓ ㅏ ㅣ", "{shift} ㅋ ㅌ ㅊ ㅍ ㅠ ㅜ ㅡ {bksp}", "{lang} {space} . ? {enter}"],
    en: ["1 2 3 4 5 6 7 8 9 0", "q w e r t y u i o p", "a s d f g h j k l", "{shift} z x c v b n m {bksp}", "{lang} {space} . ? {enter}"]
  };
  function showKeyboard(show = true) { popup.hidden = !show; document.body.classList.toggle("keyboard-open", show); }
  const keyboard = new window.SimpleKeyboard.default({
    layout: {default: layouts.ko}, useButtonTag: true, preventMouseDownDefault: true,
    display: {"{bksp}": "지우기", "{enter}": "보내기", "{space}": "띄어쓰기", "{lang}": "한/영", "{shift}": "쌍자음"},
    onKeyPress(key) {
      const input=keyboardInput;
      if (input.disabled) return;
      if (key === "{lang}" || key === "{shift}") {
        if (key === "{lang}") { korean = !korean; shift = false; } else shift = !shift;
        keyboard.setOptions({layout: {default: korean ? (shift ? layouts.koShift : layouts.ko) : layouts.en.map(row => shift ? row.split(" ").map(k => k.length === 1 ? k.toUpperCase() : k).join(" ") : row)}}); return;
      }
      if (key === "{enter}") { if(input.matches("#chat-form input"))document.querySelector("#chat-form").requestSubmit();else showKeyboard(false); return; }
      let start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? start;
      let before = input.value.slice(0,start), after = input.value.slice(end);
      let units = Hangul.disassemble(before);
      if (key === "{bksp}") { if (start === end) units.pop(); }
      else units.push(key === "{space}" ? " " : key);
      const next = Hangul.assemble(units);
      input.value = (next + after).slice(0,1200); input.focus(); input.setSelectionRange(next.length,next.length);
      input.dispatchEvent(new Event("input", {bubbles:true}));
    }
  });
  dock.querySelectorAll("[data-view]").forEach(button => button.onclick = () => {
    keyboardInput=input;page(button.dataset.view); showKeyboard(button.dataset.view === "chat");
    dock.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("selected", b === button));
  });
  document.querySelector("#panel-new-chat").onclick = () => { if(!chatController) document.querySelector("#new-chat").click(); };
  document.querySelector("#voice-file").onchange = async event => {
    const file = event.target.files[0]; if(!file || running) return;
    if(file.size>1500000) {feedback("음성 파일은 1.5MB 이하, 15초 이내로 선택하세요.");return;}
    running=true;
    try {
      feedback("음성 파일을 Pi에서 인식하고 있습니다…");
      const audio = await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(",")[1]);reader.readAsDataURL(file);});
      const result=await api("/voice/transcribe","POST",{audio}); input.value=result.text;
      feedback(result.text ? "음성 인식 완료 · 내용을 확인하고 보내세요." : "음성이 들리지 않았습니다.");
    } catch(error) {feedback(error.message);} finally {running=false;event.target.value="";}
  };
  document.querySelector("#keyboard-close").onclick = () => showKeyboard(false);
  input.addEventListener("click", () => {keyboardInput=input;showKeyboard();});
  document.querySelector('#device-filter').addEventListener('click',event=>{keyboardInput=event.target;keyboardInput.inputMode='none';showKeyboard();});
  document.querySelector("#chat-form").addEventListener("submit", () => showKeyboard(false));
  function release() { if (microphone) microphone.getTracks().forEach(track => track.stop()); microphone = null; }
  function controls() {
    document.querySelector("#panel-voice").textContent = listening ? "녹음 마치기" : "음성 입력";
    document.querySelector("#panel-wake").textContent = wake ? "호출 대기 끄기" : "얼터 호출 대기";
    document.querySelector("#panel-wake").setAttribute("aria-pressed", String(wake));
  }
  async function capture() {
    if (!window.isSecureContext || !navigator.mediaDevices) throw new Error("마이크는 HTTPS 주소 또는 Pi의 localhost에서 사용할 수 있습니다.");
    if (!microphone) microphone = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
    const chunks = [];
    return await new Promise((resolve,reject) => {
      recorder = new MediaRecorder(microphone);
      recorder.ondataavailable = event => { if(event.data.size) chunks.push(event.data); };
      recorder.onerror = () => reject(new Error("녹음을 시작하지 못했습니다."));
      recorder.onstop = () => { clearTimeout(timer); resolve(new Blob(chunks,{type:recorder.mimeType})); };
      recorder.start(); listening = true; controls();
      feedback(wake ? "‘얼터, …해줘’라고 말씀하세요 · 호출 대기 중" : "말씀하세요 · 최대 12초 · 한 번 더 누르면 녹음 종료");
      timer = setTimeout(() => {if(recorder?.state === "recording") recorder.stop();},wake ? 6000 : 12000);
    });
  }
  async function listen() {
    if (listening) { recorder?.stop(); return; }
    if (running) return;
    running = true;
    cancelled = false; page("chat"); showKeyboard();
    try {
      const state = await api("/voice");
      if (!state.ready) throw new Error("음성 모델을 준비하고 있습니다.");
      do {
        const blob = await capture(); listening = false; controls();
        if (cancelled) break;
        feedback("Pi에서 한국어를 인식하고 있습니다…");
        const encoded = await new Promise(resolve => {const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(",")[1]);reader.readAsDataURL(blob);});
        const result = await api("/voice/transcribe","POST",{audio:encoded});
        if (cancelled) break;
        let text = result.text; const fromWake = wake;
        if (wake) {
          const match = text.match(/(?:얼터|얼 털|얼타|알터)[,，.!?\s]*(.*)/);
          if (!match || !match[1].trim()) { feedback("호출 대기 중 · ‘얼터’와 요청을 함께 말씀하세요"); continue; }
          text = match[1].trim(); wake = false;
        }
        if (text) { input.value=text; feedback("음성 인식 완료 · 내용을 확인하고 보내기를 누르세요."); input.focus(); if(fromWake && !chatController) {feedback("얼터 호출을 인식했습니다. 요청을 처리합니다.");document.querySelector("#chat-form").requestSubmit();} }
        else feedback("음성이 들리지 않았습니다. 다시 시도해 주세요.");
      } while(wake && !cancelled);
    } catch(error) {
      const messages={NotFoundError:"마이크가 없습니다. USB 마이크를 연결해 주세요.",NotAllowedError:"마이크 접근이 허용되지 않았습니다. 브라우저 권한을 확인하세요.",NotReadableError:"마이크를 다른 프로그램이 사용 중입니다."};
      feedback(messages[error.name] || error.message);
    } finally { wake=false;listening=false;running=false;release();controls(); }
  }
  document.querySelector("#panel-voice").onclick = listen;
  document.querySelector("#panel-wake").onclick = () => {
    if (wake) { wake=false;cancelled=true;if(recorder?.state === "recording")recorder.stop();release();controls();feedback("호출 대기를 종료했습니다."); }
    else if (!running) { wake=true;listen(); }
  };
  document.addEventListener("visibilitychange",()=>{if(document.hidden){cancelled=true;wake=false;if(recorder?.state==="recording")recorder.stop();release();controls();}});
  window.addEventListener("pagehide",release);
})();

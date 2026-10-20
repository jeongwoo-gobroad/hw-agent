const $ = s => document.querySelector(s);
const el = (tag, text, cls) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
let chatController=null;
let csrf="", sessionId=null, roots=[], flowList=[], deviceList=[], editFlow=null, offset=0, lastQuery="";
const titles={overview:"나의 공간, 한눈에.",files:"필요한 파일을 찾아보세요.",chat:"얼터와 함께 찾기.",drives:"저장장치를 한곳에서.",home:"우리 집의 작은 자동화.",camera:"지금, 카메라 너머.",settings:"나에게 맞게 설정하기."};
function notify(text){$("#notice").textContent=text;$("#notice").hidden=false;clearTimeout(notify.timer);notify.timer=setTimeout(()=>$("#notice").hidden=true,7000);}
async function api(path,method="GET",body){const response=await fetch("/api"+path,{method,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},...(body!==undefined?{body:JSON.stringify(body)}:{})});const result=await response.json();if(!response.ok){if(response.status===401&&!path.startsWith("/smartthings/"))location.href="/login";throw new Error(typeof result.detail==="string"?result.detail:JSON.stringify(result.detail));}return result;}
function action(selector,fn){$(selector).addEventListener("click",async e=>{const button=e.currentTarget;button.disabled=true;try{await fn(e);}catch(error){notify(error.message);}finally{button.disabled=button.dataset.inactive==="true";}});}
function button(text,fn,cls="ghost"){const b=el("button",text,cls);b.type="button";b.onclick=async()=>{b.disabled=true;try{await fn();}catch(error){notify(error.message);}finally{b.disabled=false;}};return b;}
function size(value){return value==null?"—":(value/1024**3).toFixed(1)+" GiB";}
function page(name){
  if(!titles[name])name="overview";
  document.querySelectorAll(".page").forEach(n=>n.hidden=n.id!==name);
  document.querySelectorAll("nav button").forEach(n=>{n.classList.toggle("selected",n.dataset.page===name);if(n.dataset.page===name)n.setAttribute("aria-current","page");else n.removeAttribute("aria-current");});
  $("#heading").textContent=titles[name];history.replaceState(null,"","#"+name);
  if(name!=="camera")$("#stream").removeAttribute("src");
  const loaders={drives:loadDrives,home:loadHome,chat:loadSessions,camera:loadCamera};
  if(loaders[name])loaders[name]().catch(e=>notify(e.message));
  if(name==="files"&&!lastQuery)searchFiles().catch(e=>notify(e.message));
}

document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>page(b.dataset.page));
document.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>page(b.dataset.go));
action("#logout",async()=>{await api("/logout","POST",{});location.href="/login";});
async function status(){const s=await api("/status");$("#file-count").textContent=s.indexed_files.toLocaleString();$("#memory").textContent=size(s.memory.MemAvailable);$("#camera-status").textContent=s.camera.recording?"녹화 중":s.camera.running?"켜짐":"꺼짐";$("#scan-status").textContent=s.index.running?`색인 중 · ${s.index.files}개`:s.index.error|| (s.last_scan?new Date(Number(s.last_scan)*1000).toLocaleTimeString()+" 확인":"폴더를 등록하세요");$("#gesture-state").textContent=s.camera.last_gesture?.name?"최근 인식: "+({Open_Palm:"손바닥",Closed_Fist:"주먹",Victory:"V 표시",Thumb_Up:"엄지 위",Thumb_Down:"엄지 아래"}[s.camera.last_gesture.name]||s.camera.last_gesture.name):s.camera.gestures?"손동작 인식 대기 중":"제스처 인식 꺼짐";if(s.gesture_event&&status.lastEvent!==s.gesture_event.time){status.lastEvent=s.gesture_event.time;notify("제스처 감지: "+s.gesture_event.gesture);}}
async function loadRoots(){roots=await api("/roots");document.querySelectorAll(".root-select").forEach(select=>{const old=select.value;select.replaceChildren();if(select.name==="root")select.add(new Option("전체 폴더","0"));roots.forEach(r=>select.add(new Option(r.label,r.id)));if([...select.options].some(o=>o.value===old))select.value=old;});$("#share-path").replaceChildren();roots.forEach(r=>$("#share-path").add(new Option(r.path,r.path)));$("#roots").replaceChildren();if(!roots.length)$("#roots").append(el("p","등록된 폴더가 없습니다. 위에서 드라이브의 폴더를 선택하세요.","muted"));$("#share-form button").disabled=!roots.length;roots.forEach(r=>{const row=el("div",undefined,"root-row");row.append(el("span",r.path),button("등록 해제",async()=>{if(!confirm("색인에서 이 폴더를 제외할까요? 원본은 보존됩니다."))return;await api("/roots/"+r.id,"DELETE");await loadRoots();}));$("#roots").append(row);});}
async function loadDrives(){const devices=await api("/devices");$("#devices").replaceChildren();if(!devices.length)$("#devices").append(el("p","연결된 외장 저장장치가 없습니다.","muted"));devices.forEach(d=>{const card=el("div",undefined,"card");card.append(el("h2",d.model||d.name),el("p",`${d.transport} · ${d.fstype} · ${size(d.size)}`),el("p",d.mount||"마운트되지 않음"),el("small","남은 공간 "+size(d.free)));if(d.mount)card.append(button("폴더 선택",()=>browse(d.mount)));card.append(button(d.mount?"안전하게 해제":"마운트",async()=>{if(d.mount&&!confirm("이 드라이브를 해제할까요?"))return;const result=await api("/devices/action","POST",{device:d.path,action:d.mount?"unmount":"mount"});notify(result.message);await loadDrives();}));$("#devices").append(card);});await loadRoots();await loadShares();}
async function browse(path){const data=await api("/folders?path="+encodeURIComponent(path));const box=$("#folder-browser");box.replaceChildren(el("p",data.path));const controls=el("div",undefined,"actions");if(data.path!==data.mount)controls.append(button("상위 폴더",()=>browse(data.path.slice(0,data.path.lastIndexOf("/")))));controls.append(button("이 폴더 등록",async()=>{await api("/roots","POST",{path:data.path});await loadRoots();notify("폴더가 등록되었습니다.");}));box.append(controls);data.children.forEach(p=>box.append(button(p.split("/").pop(),()=>browse(p))));}
action("#refresh-drives",loadDrives);
action("#index-now",async()=>{await api("/index","POST",{});notify("색인을 시작했습니다.");});
$("#share-form").onsubmit=async e=>{e.preventDefault();try{const f=new FormData(e.target);const r=await api("/shares","POST",{path:f.get("path"),name:f.get("name"),readonly:f.has("readonly")});notify(r.message);await loadShares();}catch(error){notify(error.message);}};
function fileSize(value){if(value<1024)return value+" B";if(value<1024**2)return (value/1024).toFixed(1)+" KiB";return (value/1024**2).toFixed(1)+" MiB";}
function fileCards(files){const grid=el("div",undefined,"file-grid");files.forEach(f=>{const card=el("article",undefined,"file-card");card.append(el("span",f.ext.replace(".","").toUpperCase()||"FILE","file-type"),el("h3",f.name),el("small",f.path),el("p",f.snippet||"내용 미리보기 없음"),el("small",new Date(f.modified*1000).toLocaleDateString()+" · "+fileSize(f.size)),button("미리보기",()=>showPreview(f)));grid.append(card);});return grid;}
async function searchFiles(next=false){if(!next)offset=0;$("#result-count").textContent="검색 중…";const data=new FormData($("#search"));if(data.get("after")&&data.get("before")&&data.get("after")>data.get("before")){$("#result-count").textContent="시작 날짜가 종료 날짜보다 늦습니다.";return;}const params=new URLSearchParams();for(const [key,value]of data){if(!value)continue;if(key==="after"||key==="before")params.set(key,new Date(value+(key==="before"?"T23:59:59":"T00:00:00")).getTime()/1000);else params.set(key,key==="rerank"?"true":value);}params.set("offset",offset);lastQuery=params.toString();const files=await api("/search?"+lastQuery);if(next)$("#results").append(...fileCards(files).children);else $("#results").replaceChildren(...fileCards(files).children);$("#result-count").textContent=files.length?`검색 결과 ${offset+files.length}개 표시`:"검색 결과가 없습니다. 색인 폴더와 검색 조건을 확인하세요.";$("#more").hidden=files.length<40;}
$("#search").onsubmit=e=>{e.preventDefault();searchFiles().catch(e=>notify(e.message));};
action("#reset-search",async()=>{$("#search").reset();await searchFiles();});
action("#more",async()=>{offset+=40;await searchFiles(true);});
async function showPreview(f){$("#preview-title").textContent=f.name;$("#preview-body").replaceChildren(el("p","미리보기를 준비하고 있습니다…"));$("#download").href="/api/files/"+f.id+"/download";$("#preview").showModal();const url="/api/files/"+f.id+"/preview";if([".jpg",".jpeg",".png",".webp",".gif",".heic",".heif",".bmp"].includes(f.ext)){const img=el("img");img.src=url;img.alt=f.name;img.onerror=()=>$("#preview-body").replaceChildren(el("p","미리보기를 불러올 수 없습니다."));$("#preview-body").replaceChildren(img);}else if([".mov",".mp4",".mkv",".avi",".m4v"].includes(f.ext)){const video=el("video");video.controls=true;video.src=url;video.onerror=()=>$("#preview-body").append(el("p","변환 실패 또는 지원하지 않는 영상입니다."));$("#preview-body").replaceChildren(video);}else{const response=await fetch(url);if(!response.ok){$("#preview-body").replaceChildren(el("p","미리보기를 열지 못했습니다. 드라이브 연결 상태를 확인하세요."));return;}$("#preview-body").replaceChildren(el("pre",await response.text()));}}
action("#close-preview",()=>$("#preview").close());
$("#preview").addEventListener("close",()=>$("#preview-body").replaceChildren());
async function loadSessions(){
 const list=await api("/sessions");$("#sessions").replaceChildren();
 if(!sessionId&&list.length){sessionId=list[0].id;$("#chat-title").textContent=list[0].title;await loadMessages();}
 list.forEach(s=>{const item=button(s.title,async()=>{sessionId=s.id;$("#chat-title").textContent=s.title;await loadMessages();await loadSessions();},"session"+(sessionId===s.id?" active":""));item.disabled=!!chatController;$("#sessions").append(item);});
 if(!list.length)$("#sessions").append(el("small","대화를 시작하면 여기에 저장됩니다."));
 for(const id of ["rename-chat","delete-chat","export-chat"])$("#"+id).disabled=!sessionId||!!chatController;
}

async function loadMessages(){if(!sessionId)return;const messages=await api("/sessions/"+sessionId);$("#messages").replaceChildren();messages.forEach(m=>{const node=el("div",undefined,"message "+m.role);if(m.role==="assistant"){try{const result=JSON.parse(m.content);node.append(el("p",result.text),el("small",result.mode==="local_llm"?"로컬 모델":result.mode==="keyword_fallback"?"모델 응답 실패 · 키워드 검색":"키워드 검색"),fileCards(result.files||[]));if(result.proposed_flow)node.append(button("Flow 실행 · "+result.proposed_flow.name,async()=>{if(confirm("이 Flow를 실행할까요?")){const run=await api("/flows/"+result.proposed_flow.id+"/run","POST",{});notify("Flow "+run.status);}}));if(result.proposed_command)node.append(button("기기 명령 실행",async()=>{if(confirm(result.text)){await api("/smartthings/command","POST",result.proposed_command);notify("명령을 전달했습니다.");}}));}catch{node.textContent=m.content;}}else node.textContent=m.content;$("#messages").append(node);});$("#messages").scrollTop=$("#messages").scrollHeight;}
action("#new-chat",async()=>{const r=await api("/sessions","POST",{title:"새 대화"});sessionId=r.id;$("#chat-title").textContent=r.title;await loadSessions();await loadMessages();});
action("#rename-chat",async()=>{if(!sessionId)return;const title=prompt("대화 이름");if(title){await api("/sessions/"+sessionId,"PATCH",{title});$("#chat-title").textContent=title;await loadSessions();}});
action("#delete-chat",async()=>{if(sessionId&&confirm("이 대화를 삭제할까요?")){await api("/sessions/"+sessionId,"DELETE");sessionId=null;$("#messages").replaceChildren();await loadSessions();}});
action("#export-chat",async()=>{if(!sessionId)return;const data=await api("/sessions/"+sessionId);const a=el("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));a.download="alter-chat.json";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});
$("#chat-form").onsubmit=async e=>{
 e.preventDefault();if(chatController)return;
 const form=e.target,input=form.elements.namedItem("message"),message=input.value.trim();if(!message)return;
 chatController=new AbortController();const controller=chatController;
 form.querySelector('button[type="submit"],button:not([type])').disabled=true;input.disabled=true;
 $("#stop-chat").hidden=false;$("#new-chat").disabled=true;
 let node,textNode,timer;
 try{
  if(!sessionId){const session=await api("/sessions","POST",{title:message.slice(0,40)});sessionId=session.id;$("#chat-title").textContent=session.title;}
  await loadSessions();
  $("#messages").append(el("div",message,"message user"));
  node=el("div",undefined,"message assistant streaming");textNode=el("p","요청을 읽고 있습니다…");const progress=el("small","생성 준비 중 · 0초");node.append(textNode,progress);$("#messages").append(node);input.value="";
  const started=Date.now();let receiving=false;
  timer=setInterval(()=>progress.textContent=(receiving?"실시간 생성 중":"모델이 요청을 처리하고 있습니다")+" · "+Math.floor((Date.now()-started)/1000)+"초",1000);
  await streamAnswer(sessionId,message,csrf,controller.signal,event=>{if(event.text){textNode.textContent=event.text;receiving=event.type==="delta";$("#messages").scrollTop=$("#messages").scrollHeight;}});
  await loadMessages();
 }catch(error){if(textNode)textNode.textContent=error.name==="AbortError"?"생성을 중단했습니다. 중단된 답변은 저장하지 않습니다.":error.message;else notify(error.message);}
 finally{clearInterval(timer);node?.classList.remove("streaming");if(node?.isConnected)node.querySelector("small").textContent="";chatController=null;input.disabled=false;form.querySelector('button[type="submit"],button:not([type])').disabled=false;$("#stop-chat").hidden=true;$("#new-chat").disabled=false;await loadSessions();input.focus();}
};
action("#stop-chat",()=>chatController?.abort());

async function loadFlows(){flowList=await api("/flows");$("#flows").replaceChildren();if(!flowList.length)$("#flows").append(el("p","아직 Flow가 없습니다. 기기 동작과 대기를 조합해 보세요.","muted"));flowList.forEach(f=>{const card=el("div",undefined,"card");card.append(el("h2",f.name),el("p",f.steps.length+"개 단계"),button("실행",async()=>{if(!confirm(f.name+" Flow를 실행할까요?"))return;const r=await api("/flows/"+f.id+"/run","POST",{});notify("Flow "+r.status);await loadRuns();}),button("편집",()=>editFlowForm(f)),button("복제",async()=>{await api("/flows","POST",{name:f.name+" 복사",steps:f.steps});await loadFlows();}),button("삭제",async()=>{if(confirm("Flow를 삭제할까요?")){await api("/flows/"+f.id,"DELETE");await loadFlows();}}));$("#flows").append(card);});await loadRuns();}
async function loadRuns(){const rows=await api("/runs");$("#runs").replaceChildren();rows.forEach(r=>{$("#runs").append(el("p",`${new Date(r.created*1000).toLocaleString()} · ${flowList.find(f=>f.id===r.flow)?.name||"삭제된 Flow"} · ${({completed:"완료",failed:"실패",running:"실행 중",interrupted:"재시작으로 중단"})[r.status]||r.status} · ${JSON.parse(r.log).filter(x=>x.status==="completed").length}단계 완료`));});if(!rows.length)$("#runs").append(el("p","아직 실행 이력이 없습니다.","muted"));}
async function loadHome(){await loadFlows();const connection=await loadConnection();if(connection.connected||connection.pat_configured)await loadDevices();else $("#smart-devices").replaceChildren(el("p","삼성 계정을 연결하면 기기 목록을 볼 수 있습니다.","muted"));}
async function loadDevices(){
 $("#smart-devices").replaceChildren(el("p","기기를 불러오고 있습니다…","loading"));
 try{deviceList=await api("/smartthings/devices");renderDevices();}
 catch(error){$("#smart-devices").replaceChildren(el("p",error.message,"muted"));}
}
function renderDevices(){
 const query=$("#device-filter").value.trim().toLowerCase();$("#smart-devices").replaceChildren();
 const listing=deviceList.filter(d=>(d.label||d.name).toLowerCase().includes(query));
 if(!listing.length)$("#smart-devices").append(el("p",query?"이름이 일치하는 기기가 없습니다.":"연결된 기기가 없습니다.","muted"));
 listing.forEach(d=>{const card=el("div",undefined,"card"),state=el("p","상태 확인을 누르면 최신 정보를 가져옵니다.","device-state muted");
 card.append(el("h2",d.label||d.name));const controls=el("div",undefined,"actions");
 const refresh=async()=>{const result=await api("/smartthings/devices/"+d.deviceId+"/status");const values=[];for(const [capability,attributes]of Object.entries(result.components?.main||{})){for(const [attribute,data]of Object.entries(attributes)){if(data.value==null||typeof data.value==="object")continue;const labels={switch:"전원",level:"밝기",temperature:"온도",humidity:"습도",battery:"배터리",motion:"움직임",contact:"접촉",presence:"재실",volume:"음량",mute:"음소거"};if(labels[attribute])values.push(labels[attribute]+": "+({on:"켜짐",off:"꺼짐",active:"감지",inactive:"미감지",open:"열림",closed:"닫힘",present:"있음","not present":"없음"}[data.value]??data.value)+(data.unit?" "+data.unit:""));}}state.textContent=values.length?values.join(" · "):"이 기기는 표시할 수 있는 기본 상태가 없습니다.";};
 controls.append(button("상태 확인",refresh));
 if(d.components?.find(c=>c.id==="main")?.capabilities.some(x=>x.id==="switch"))for(const [name,command]of [["켜기","on"],["끄기","off"]])controls.append(button(name,async()=>{await api("/smartthings/command","POST",{device_id:d.deviceId,capability:"switch",command});state.textContent="명령을 전달했습니다. 실제 상태는 ‘상태 확인’으로 갱신하세요.";}));
 card.append(controls,state);$("#smart-devices").append(card);
 });
}
action("#refresh-home",loadHome);
$("#device-filter").addEventListener("input",renderDevices);
action("#jump-flows",()=>$("#flow-section").scrollIntoView({behavior:"smooth",block:"start"}));
action("#cancel-flow",()=>{$("#flow-editor").hidden=true;editFlow=null;});

function editFlowForm(flow=null){editFlow=flow?.id||null;$("#flow-editor").hidden=false;$("#flow-editor").scrollIntoView({behavior:"smooth",block:"center"});$("#flow-form").elements.namedItem("name").value=flow?.name||"";$("#flow-steps").replaceChildren();(flow?.steps||[{type:"delay",seconds:1}]).forEach(addStep);}
function addStep(step){
  const row=el("div",undefined,"step");row.dataset.type=step.type;
  if(step.type==="delay"){
    row.append(el("span","기다리기"));const input=el("input");input.type="number";input.min=0;input.max=60;input.value=step.seconds;input.dataset.field="seconds";input.setAttribute("aria-label","대기 시간 (초)");row.append(input,el("span","초"));
  }else{
    const device=el("select");device.dataset.field="device_id";device.setAttribute("aria-label","대상 기기");deviceList.forEach(d=>device.add(new Option(d.label||d.name,d.deviceId)));
    if(step.device_id&&!deviceList.some(d=>d.deviceId===step.device_id))device.add(new Option("미연결 기기 · "+step.device_id,step.device_id));
    device.value=step.device_id||device.value;
    const cmd=el("select");cmd.dataset.field="command";cmd.setAttribute("aria-label","기기 동작");
    const value=el("input");value.type="number";value.dataset.field="argument";value.setAttribute("aria-label","설정 값");value.placeholder="값";value.value=step.arguments?.[0]??50;
    const choices={switch:[["on","켜기"],["off","끄기"]],switchLevel:[["setLevel","밝기 설정"]],audioVolume:[["setVolume","음량 설정"],["mute","음소거"],["unmute","음소거 해제"]],colorTemperature:[["setColorTemperature","색온도 설정"]]};
    function options(){cmd.replaceChildren();const d=deviceList.find(d=>d.deviceId===device.value);const capabilities=d?.components?.find(c=>c.id==="main")?.capabilities?.map(c=>c.id)||[step.capability||"switch"];for(const cap of capabilities)for(const [command,label]of choices[cap]||[])cmd.add(new Option(label,cap+":"+command));if(step.command)cmd.value=(step.capability||"switch")+":"+step.command;update();}
    function update(){const numeric=cmd.value.includes(":set");value.hidden=!numeric;value.min=cmd.value.startsWith("colorTemperature")?2000:0;value.max=cmd.value.startsWith("colorTemperature")?6500:100;}
    cmd.onchange=update;device.onchange=options;options();row.append(device,cmd,value);
  }
  row.append(button("제거",()=>row.remove()));$("#flow-steps").append(row);
}
function readStep(row){
  if(row.dataset.type==="delay")return {type:"delay",seconds:Number(row.querySelector("input").value)};
  const [capability,command]=row.querySelector('[data-field="command"]').value.split(":");
  return {type:"device",device_id:row.querySelector('[data-field="device_id"]').value,capability,command,arguments:command?.startsWith("set")?[Number(row.querySelector('[data-field="argument"]').value)]:[]};
}
action("#new-flow",()=>editFlowForm());
action("#add-delay",()=>addStep({type:"delay",seconds:1}));
action("#add-device",()=>{if(!deviceList.length){notify("SmartThings 기기를 먼저 연결하세요.");return;}addStep({type:"device"});});
$("#flow-form").onsubmit=async e=>{e.preventDefault();try{const steps=[...$("#flow-steps").children].map(readStep);await api("/flows"+(editFlow?"/"+editFlow:""),editFlow?"PUT":"POST",{name:e.target.elements.namedItem("name").value,steps});$("#flow-editor").hidden=true;await loadFlows();}catch(error){notify(error.message);}};
async function loadCamera(){await loadRoots();flowList=await api("/flows");const state=await api("/camera");$("#camera-detail").textContent=state.error|| (state.recording?"녹화 중 · "+state.record_dir:state.running?"카메라 켜짐":"카메라 꺼짐");if(state.running&&!$("#stream").getAttribute("src"))$("#stream").src="/api/camera/stream";for(const [id,inactive]of Object.entries({"camera-on":state.running,"camera-off":!state.running,"record-on":state.recording||!roots.length,"record-off":!state.recording})){const control=$("#"+id);control.dataset.inactive=String(inactive);control.disabled=inactive;}$("#gesture-enabled").checked=state.gestures;$("#gesture-mappings").replaceChildren();for(const [key,label]of Object.entries({Open_Palm:"손바닥",Closed_Fist:"주먹",Victory:"V 표시",Thumb_Up:"엄지 위",Thumb_Down:"엄지 아래"})){const l=el("label",label);const select=el("select");select.dataset.gesture=key;select.add(new Option("동작 없음",""));select.add(new Option("대시보드에 알림","chat"));flowList.forEach(f=>select.add(new Option("Flow · "+f.name,"flow:"+f.id)));select.value=state.mappings[key]||"";l.append(select);$("#gesture-mappings").append(l);}}
action("#camera-on",async()=>{await api("/camera/start","POST",{});await loadCamera();});
action("#camera-off",async()=>{$("#stream").removeAttribute("src");await api("/camera/stop","POST",{});await loadCamera();});
action("#record-on",async()=>{await api("/camera/record","POST",{root_id:Number($("#record-root").value)});await loadCamera();});
action("#record-off",async()=>{await api("/camera/record/stop","POST",{});await loadCamera();notify("녹화가 저장되었습니다.");});
action("#save-gestures",async()=>{const mappings={};document.querySelectorAll("[data-gesture]").forEach(s=>mappings[s.dataset.gesture]=s.value);await api("/gestures","POST",{enabled:$("#gesture-enabled").checked,mappings});notify("제스처 설정을 적용했습니다.");});
(async()=>{try{const user=await api("/me");csrf=user.csrf;await loadRoots();await status();page(location.pathname==="/panel"?"home":location.hash.slice(1)||"overview");setInterval(()=>status().catch(()=>{}),5000);}catch(error){notify(error.message);}})();

async function loadShares(){const shares=await api("/shares");$("#shares").replaceChildren();if(!shares.length)$("#shares").append(el("p","활성 SMB 공유가 없습니다.","muted"));shares.forEach(s=>{const row=el("div",undefined,"root-row");row.append(el("span","Alter-"+s.name+" · "+(s.readonly?"읽기 전용":"읽기/쓰기")+" · "+s.path),button("공유 해제",async()=>{await api("/shares/"+s.name+"?path="+encodeURIComponent(s.path),"DELETE");await loadShares();}));$("#shares").append(row);});}

async function loadConnection(){const state=await api("/smartthings/connection");$("#oauth-status").textContent=state.connected?(state.error?"인증 갱신에 실패했습니다. 다시 연결하세요.":"삼성 계정이 연결되었습니다."):state.configured?"삼성 계정으로 로그인하여 기기를 연결하세요.":"OAuth 앱 등록을 준비하고 있습니다.";$("#oauth-connect").disabled=!state.configured;$("#oauth-connect").textContent=state.connected?"다시 연결":"삼성 계정으로 연결";$("#oauth-disconnect").hidden=!state.connected;return state;}
action("#oauth-connect",async()=>{const result=await api("/smartthings/oauth/start","POST",{});location.assign(result.url);});
action("#oauth-disconnect",async()=>{if(confirm("Alter에 저장된 SmartThings 인증을 지울까요? 삼성 계정의 앱 권한은 별도로 철회할 수 있습니다.")){await api("/smartthings/oauth","DELETE");deviceList=[];$("#smart-devices").replaceChildren();await loadConnection();}});

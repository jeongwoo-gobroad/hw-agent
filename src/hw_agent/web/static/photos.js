/* Photo-only folders, timeline and editable local model suggestions. */
let photoOffset=0,photoPerson=0,photoSelected=null,photoTopics={},photoPeople=[],photoJobVersion="",photoQueryVersion=0;
const photoStage={idle:tr("대기"),discovering:tr("파일 확인 중"),classifying:tr("주제·얼굴 분류 중"),complete:tr("처리 완료"),paused:tr("일시정지"),error:tr("작업 중단")};
function etaText(seconds){if(seconds==null)return tr("ETA 계산 중");if(seconds<=0)return tr("남은 처리 없음");const m=Math.ceil(seconds/60);return tr("예상 약 ")+(m>=60?Math.floor(m/60)+tr("시간 ")+m%60+tr("분"):m+tr("분"))+tr(" 남음");}
function progressCounts(done,total){return tr("{{v0}} / {{v1}}개 · {{v2}}%", {v0: done.toLocaleString(window.alterLanguage), v1: total.toLocaleString(window.alterLanguage), v2: total?Math.min(100,100*done/total).toFixed(1):'0.0'});}
function photoCounters(s){return s.discovery_complete?[(s.processed_base||0)+(s.done||0),s.media_total||0]:[s.discovered||0,s.inventory_total||0];}
function photoProgress(s){const [done,total]=photoCounters(s);const phase=s.stage==='counting'?tr("전체 대상 집계 중"):s.discovery_complete?tr("주제·얼굴 분류"):tr("파일 정보 확인");const eta=s.stage==='waiting_for_storage'?tr("드라이브 연결 대기 · 자동 재개"):s.paused?tr("일시정지 · ETA 대기"):s.error||s.stage==='error'?tr("오류 확인 필요 · ETA 없음"):!s.worker_online?tr("작업자 연결 대기 · ETA 없음"):s.stage==='waiting'?tr("오류 항목 재시도 대기"):s.stage==='complete'?tr("처리 완료"):s.stage==='counting'?tr("ETA 집계 후 계산"):etaText(s.eta_seconds);return `${phase} · ${s.stage==='counting'?(total.toLocaleString(window.alterLanguage)+tr("개 발견")):progressCounts(done,total)} · ${eta}${s.errors?tr(" · 확인 필요 ")+s.errors+tr("개"):''}${!s.discovery_complete?tr(" · 분류 완료 ")+(s.classified_media||0).toLocaleString(window.alterLanguage)+tr("개"):''}`;}
window.photoDashboard=s=>{
  $("#photo-total").textContent=(s.photos.total_media||0).toLocaleString(window.alterLanguage);$("#photo-progress").textContent=photoProgress(s.photos);
  const [done,total]=photoCounters(s.photos);$("#photo-progress-bar").max=Math.max(1,total);if(s.photos.stage==='counting')$("#photo-progress-bar").removeAttribute('value');else $("#photo-progress-bar").value=done;
  const f=s.index;$('#scan-status').textContent=(f.stage==='counting'?tr("전체 대상 집계 중 · ")+(f.total||0).toLocaleString(window.alterLanguage)+tr("개 발견"):!f.total_known?tr("{{v0}}개 확인 · 현재 {{v1}}개 발견 · 나머지 폴더 집계 대기", {v0: (f.files||0).toLocaleString(window.alterLanguage), v1: (f.total||0).toLocaleString(window.alterLanguage)}):progressCounts(f.files||0,f.total||0))+(f.error?' · '+f.error:'')+(f.errors?tr(" · 확인 필요 ")+f.errors+tr("개"):'')+(f.retry_pending?tr(" · 자동 재시도 {{v0}}개", {v0:f.retry_pending.toLocaleString(window.alterLanguage)}):'');
  $('#file-eta').textContent=f.stage==='waiting_for_storage'?tr("드라이브 연결 대기 · 자동 재개"):f.error?tr("오류 확인 필요 · ETA 없음"):f.stage==='waiting_for_retry'?tr("오류 항목 재시도 대기"):f.stage==='complete'?tr("확인 완료"):f.stage==='finalizing'?tr("검색 색인 반영 중 · ETA 계산 대기"):!f.running?tr("대기 · ETA 없음"):!f.total_known?tr("전체 ETA는 모든 폴더 집계 후 계산"):etaText(f.eta_seconds);
  $('#file-progress-bar').max=Math.max(1,f.total||0);if(!f.total_known)$('#file-progress-bar').removeAttribute('value');else $('#file-progress-bar').value=f.files||0;
  $("#resource-load").textContent=`${s.resources.cpu_percent??"—"}% · ${s.resources.ram_percent}%`;
  $("#resource-temperature").textContent=`CPU ${s.resources.cpu_temperature==null?tr("계측 미지원"):s.resources.cpu_temperature+"°C"} · RAM ${s.resources.ram_temperature==null?tr("온도 센서 없음"):s.resources.ram_temperature+"°C"}`;
  $("#resource-gpu").textContent=s.resources.gpu_percent==null?(s.resources.gpu_source?tr("측정 중"):tr("계측 미지원")):s.resources.gpu_percent+"%";
  const engines=s.resources.gpu_engines||{};
  const gpuDetails=[["csd",tr("연산")],["render",tr("렌더")],["bin",tr("타일 준비")],["tfu",tr("텍스처")]].filter(([key])=>engines[key]!=null).map(([key,label])=>`${label} ${engines[key]}%`).join(" · ");
  $("#resource-gpu-note").textContent=[tr(s.resources.gpu_note||""),gpuDetails].filter(Boolean).join(" · ");
  $("#resource-gpu").title=s.resources.gpu_source||"";
  $("#photo-job").textContent=photoProgress(s.photos);
  const version=[s.photos.stage,s.photos.done,s.photos.discovered].join(":");
  if(version!==photoJobVersion&&!$("#photos").hidden&&!$("#photo-viewer").open&&photoOffset===0)searchPhotos().catch(e=>notify(e.message));
  photoJobVersion=version;
};
window.loadPhotoFolders=async()=>{
  const roots=await api("/photos/roots"),devices=await api("/devices");
  $("#photo-roots").replaceChildren();
  if(!roots.length)$("#photo-roots").append(el("p",tr("아직 등록된 사진 폴더가 없습니다."),"muted"));
  roots.forEach(r=>{const row=el("div",undefined,"root-row");row.append(el("span",`${r.path} · ${r.online?tr("연결됨"):tr("연결 끊김")}`),button(tr("사진 폴더 등록 해제"),async()=>{if(!confirm(tr("사진 색인에서만 제외할까요? 원본·파일 색인·SMB 공유는 유지됩니다.")))return;await api("/photos/roots/"+r.id,"DELETE");await loadPhotoFolders();}));$("#photo-roots").append(row);});
  $("#photo-drives").replaceChildren();devices.filter(d=>d.mount).forEach(d=>$("#photo-drives").append(button(d.model||d.name,()=>photoBrowse(d.mount))));
  if(!devices.some(d=>d.mount))$("#photo-drives").append(el("p",tr("연결된 외장 드라이브가 없습니다.")));
};
async function photoBrowse(path){
  const data=await api("/folders?path="+encodeURIComponent(path)),box=$("#photo-folder-browser");box.replaceChildren(el("p",data.path));
  const controls=el("div",undefined,"actions");
  if(data.path!==data.mount)controls.append(button(tr("상위 폴더"),()=>photoBrowse(data.path.slice(0,data.path.lastIndexOf("/")))));
  controls.append(button(tr("이 폴더를 사진 관리에 등록"),async()=>{await api("/photos/roots","POST",{path:data.path});await loadPhotoFolders();notify(tr("사진 전용 폴더로 등록했습니다. 자동 처리를 시작합니다."));}));box.append(controls);
  data.children.forEach(path=>box.append(button(path.split("/").pop(),()=>photoBrowse(path))));
}
window.loadPhotos=async()=>{
  const [state,albums,people,roots]=await Promise.all([api("/photos/status"),api("/photos/albums"),api("/photos/people"),api("/photos/roots")]);
  photoTopics=Object.fromEntries(Object.entries(state.topics).map(([k,v])=>[k,tr(v)]));photoPeople=people;
  const topics=$("#photo-search [name=topic]"),old=topics.value;topics.replaceChildren(new Option(tr("모든 주제"),""));Object.entries(photoTopics).forEach(([k,v])=>topics.add(new Option(v,k)));topics.value=old;
  const select=$("#photo-search [name=album_key]"),previous=select.value;select.replaceChildren(new Option(tr("전체 앨범"),""));
  albums.forEach(a=>select.add(new Option(`${roots.find(r=>r.id===a.root)?.label||tr("폴더")} / ${a.album==="."?tr("최상위"):a.album} (${a.count})`,JSON.stringify([a.root,a.album]))));select.value=previous;
  $("#photo-people").replaceChildren();
  if(!people.length)$("#photo-people").append(el("p",tr("분류된 얼굴이 아직 없습니다."),"muted"));
  people.forEach(p=>{const card=el("article",undefined,"card");const cover=el("img");cover.src=`/api/photos/faces/${p.cover_face}/thumbnail`;cover.alt=p.name||tr("사람 {{v0}}", {v0: p.id});cover.loading="lazy";card.append(cover,button(tr("{{v0}} · {{v1}}개", {v0: p.name||tr("사람 ")+p.id, v1: p.count}),async()=>{photoPerson=p.id;$("#photo-person-filter").textContent=p.name||tr("사람 {{v0}}", {v0: p.id});await searchPhotos();}));const name=el("input");name.value=p.name;name.placeholder=tr("이름 입력");name.maxLength=100;name.setAttribute("aria-label",tr("사람 {{v0}} 이름", {v0: p.id}));card.append(name,button(tr("이름 저장"),async()=>{await api("/photos/people/"+p.id,"PATCH",{name:name.value});await loadPhotos();}));$("#photo-people").append(card);});
  $("#photo-job").textContent=photoProgress(state);await searchPhotos();
};
async function searchPhotos(next=false){
  const queryVersion=++photoQueryVersion;if(!next)photoOffset=0;const form=new FormData($("#photo-search")),params=new URLSearchParams();
  for(const key of ["q","topic","kind","exclude"])if(form.get(key))params.set(key,form.get(key));
  if(form.get("album_key")){const [root,album]=JSON.parse(form.get("album_key"));params.set("root",root);params.set("album",album);}
  for(const key of ["after","before"])if(form.get(key))params.set(key,new Date(form.get(key)).getTime()/1000);
  params.set("person",photoPerson);params.set("offset",photoOffset);
  const result=await api("/photos/items?"+params);if(queryVersion!==photoQueryVersion)return;const grid=$("#photo-grid");if(!next)grid.replaceChildren();
  let lastMonth=grid.lastElementChild?.dataset.month;
  result.items.forEach(item=>{const month=new Date(item.captured*1000).toLocaleDateString(window.alterLanguage,{year:"numeric",month:"long"});if(lastMonth!==month){const title=el("h3",month,"photo-month");grid.append(title);lastMonth=month;}
    const card=button("",()=>viewPhoto(item),"photo-tile");card.dataset.month=month;card.setAttribute("aria-label",item.name+tr(" 열기"));const img=el("img");img.src=`/api/photos/items/${item.id}/thumbnail`;img.alt=item.name;img.loading="lazy";img.onerror=()=>{img.remove();card.prepend(el("span",item.error?tr("미리보기 오류"):tr("처리 대기"),"muted"));};
    card.append(img,el("span",item.name,"photo-caption"));if(item.kind!=="photo")card.append(el("span",item.kind==="live"?"LIVE":tr("동영상"),"photo-kind"));grid.append(card);
  });
  $("#photo-result-count").textContent=tr("{{v0}}개의 추억", {v0: result.total.toLocaleString(window.alterLanguage)});
  if(!result.total)grid.append(el("p",tr("사진 대상 폴더를 등록하거나 검색 조건을 바꿔 보세요."),"muted"));
  $("#photo-more").hidden=photoOffset+result.items.length>=result.total;
}
async function viewPhoto(item){
  photoSelected=item;const dialog=$("#photo-viewer");$("#photo-viewer-title").textContent=item.name;
  const box=$("#photo-media");box.replaceChildren();const media=el(item.kind==="video"?"video":"img");media.src=`/api/photos/items/${item.id}/media`;media.alt=item.name;if(item.kind==="video"){media.controls=true;media.preload="metadata";}box.append(media);
  $("#photo-detail").textContent=`${new Date(item.captured*1000).toLocaleString(window.alterLanguage)} · ${item.date_source} · ${item.album}${item.pair_source==="filename_candidate"?tr(" · Live Photo: 파일명·시각으로 추정 연결"):""}${item.error?tr(" · 처리 오류: ")+item.error:""}`;
  const actions=$("#photo-media-actions");actions.replaceChildren();
  const download=el("a",tr("원본 다운로드"),"button");download.href=`/api/photos/items/${item.id}/media?original=true`;actions.append(download);
  if(item.kind==="live")actions.append(button(tr("Live Photo 재생"),async()=>{box.replaceChildren();const video=el("video");video.controls=true;video.autoplay=true;video.src=`/api/photos/items/${item.id}/media?live=true`;box.append(video);}));
  $("#photo-labels").replaceChildren();Object.entries(photoTopics).forEach(([key,name])=>{const label=el("label",name,"check"),check=el("input");check.type="checkbox";check.name=key;check.checked=item.labels.includes(key);label.prepend(check);$("#photo-labels").append(label);});
  const faces=$("#photo-face-editor");faces.replaceChildren();
  if(!item.faces.length)faces.append(el("p",tr("감지된 얼굴이 없습니다.")));
  item.faces.forEach((f,i)=>{const row=el("div",undefined,"root-row"),select=el("select");select.setAttribute("aria-label",tr("얼굴 {{v0}} 사람", {v0: i+1}));select.add(new Option(tr("새 사람으로 분리"),"0"));photoPeople.forEach(p=>select.add(new Option(p.name||tr("사람 {{v0}}", {v0: p.id}),p.id)));select.value=f.person;const faceImage=el("img");faceImage.src=`/api/photos/faces/${f.id}/thumbnail`;faceImage.alt=tr("얼굴 {{v0}}", {v0: i+1});faceImage.width=64;faceImage.height=64;row.append(faceImage,el("span",tr("얼굴 {{v0}} · {{v1}}", {v0: i+1, v1: f.name||tr("사람 ")+f.person})),select,button(tr("얼굴 묶음 수정"),async()=>{await api("/photos/faces/"+f.id,"PATCH",{person:Number(select.value)});notify(tr("얼굴 묶음을 수정했습니다."));}));faces.append(row);});
  if(!dialog.open)dialog.showModal();
}
function closePhoto(){ $("#photo-media").querySelectorAll("video").forEach(v=>v.pause());$("#photo-media").replaceChildren();$("#photo-viewer").close(); }
action("#photo-viewer-close",async()=>closePhoto());$("#photo-viewer").addEventListener("cancel",closePhoto);
$("#photo-label-form").onsubmit=async e=>{e.preventDefault();try{const labels=[...$("#photo-labels").querySelectorAll("input:checked")].map(i=>i.name);await api("/photos/items/"+photoSelected.id,"PATCH",{labels});photoSelected.labels=labels;notify(tr("주제를 저장했습니다."));await searchPhotos();}catch(e){notify(e.message);}};
action("#photo-label-reset",async()=>{await api("/photos/items/"+photoSelected.id,"PATCH",{labels:null});closePhoto();await searchPhotos();});
$("#photo-search").onsubmit=e=>{e.preventDefault();searchPhotos().catch(e=>notify(e.message));};
action("#photo-reset",async()=>{$("#photo-search").reset();photoPerson=0;$("#photo-person-filter").textContent="";await searchPhotos();});
action("#photo-more",async()=>{photoOffset+=120;await searchPhotos(true);});
action("#photo-library-tab",async()=>{$("#photo-people").hidden=true;photoPerson=0;$("#photo-person-filter").textContent="";await loadPhotos();});
action("#photo-people-tab",async()=>{$("#photo-people").hidden=false;await loadPhotos();});
action("#photo-scan",async()=>{await api("/photos/scan","POST",{});notify(tr("사진 색인을 요청했습니다."));});
action("#photo-pause",async()=>{await api("/photos/pause","POST",{});notify(tr("현재 파일 처리 후 일시정지합니다. ‘지금 색인’으로 재개할 수 있습니다."));});
action("#photo-refresh-drives",loadPhotoFolders);

window.photoChatCards=items=>{const grid=el('div',undefined,'photo-grid');items.forEach(item=>{const card=button('',async()=>{const [state,people]=await Promise.all([api('/photos/status'),api('/photos/people')]);photoTopics=Object.fromEntries(Object.entries(state.topics).map(([k,v])=>[k,tr(v)]));photoPeople=people;await viewPhoto(item);},'photo-tile');const image=el('img');image.src=`/api/photos/items/${item.id}/thumbnail`;image.alt=item.name;image.loading='lazy';card.append(image,el('span',item.name,'photo-caption'));grid.append(card);});return grid;};

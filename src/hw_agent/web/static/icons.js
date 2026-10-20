/* Icons supplement text labels and inherit the active theme. */
(() => {
  const pages={overview:"layout-dashboard",files:"files",chat:"messages-square",drives:"hard-drive",home:"house",camera:"camera",settings:"settings"};
  const rules=[[/키보드 닫기/,"keyboard"],[/새 대화/,"message-circle-plus"],[/대화 목록/,"history"],[/챗봇|얼터.*물어/,"messages-square"],[/우리 집|스마트홈/,"house"],[/호출 대기/,"audio-lines"],[/음성|녹음/,"mic"],[/다크 모드/,"moon"],[/라이트 모드/,"sun"],[/로그아웃/,"log-out"],[/로그인|삼성 계정/,"log-in"],[/공유 해제/,"unlink"],[/공유/,"network"],[/안전하게 해제/,"eject"],[/마운트/,"hard-drive-download"],[/폴더|파일 찾아/,"folder-search"],[/미리보기|상태 확인/,"eye"],[/다운로드|내보내기/,"download"],[/녹화 중지|중단/,"square"],[/녹화 시작/,"circle-dot"],[/카메라 끄기/,"camera-off"],[/카메라 켜기/,"camera"],[/새로고침|색인/,"refresh-cw"],[/초기화/,"rotate-ccw"],[/검색/,"search"],[/보내기/,"send"],[/Flow 만들기/,"workflow"],[/실행|명령/,"play"],[/편집|이름 변경/,"pencil"],[/복제/,"copy"],[/삭제|제거/,"trash-2"],[/켜기/,"power"],[/끄기/,"power-off"],[/추가/,"plus"],[/저장|적용/,"check"],[/닫기|취소/,"x"],[/다음/,"chevron-right"],[/대시보드/,"layout-dashboard"]];
  let queued=false;
  const observer=new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(decorate);}});
  function decorate(){
    queued=false;observer.disconnect();
    document.querySelectorAll('button,a.button,.panel-dock a').forEach(node=>{
      if(node.closest('.simple-keyboard')||node.querySelector('svg')||node.querySelector('img'))return;
      const icon=pages[node.dataset.page||node.dataset.go]||rules.find(([pattern])=>pattern.test(node.textContent))?.[1];
      if(!icon)return;
      const glyph=document.createElement('i');glyph.dataset.lucide=icon;glyph.setAttribute('aria-hidden','true');node.prepend(glyph);
    });
    lucide.createIcons({attrs:{class:'ui-icon',width:19,height:19,stroke:'currentColor','stroke-width':1.8,'aria-hidden':'true',focusable:'false'}});
    observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  }
  decorate();
})();

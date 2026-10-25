async function loadSettings(){await Promise.all([loadCameraOrientation(),loadLoginPolicy()]);}
function displayLoginPolicy(policy){
  for(const name of ['max_failures','block_minutes','window_minutes'])document.querySelector(`#security-${name}`).value=policy[name];
  document.querySelector('#security-summary').textContent=`같은 접속 주소에서 ${policy.window_minutes}분 동안 ${policy.max_failures}회 실패하면 ${policy.block_minutes}분간 차단합니다.`;
  document.querySelector('#security-save').disabled=false;
}
async function loadLoginPolicy(){displayLoginPolicy(await api('/settings/security'));}
document.querySelector('#security-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const button=document.querySelector('#security-save'),status=document.querySelector('#security-status');
  button.disabled=true;status.textContent='저장 중…';
  try{
    const policy=Object.fromEntries(new FormData(event.target).entries());
    Object.keys(policy).forEach(key=>policy[key]=Number(policy[key]));
    displayLoginPolicy(await api('/settings/security','PUT',policy));
    status.textContent='저장했습니다. 다음 로그인 시도부터 적용됩니다.';
  }catch(error){status.textContent=error.message;}
  finally{button.disabled=false;}
});

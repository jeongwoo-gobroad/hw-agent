const form=document.querySelector('#login'),submit=form.querySelector('button[type="submit"]');
const errorText=document.querySelector('#error'),captchaBox=document.querySelector('#captcha-box');
let blockedUntil=0,publicLogin=false,ready=false;
function block(response){if(response.status===429)blockedUntil=Date.now()+Number(response.headers.get('Retry-After')||1)*1000;}
async function refreshChallenge(){
  ready=false;submit.disabled=true;
  try{
    const response=await fetch('/api/login/challenge',{cache:'no-store'}),result=await response.json();
    if(!response.ok){block(response);throw new Error(result.detail);}
    publicLogin=result.required;captchaBox.hidden=!publicLogin;
    form.elements.captcha.required=publicLogin;
    form.elements.captcha.value='';form.elements.challenge_id.value=result.id||'';
    if(publicLogin)document.querySelector('#captcha-image').src=result.image;
    document.querySelector('#http-note').hidden=!publicLogin||location.protocol==='https:';
    ready=true;
  }catch(error){errorText.textContent=error.message;}
  finally{submit.disabled=!ready||Date.now()<blockedUntil;}
}
document.querySelector('#captcha-refresh').onclick=()=>refreshChallenge();
setInterval(()=>{
  if(!blockedUntil)return;
  const seconds=Math.ceil((blockedUntil-Date.now())/1000);
  submit.disabled=seconds>0;document.querySelector('#retry-status').textContent=seconds>0?`${seconds}초 후 다시 시도할 수 있습니다.`:'';
  if(seconds<=0){blockedUntil=0;refreshChallenge();}
},1000);
form.addEventListener('submit',async event=>{
  event.preventDefault();if(!ready||Date.now()<blockedUntil)return;
  submit.disabled=true;errorText.textContent='';
  try{
    const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});
    const result=await response.json();
    if(!response.ok){block(response);throw new Error(typeof result.detail==='string'?result.detail:'입력 내용을 확인하세요.');}
    location.href=new URLSearchParams(location.search).get('next')==='/panel'?'/panel':'/';
  }catch(error){errorText.textContent=error.message;if(publicLogin&&!blockedUntil)await refreshChallenge();submit.disabled=!ready||Date.now()<blockedUntil;}
});
refreshChallenge();

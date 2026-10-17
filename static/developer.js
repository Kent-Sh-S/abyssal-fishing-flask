'use strict';
(() => {
  const app = document.getElementById('developer-app');
  const feedback = document.getElementById('developer-feedback');
  const csrf = app.dataset.csrf;
  let busy = false;
  function message(text, error=false) {
    feedback.hidden = false;
    feedback.classList.toggle('error',error);
    feedback.textContent=text;
  }
  async function send(path, method='GET', body) {
    const headers = method==='GET' ? {} : {'X-CSRF-Token':csrf,'Content-Type':'application/json'};
    const response=await fetch(path,{method,headers,credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
    if(response.status===401) window.location.assign('/login');
    const data=await response.json();
    if(!response.ok) throw new Error(data.error || '操作失败，请稍后重试');
    return data;
  }
  const date = value => value ? new Date(value*1000).toLocaleString('zh-CN') : '尚未使用';
  async function loadKeys() {
    const data=await send('/developer/keys');
    const body=document.getElementById('key-list');
    body.replaceChildren();
    if(!data.keys.length) {
      const row=document.createElement('tr'), cell=document.createElement('td');
      cell.colSpan=5;cell.className='dev-empty';cell.textContent='还没有 User Key。创建第一枚 Key，开始调用深海接口。';row.append(cell);body.append(row);
    }
    for(const key of data.keys) {
      const row=document.createElement('tr');
      for(const value of [key.name,key.prefix,date(key.last_used_at),key.revoked_at?'已吊销':'有效']) {
        const cell=document.createElement('td');cell.textContent=value;row.append(cell);
      }
      const cell=document.createElement('td');
      if(!key.revoked_at) {
        const button=document.createElement('button');button.className='dev-revoke-button';button.dataset.revokeKey=key.id;button.textContent='吊销';button.disabled=busy;cell.append(button);
      } else {cell.textContent='—';}
      row.append(cell);body.append(row);
    }
  }
  document.getElementById('join-developer-button')?.addEventListener('click',async event=>{
    if(busy)return;busy=true;event.target.disabled=true;
    try {await send('/developer/join','POST',{});window.location.reload();}
    catch(error){message(error.message,true);busy=false;event.target.disabled=false;}
  });
  document.getElementById('create-key-form')?.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;busy=true;
    const button=document.getElementById('create-key-button');button.disabled=true;
    try {
      const data=await send('/developer/keys','POST',{name:document.getElementById('key-name').value});
      document.getElementById('new-key-value').value=data.key.value;
      document.getElementById('new-key-panel').hidden=false;
      message('User Key 已创建。请复制保存；完整 Key 仅显示这一次。');
      await loadKeys();
    } catch(error){message(error.message,true);}
    finally {busy=false;button.disabled=false;document.querySelectorAll('[data-revoke-key]').forEach(b=>b.disabled=false);}
  });
  document.getElementById('key-list')?.addEventListener('click',async event=>{
    const button=event.target.closest('[data-revoke-key]');if(!button||busy)return;
    busy=true;button.disabled=true;
    try {await send('/developer/keys/'+encodeURIComponent(button.dataset.revokeKey)+'/revoke','POST',{});message('User Key 已吊销，后续调用将返回 401。');await loadKeys();}
    catch(error){message(error.message,true);}
    finally {busy=false;document.querySelectorAll('[data-revoke-key]').forEach(b=>b.disabled=false);}
  });
  document.getElementById('hide-new-key')?.addEventListener('click',()=>{
    document.getElementById('new-key-value').value='';document.getElementById('new-key-panel').hidden=true;
  });
  document.getElementById('copy-key-button')?.addEventListener('click',async()=>{
    const input=document.getElementById('new-key-value');
    try {await navigator.clipboard.writeText(input.value);message('User Key 已复制。');}
    catch(_){input.select();message('请手动复制已选中的 User Key。');}
  });
  if(app.dataset.enabled==='true') loadKeys().catch(error=>message(error.message,true));
})();

'use strict';
(() => {
  const form = document.getElementById('auth-form');
  let mode = 'login', busy = false, csrf = form.dataset.csrf;
  const submit = document.getElementById('auth-submit');
  function label() { submit.innerHTML = mode === 'login' ? '登录并继续航行 <span>→</span>' : '注册并开启航程 <span>→</span>'; }
  document.querySelectorAll('[data-auth-mode]').forEach(button => button.addEventListener('click', () => {
    if (busy) return;
    mode = button.dataset.authMode;
    document.querySelectorAll('[data-auth-mode]').forEach(b => b.classList.toggle('active', b === button));
    document.getElementById('auth-title').textContent = mode === 'login' ? '欢迎返航，潜航员。' : '深海，需要一个新名字。';
    document.getElementById('password').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
    document.getElementById('developer-opt').hidden = mode !== 'register';
    document.getElementById('auth-error').textContent = ''; label();
  }));
  document.getElementById('show-password').addEventListener('click', event => {
    const password = document.getElementById('password');
    const show = password.type === 'password'; password.type = show ? 'text' : 'password';
    event.target.textContent = show ? '隐藏' : '显示'; event.target.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    busy = true; submit.disabled = true; submit.textContent = '正在接入航行档案…';
    document.getElementById('auth-error').textContent = '';
    try {
      const response = await fetch('/auth/' + mode, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({username: document.getElementById('username').value, password: document.getElementById('password').value, developer_plan: mode === 'register' && document.getElementById('developer-plan').checked})});
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 403) { const renewed = await fetch('/auth/csrf', {cache:'no-store'}); csrf = (await renewed.json()).csrf; }
        throw new Error(result.error || '无法登录，请稍后再试');
      }
      window.location.assign(result.redirect);
    } catch (error) { document.getElementById('auth-error').textContent = error.message; }
    finally { busy = false; submit.disabled = false; label(); }
  });
})();

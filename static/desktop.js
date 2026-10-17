'use strict';
document.querySelectorAll('[data-desktop-quit]').forEach(button => {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const tokenResponse = await fetch('/auth/csrf', {cache:'no-store'});
      const {csrf} = await tokenResponse.json();
      const response = await fetch('/desktop/quit', {method:'POST', headers:{'X-CSRF-Token':csrf}});
      if (!response.ok) throw new Error('无法退出，请重试');
      document.body.textContent = '深渊渔场已退出，存档已保留。现在可以关闭此页面。';
    } catch (error) {
      button.disabled = false;
      button.textContent = error.message;
    }
  });
});

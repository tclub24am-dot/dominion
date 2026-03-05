(() => {
  // Не показывать кнопку на главной странице (neural-core / dashboard)
  const isMainPage = window.location.pathname === '/' 
    || window.location.pathname === '/neural-core'
    || window.location.pathname === '/dashboard';
  if (isMainPage) return;
  
  const existing = document.getElementById('globalBackBtn');
  if (existing) return;
  
  const btn = document.createElement('button');
  btn.id = 'globalBackBtn';
  btn.type = 'button';
  btn.textContent = '← Назад';
  btn.onclick = () => {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = '/';
    }
  };
  const style = document.createElement('style');
  style.textContent = `
    #globalBackBtn {
      position: fixed;
      top: 16px;
      left: 16px;
      z-index: 100;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid rgba(212,175,55,0.5);
      background: rgba(13,12,11,0.9);
      color: #f7f4ee;
      font-family: 'Montserrat', sans-serif;
      font-size: 11px;
      letter-spacing: 0.04em;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      cursor: pointer;
    }
    #globalBackBtn:hover {
      box-shadow: 0 0 10px rgba(212,175,55,0.5);
    }
  `;
  document.head.appendChild(style);
  document.body.appendChild(btn);
})();

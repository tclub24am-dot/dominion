/**
 * S-GLOBAL DOMINION — ПРОТОКОЛ «ВЕЧНЫЙ МОСТ»
 * Сквозные UI-компоненты: Imperial Console, S-GLOBAL FAB, Messenger, Oracle Modal
 * Инжектируются на ВСЕ страницы Империи автоматически.
 */
(() => {
  'use strict';

  /* ── CSS ──────────────────────────────────────────────────── */
  const STYLE = `
  /* IMPERIAL CONSOLE */
  .imperial-console{position:fixed;bottom:0;left:0;right:0;height:48px;background:#0D0C0B;border-top:1px solid #f7f4ee;display:flex;align-items:center;justify-content:center;gap:8px;z-index:1000;padding:0 12px;font-family:'Montserrat',sans-serif;}
  .imperial-console .console-btn{color:rgba(247,244,238,0.85);text-decoration:none;font-size:12px;letter-spacing:0.06em;padding:8px 14px;border-radius:8px;border:1px solid rgba(247,244,238,0.3);transition:background 0.2s,color 0.2s,border-color 0.2s;background:transparent;cursor:pointer;font-family:inherit;}
  .imperial-console .console-btn:hover{background:rgba(247,244,238,0.1);color:#f7f4ee;border-color:#f7f4ee;}

  /* S-GLOBAL FAB */
  .sglobal-fab{position:fixed;right:24px;bottom:70px;width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,#D4AF37,#B8860B);display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:1100;box-shadow:0 4px 20px rgba(212,175,55,0.4);transition:transform 0.2s,box-shadow 0.2s;font-family:'Orbitron',sans-serif;}
  .sglobal-fab:hover{transform:scale(1.1);box-shadow:0 6px 28px rgba(212,175,55,0.6);}
  .fab-logo{font-size:20px;font-weight:700;color:#0D0C0B;}
  .fab-badge{position:absolute;top:-4px;right:-4px;background:#ff5252;color:#fff;font-size:10px;min-width:18px;height:18px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:700;}

  /* MESSENGER WIDGET */
  .messenger-widget{position:fixed;right:18px;bottom:130px;width:360px;height:440px;background:rgba(13,12,11,0.92);border:1px solid rgba(212,175,55,0.3);border-radius:16px;display:none;flex-direction:column;z-index:1099;box-shadow:0 12px 40px rgba(0,0,0,0.5);backdrop-filter:blur(12px);font-family:'Montserrat',sans-serif;}
  .messenger-header{padding:10px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(212,175,55,0.3);}
  .messenger-header strong{color:#f7f4ee;font-size:13px;}
  .messenger-body{flex:1;padding:10px;overflow:auto;font-size:12px;color:#e8eaf6;}
  .messenger-input{padding:10px;border-top:1px solid rgba(212,175,55,0.3);display:flex;gap:6px;}
  .messenger-input input{flex:1;background:transparent;border:1px solid rgba(212,175,55,0.3);color:#e8eaf6;border-radius:8px;padding:6px;font-family:inherit;font-size:12px;}
  .messenger-input button{border:1px solid rgba(212,175,55,0.3);background:transparent;color:#e8eaf6;border-radius:8px;padding:6px 8px;cursor:pointer;font-size:12px;}
  .msg-btn{border:1px solid rgba(212,175,55,0.3);background:transparent;color:#e8eaf6;border-radius:8px;padding:4px 8px;cursor:pointer;font-size:11px;margin-left:4px;}
  .attach-input{display:none;}

  /* ORACLE MODAL */
  .oracle-modal{position:fixed;inset:0;background:rgba(6,8,12,0.88);display:none;align-items:flex-start;justify-content:center;z-index:2000;backdrop-filter:blur(12px);font-family:'Montserrat',sans-serif;}
  .oracle-modal.active{display:flex;}
  .oracle-modal-inner{width:700px;max-width:95vw;margin-top:10vh;background:rgba(18,21,40,0.92);border:1px solid rgba(212,175,55,0.35);border-radius:18px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,0.5);}
  .oracle-modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;}
  .oracle-search-input{width:100%;background:transparent;border:1px solid rgba(212,175,55,0.4);color:#e8eaf6;border-radius:12px;padding:14px 16px;font-size:15px;letter-spacing:0.04em;outline:none;font-family:inherit;}
  .oracle-search-input:focus{border-color:#d4af37;box-shadow:0 0 12px rgba(212,175,55,0.2);}
  .oracle-dropdown{margin-top:8px;max-height:50vh;overflow:auto;}
  .oracle-dropdown:empty{display:none;}
  .oracle-result{display:block;padding:12px 14px;color:#e8eaf6;text-decoration:none;font-size:12px;border-bottom:1px solid rgba(255,255,255,0.08);transition:background 0.15s;}
  .oracle-result:hover{background:rgba(212,175,55,0.1);}
  .btn-ghost{border:1px solid rgba(255,255,255,0.08);background:transparent;color:#e8eaf6;border-radius:10px;padding:6px 10px;font-size:11px;cursor:pointer;}
  `;

  /* ── SKIP INJECTION IF ALL COMPONENTS ALREADY EXIST ───────── */
  const hasConsole  = !!document.getElementById('imperialConsole');
  const hasFab      = !!document.getElementById('sglobalFab');
  const hasOracle   = !!document.getElementById('oracleModal');
  const hasMsgr     = !!document.getElementById('messengerWidget');
  if (hasConsole && hasFab && hasOracle && hasMsgr) return; // fleet.html — уже всё есть

  /* ── INJECT CSS ──────────────────────────────────────────── */
  const styleEl = document.createElement('style');
  styleEl.id = 'globalUiStyle';
  styleEl.textContent = STYLE;
  document.head.appendChild(styleEl);

  /* ── IMPERIAL CONSOLE ────────────────────────────────────── */
  if (!hasConsole) {
    const oldConsole = document.querySelector('nav.imperial-console');
    if (oldConsole) oldConsole.remove(); // Remove old-style console

    const nav = document.createElement('nav');
    nav.className = 'imperial-console';
    nav.id = 'imperialConsole';
    nav.innerHTML = `
      <button class="console-btn" id="consoleSearchBtn" title="Глаз Оракула">🔎 ПОИСК</button>
      <a href="mailto:" class="console-btn" title="Email">📧 EMAIL</a>
      <a href="/fleet/notes" class="console-btn" title="Записная книжка">📒 КНИЖКА</a>
      <a href="/ai-reports" class="console-btn" title="AI Отчеты">🤖 AI</a>
      <a href="/neural-core" class="console-btn" title="MindMap">🧠 MINDMAP</a>
      <a href="/fleet" class="console-btn" title="Командная башня">🏰 ФЛОТ</a>
      <a href="/fleet/contract-matrix" class="console-btn">📊 МАТРИЦА</a>
      <a href="/settings" class="console-btn">⚙️</a>
    `;
    document.body.appendChild(nav);
  }

  /* ── ORACLE MODAL ────────────────────────────────────────── */
  if (!hasOracle) {
    const modal = document.createElement('div');
    modal.className = 'oracle-modal';
    modal.id = 'oracleModal';
    modal.innerHTML = `
      <div class="oracle-modal-inner">
        <div class="oracle-modal-header">
          <span style="font-family:'Orbitron',sans-serif;font-size:14px;letter-spacing:0.12em;color:#f7f4ee;">ГЛАЗ ОРАКУЛА</span>
          <button class="btn-ghost" id="closeOracleModal">✕</button>
        </div>
        <input type="text" id="globalSearchInput" class="oracle-search-input" placeholder="Поиск: госномер, VIN, ФИО, запчасть, план..." autofocus>
        <div id="globalOracleDropdown" class="oracle-dropdown"></div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  /* ── S-GLOBAL FAB ────────────────────────────────────────── */
  if (!hasFab) {
    const fab = document.createElement('div');
    fab.className = 'sglobal-fab';
    fab.id = 'sglobalFab';
    fab.title = 'S-GLOBAL Messenger';
    fab.innerHTML = `
      <span class="fab-logo">S</span>
      <span class="fab-badge" id="fabBadge" style="display:none;">0</span>
    `;
    document.body.appendChild(fab);
  }

  /* ── MESSENGER WIDGET ────────────────────────────────────── */
  if (!hasMsgr) {
    const widget = document.createElement('div');
    widget.className = 'messenger-widget';
    widget.id = 'messengerWidget';
    widget.innerHTML = `
      <div class="messenger-header">
        <strong id="messengerTitle">S-GLOBAL Messenger</strong>
        <div>
          <button class="msg-btn" id="aiButton" title="AI помощник">AI</button>
          <button class="msg-btn" id="closeMessenger">✕</button>
        </div>
      </div>
      <div class="messenger-body" id="messengerBody">
        <div>Контекстный канал активен. AI-интеграция готова.</div>
      </div>
      <div class="messenger-input">
        <input id="messengerInput" placeholder="Сообщение...">
        <button id="micButton">🎙️</button>
        <button id="attachButton">📎</button>
        <button id="sendMessage">→</button>
        <input type="file" id="attachInput" class="attach-input" multiple>
      </div>
    `;
    document.body.appendChild(widget);
  }

  /* ── ENSURE BODY PADDING FOR CONSOLE ─────────────────────── */
  document.body.style.paddingBottom = Math.max(
    parseInt(getComputedStyle(document.body).paddingBottom) || 0,
    56
  ) + 'px';

  /* ── EVENT BINDINGS ──────────────────────────────────────── */

  // FAB toggle
  const fabEl = document.getElementById('sglobalFab');
  if (fabEl) {
    fabEl.onclick = () => {
      const w = document.getElementById('messengerWidget');
      if (!w) return;
      w.style.display = w.style.display === 'flex' ? 'none' : 'flex';
    };
  }

  // Messenger close
  const closeMsg = document.getElementById('closeMessenger');
  if (closeMsg) {
    closeMsg.onclick = () => {
      const w = document.getElementById('messengerWidget');
      if (w) w.style.display = 'none';
    };
  }

  // Oracle Modal open/close
  const searchBtn  = document.getElementById('consoleSearchBtn');
  const oracleM    = document.getElementById('oracleModal');
  const closeOrBtn = document.getElementById('closeOracleModal');
  const oracleInp  = document.getElementById('globalSearchInput');

  if (searchBtn && oracleM) {
    searchBtn.addEventListener('click', e => {
      e.preventDefault();
      oracleM.classList.add('active');
      if (oracleInp) setTimeout(() => oracleInp.focus(), 100);
    });
  }
  if (closeOrBtn && oracleM) {
    closeOrBtn.addEventListener('click', () => oracleM.classList.remove('active'));
  }
  if (oracleM) {
    oracleM.addEventListener('click', e => { if (e.target === oracleM) oracleM.classList.remove('active'); });
  }
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && oracleM && oracleM.classList.contains('active')) oracleM.classList.remove('active');
  });

  // Oracle search (global — API-based)
  if (oracleInp) {
    let timer = null;
    const dropdown = document.getElementById('globalOracleDropdown');
    oracleInp.addEventListener('input', e => {
      const q = (e.target.value || '').trim();
      if (dropdown && q.length < 2) { dropdown.style.display = 'none'; dropdown.innerHTML = ''; return; }
      clearTimeout(timer);
      timer = setTimeout(async () => {
        try {
          const r = await fetch('/api/v1/fleet/oracle-search?q=' + encodeURIComponent(q), { credentials: 'include' });
          const data = await r.json();
          const results = data.results || [];
          if (!results.length) {
            dropdown.innerHTML = '<div style="padding:12px;color:#9aa5ce;font-size:11px;">Ничего не найдено</div>';
          } else {
            dropdown.innerHTML = results.map(item =>
              '<a href="' + item.url + '" class="oracle-result">' +
              (item.type === 'vehicle' ? '🚗 ' : '👤 ') + (item.label || '') + '</a>'
            ).join('');
            dropdown.querySelectorAll('.oracle-result').forEach(el => {
              el.addEventListener('click', () => { if (oracleM) oracleM.classList.remove('active'); });
            });
          }
          dropdown.style.display = 'block';
        } catch { if (dropdown) dropdown.style.display = 'none'; }
      }, 280);
    });
    oracleInp.addEventListener('focus', () => { if (dropdown && dropdown.innerHTML) dropdown.style.display = 'block'; });
    oracleInp.addEventListener('blur', () => { setTimeout(() => { if (dropdown) dropdown.style.display = 'none'; }, 180); });
  }

  // Hash #search opens oracle
  if (window.location.hash === '#search' && oracleM) {
    oracleM.classList.add('active');
    if (oracleInp) setTimeout(() => oracleInp.focus(), 100);
  }

  // Mic button (speech recognition)
  const micBtn = document.getElementById('micButton');
  if (micBtn && 'webkitSpeechRecognition' in window) {
    micBtn.onclick = () => {
      const rec = new webkitSpeechRecognition();
      rec.lang = 'ru-RU';
      rec.onresult = e => {
        const text = e.results[0][0].transcript;
        const input = document.getElementById('messengerInput');
        if (input) input.value = text;
      };
      rec.start();
    };
  }

  // Attach button
  const attachBtn = document.getElementById('attachButton');
  const attachInp = document.getElementById('attachInput');
  if (attachBtn && attachInp) {
    attachBtn.onclick = () => attachInp.click();
    attachInp.onchange = () => {
      if (!attachInp.files.length) return;
      const body = document.getElementById('messengerBody');
      const form = new FormData();
      form.append('file', attachInp.files[0]);
      form.append('channel', 'ФЛОТ');
      fetch('/api/v1/messenger/upload', { method: 'POST', body: form })
        .then(r => r.json())
        .then(() => { if (body) body.innerHTML += '<div>📎 Файл отправлен</div>'; });
    };
  }

  /* ── PUBLIC API (for page-specific hooks) ────────────────── */
  window.GlobalUI = {
    openOracle() { if (oracleM) { oracleM.classList.add('active'); if (oracleInp) setTimeout(() => oracleInp.focus(), 100); } },
    closeOracle() { if (oracleM) oracleM.classList.remove('active'); },
    openMessenger(title) {
      const w = document.getElementById('messengerWidget');
      const t = document.getElementById('messengerTitle');
      if (t && title) t.textContent = title;
      if (w) w.style.display = 'flex';
    },
    closeMessenger() {
      const w = document.getElementById('messengerWidget');
      if (w) w.style.display = 'none';
    },
    setBadge(n) {
      const b = document.getElementById('fabBadge');
      if (!b) return;
      if (n > 0) { b.textContent = n; b.style.display = 'flex'; }
      else { b.style.display = 'none'; }
    },
  };

})();

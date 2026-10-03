/**
 * Chat Module — Delux Radio
 * Full-featured live chat: emoji picker, unread badge, typing indicator,
 * online users, reactions, and robust WebSocket integration.
 */

const Chat = (() => {
  let _ws       = null;
  let _username = '';
  let _clientId = '';
  let _isOpen   = false;
  let _unread   = 0;
  let _typingTimer = null;
  let _typingUsers = new Set();   // display_names currently typing
  let _typingTimeout = null;
  let _eventsbound = false;

  /* ── Quick emoji list ────────────────────────────────────────────────────── */
  const QUICK_EMOJIS = ['❤️','😭','😂','🥹','🎵','🔥','💯','👏','😍','🥰','😢','✨'];

  const $ = id => document.getElementById(id);

  /* ── Init ─────────────────────────────────────────────────────────────────── */
  function init(wsInstance, uname, cid) {
    _username = uname || _username;
    _clientId = cid  || _clientId;
    if (wsInstance) _ws = wsInstance;

    if (!_eventsbound) {
      _buildEmojiBar();
      _bindEvents();
      _eventsbound = true;
    }
  }

  /* Update WS reference after reconnect without re-binding events */
  function setWs(wsInstance) {
    _ws = wsInstance;
  }

  /* ── Build emoji quick-bar ────────────────────────────────────────────────── */
  function _buildEmojiBar() {
    const area = $('chat-input-area');
    if (!area || $('emoji-bar')) return;

    const bar = document.createElement('div');
    bar.id = 'emoji-bar';
    bar.className = 'emoji-bar';
    bar.setAttribute('aria-label', 'Quick emoji');

    QUICK_EMOJIS.forEach(em => {
      const btn = document.createElement('button');
      btn.className = 'emoji-btn';
      btn.textContent = em;
      btn.type = 'button';
      btn.setAttribute('aria-label', `Insert ${em}`);
      btn.addEventListener('click', () => {
        const input = $('chat-input');
        if (!input) return;
        const pos = input.selectionStart ?? input.value.length;
        input.value = input.value.slice(0, pos) + em + input.value.slice(pos);
        input.focus();
        input.selectionStart = input.selectionEnd = pos + em.length;
        _updateCharCount();
      });
      bar.appendChild(btn);
    });

    // Insert emoji bar before the input row
    const row = area.querySelector('.chat-input-row');
    area.insertBefore(bar, row);
  }

  /* ── Bind events ──────────────────────────────────────────────────────────── */
  function _bindEvents() {
    const sendBtn = $('btn-send-chat');
    const input   = $('chat-input');
    const openBtn = $('btn-open-chat');
    const closeBtn= $('btn-close-chat');

    sendBtn?.addEventListener('click', _sendMessage);

    input?.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        _sendMessage();
      }
    });

    input?.addEventListener('input', () => {
      _updateCharCount();
      _sendTyping();
    });

    openBtn?.addEventListener('click', _openPanel);
    closeBtn?.addEventListener('click', _closePanel);

    // Close on backdrop click (when panel is overlaying)
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && _isOpen) _closePanel();
    });

    // Char count
    _buildCharCount();
  }

  /* ── Char count label ─────────────────────────────────────────────────────── */
  function _buildCharCount() {
    const row = document.querySelector('.chat-input-row');
    if (!row || $('chat-char-count')) return;
    const label = document.createElement('div');
    label.id = 'chat-char-count';
    label.className = 'chat-char-count';
    label.textContent = '';
    row.appendChild(label);
  }

  function _updateCharCount() {
    const input = $('chat-input');
    const label = $('chat-char-count');
    if (!input || !label) return;
    const len = input.value.length;
    label.textContent = len > 200 ? `${len}/300` : '';
    label.style.color = len > 270 ? '#ef4444' : 'rgba(255,255,255,0.3)';
  }

  /* ── Open / Close ─────────────────────────────────────────────────────────── */
  function _openPanel() {
    $('chat-panel')?.classList.add('open');
    _isOpen = true;
    _clearUnread();
    setTimeout(() => $('chat-input')?.focus(), 300);
  }

  function _closePanel() {
    $('chat-panel')?.classList.remove('open');
    _isOpen = false;
  }

  /* ── Unread badge ─────────────────────────────────────────────────────────── */
  function _incUnread() {
    if (_isOpen) return;
    _unread++;
    _renderBadge();
  }

  function _clearUnread() {
    _unread = 0;
    _renderBadge();
  }

  function _renderBadge() {
    const btn = $('btn-open-chat');
    if (!btn) return;
    let badge = btn.querySelector('.chat-badge');
    if (_unread > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'chat-badge';
        btn.appendChild(badge);
      }
      badge.textContent = _unread > 9 ? '9+' : _unread;
    } else {
      badge?.remove();
    }
  }

  /* ── Typing indicator ─────────────────────────────────────────────────────── */
  function _sendTyping() {
    if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
    _ws.send(JSON.stringify({ type: 'typing' }));

    clearTimeout(_typingTimer);
    _typingTimer = setTimeout(() => {
      if (_ws?.readyState === WebSocket.OPEN) {
        _ws.send(JSON.stringify({ type: 'stop_typing' }));
      }
    }, 2500);
  }

  function _showTyping(names) {
    let el = $('typing-indicator');
    if (!el) {
      el = document.createElement('div');
      el.id = 'typing-indicator';
      el.className = 'typing-indicator';
      const msgs = $('chat-messages');
      msgs?.parentNode?.insertBefore(el, msgs.nextSibling);
    }
    if (names.size === 0) {
      el.classList.remove('visible');
    } else {
      const list = [...names].slice(0, 2);
      const suffix = list.length === 1 ? 'is typing…' : 'are typing…';
      el.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span> ${_esc(list.join(', '))} ${suffix}`;
      el.classList.add('visible');
    }
  }

  /* ── Send message ─────────────────────────────────────────────────────────── */
  function _sendMessage() {
    const input = $('chat-input');
    const msg   = input?.value?.trim();
    if (!msg) return;
    if (!_ws || _ws.readyState !== WebSocket.OPEN) {
      renderError('Not connected. Please wait…');
      return;
    }
    _ws.send(JSON.stringify({ type: 'chat', message: msg }));
    input.value = '';
    _updateCharCount();
    // stop typing
    clearTimeout(_typingTimer);
    if (_ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'stop_typing' }));
    }
  }

  /* ── Render a message ─────────────────────────────────────────────────────── */
  function renderMessage(data) {
    const container = $('chat-messages');
    if (!container) return;

    // Remove "be first" placeholder
    const placeholder = container.querySelector('[data-placeholder]');
    placeholder?.remove();

    const isOwn = data.client_id === _clientId;
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${isOwn ? 'chat-bubble--own' : ''}`;
    bubble.dataset.msgId = data.id || '';

    const ts = data.ts ? new Date(data.ts) : new Date();
    const timeStr = ts.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });

    // Avatar letter
    const initial = (data.display_name || '?')[0].toUpperCase();
    const avatarColor = _nameToColor(data.display_name || '');

    bubble.innerHTML = `
      ${!isOwn ? `<div class="bubble-avatar" style="background:${avatarColor}" aria-hidden="true">${_esc(initial)}</div>` : ''}
      <div class="bubble-body">
        <div class="bubble-meta">
          <span class="bubble-name ${isOwn ? 'bubble-name--own' : ''}">${_esc(data.display_name || 'Listener')}</span>
          <span class="bubble-time">${timeStr}</span>
        </div>
        <div class="bubble-text ${isOwn ? 'bubble-text--own' : ''}">${_esc(data.message)}</div>
        <div class="bubble-reactions" data-reactions></div>
      </div>
    `;

    // Quick reaction click
    const textEl = bubble.querySelector('.bubble-text');
    textEl?.addEventListener('dblclick', () => _showReactionPicker(bubble, data));

    container.appendChild(bubble);
    _scrollToBottom(container);
    _incUnread();
  }

  /* ── Render history ───────────────────────────────────────────────────────── */
  function renderHistory(messages) {
    const container = $('chat-messages');
    if (!container) return;
    container.innerHTML = '';

    if (!messages || messages.length === 0) {
      const el = document.createElement('div');
      el.dataset.placeholder = '1';
      el.className = 'chat-empty';
      el.innerHTML = `<div class="chat-empty-icon">💬</div><div>Be the first to say something!</div>`;
      container.appendChild(el);
      return;
    }

    messages.forEach(m => renderMessage({ ...m, client_id: '' }));
  }

  /* ── Render system/error message ──────────────────────────────────────────── */
  function renderError(msg) {
    const container = $('chat-messages');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'chat-system-msg chat-system-msg--error';
    el.textContent = msg;
    container.appendChild(el);
    _scrollToBottom(container);
    setTimeout(() => el.remove(), 4500);
  }

  function renderSystem(msg) {
    const container = $('chat-messages');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'chat-system-msg';
    el.textContent = msg;
    container.appendChild(el);
    _scrollToBottom(container);
  }

  /* ── Inline reaction picker ───────────────────────────────────────────────── */
  const REACTION_EMOJIS = ['❤️','😂','🥹','🔥','👏','😍'];

  function _showReactionPicker(bubble, data) {
    // Remove existing picker
    document.querySelectorAll('.inline-reaction-picker').forEach(p => p.remove());

    const picker = document.createElement('div');
    picker.className = 'inline-reaction-picker';
    REACTION_EMOJIS.forEach(em => {
      const btn = document.createElement('button');
      btn.textContent = em;
      btn.className = 'reaction-option';
      btn.addEventListener('click', () => {
        _addReaction(bubble, em);
        picker.remove();
      });
      picker.appendChild(btn);
    });
    bubble.appendChild(picker);
    setTimeout(() => picker.remove(), 3000);
  }

  function _addReaction(bubble, emoji) {
    const area = bubble.querySelector('[data-reactions]');
    if (!area) return;
    let existing = area.querySelector(`[data-emoji="${emoji}"]`);
    if (existing) {
      const count = parseInt(existing.dataset.count || '1') + 1;
      existing.dataset.count = count;
      existing.querySelector('.rxn-count').textContent = count;
    } else {
      const span = document.createElement('span');
      span.className = 'reaction-pill';
      span.dataset.emoji = emoji;
      span.dataset.count = 1;
      span.innerHTML = `${emoji}<span class="rxn-count">1</span>`;
      area.appendChild(span);
    }
  }

  /* ── Handle incoming typing events ───────────────────────────────────────── */
  function handleTyping(data) {
    if (data.display_name === _username) return;
    _typingUsers.add(data.display_name);
    _showTyping(_typingUsers);

    clearTimeout(_typingTimeout);
    _typingTimeout = setTimeout(() => {
      _typingUsers.delete(data.display_name);
      _showTyping(_typingUsers);
    }, 3500);
  }

  function handleStopTyping(data) {
    _typingUsers.delete(data.display_name);
    _showTyping(_typingUsers);
  }

  /* ── Scroll helpers ───────────────────────────────────────────────────────── */
  function _scrollToBottom(container) {
    requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });
  }

  /* ── Username ─────────────────────────────────────────────────────────────── */
  function setUsername(name) {
    _username = name;
    const el = $('username-display');
    if (el) el.textContent = name;
  }

  /* ── Utilities ────────────────────────────────────────────────────────────── */
  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function _nameToColor(name) {
    // Deterministic pastel-ish color per username
    const colors = [
      '#c2410c','#b45309','#15803d','#0369a1',
      '#7c3aed','#be185d','#0f766e','#a16207',
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return colors[Math.abs(hash) % colors.length];
  }

  return {
    init,
    setWs,
    setUsername,
    renderMessage,
    renderHistory,
    renderError,
    renderSystem,
    handleTyping,
    handleStopTyping,
  };
})();

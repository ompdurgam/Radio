/**
 * Song Request Module — Delux Radio
 * Handles the request form submission and response feedback.
 */

const RequestModule = (() => {
  const elements = {
    modal: () => document.getElementById('request-modal'),
    form: () => document.getElementById('request-form'),
    songInput: () => document.getElementById('req-song'),
    nameInput: () => document.getElementById('req-name'),
    dedicatedInput: () => document.getElementById('req-dedicated'),
    storyInput: () => document.getElementById('req-story'),
    submitBtn: () => document.getElementById('req-submit'),
    feedback: () => document.getElementById('req-feedback'),
    suggestionsBox: () => document.getElementById('req-song-suggestions'),
  };

  let searchTimeout = null;

  function init() {
    elements.form()?.addEventListener('submit', _handleSubmit);

    // Close modal on overlay click
    elements.modal()?.addEventListener('click', e => {
      if (e.target === elements.modal()) close();
    });

    // Handle autocomplete
    elements.songInput()?.addEventListener('input', _handleSearchInput);
    document.addEventListener('click', e => {
      const box = elements.suggestionsBox();
      if (box && e.target !== elements.songInput() && !box.contains(e.target)) {
        box.style.display = 'none';
      }
    });

    // Escape key closes modal
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') close();
    });
  }

  function open() {
    elements.modal()?.classList.add('open');
    setTimeout(() => elements.songInput()?.focus(), 400);
    _clearFeedback();
  }

  function close() {
    elements.modal()?.classList.remove('open');
    if (elements.suggestionsBox()) elements.suggestionsBox().style.display = 'none';
  }

  async function _handleSearchInput(e) {
    const q = e.target.value.trim();
    const box = elements.suggestionsBox();
    if (!box) return;

    // Skip if it's a YouTube link or too short
    if (!q || q.length < 2 || q.includes('youtu')) {
      box.style.display = 'none';
      return;
    }

    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(async () => {
      try {
        const res = await fetch(`/api/requests/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (data.success && data.results.length > 0) {
          box.innerHTML = '';
          data.results.forEach(song => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = `${song.title} <small>${song.artist}</small>`;
            div.addEventListener('click', () => {
              elements.songInput().value = song.title;
              box.style.display = 'none';
            });
            box.appendChild(div);
          });
          box.style.display = 'block';
        } else {
          box.style.display = 'none';
        }
      } catch (err) {
        console.error("Autocomplete error:", err);
      }
    }, 300);
  }

  async function _handleSubmit(e) {
    e.preventDefault();

    const song_name = elements.songInput()?.value?.trim();
    const requester_name = elements.nameInput()?.value?.trim();
    const dedicated_to = elements.dedicatedInput()?.value?.trim() || null;
    const story = elements.storyInput()?.value?.trim() || null;

    if (!song_name || !requester_name) {
      _showFeedback('Please fill in Your Name and a YouTube Link / Song Name.', 'error');
      return;
    }

    const btn = elements.submitBtn();
    btn.disabled = true;
    btn.textContent = '⏳ Sending request...';
    _clearFeedback();

    try {
      const res = await fetch('/api/requests/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_name, requester_name, dedicated_to, story }),
      });

      const data = await res.json();

      if (!res.ok) {
        _showFeedback(data.detail || 'Request failed. Please try again.', 'error');
        return;
      }

      // Success!
      _showFeedback(
        `✅ "${data.song?.title}" requested! The RJ will announce it soon. Queue position: #${data.queue_position}`,
        'success'
      );
      elements.form()?.reset();

      // Auto close after 3 seconds on success
      setTimeout(() => close(), 3500);

    } catch (err) {
      _showFeedback('❌ Connection error. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🎙️ Send Request';
    }
  }

  function _showFeedback(message, type) {
    const fb = elements.feedback();
    if (!fb) return;
    fb.textContent = message;
    fb.style.display = 'block';
    fb.style.color = type === 'error' ? '#e74c3c' : '#2ecc71';
    fb.style.background = type === 'error' ? 'rgba(231,76,60,0.08)' : 'rgba(46,204,113,0.08)';
    fb.style.border = `1px solid ${type === 'error' ? 'rgba(231,76,60,0.2)' : 'rgba(46,204,113,0.2)'}`;
    fb.style.padding = '10px 14px';
    fb.style.borderRadius = '8px';
    fb.style.fontSize = '13px';
    fb.style.lineHeight = '1.5';
    fb.style.marginTop = '12px';
  }

  function _clearFeedback() {
    const fb = elements.feedback();
    if (fb) fb.style.display = 'none';
  }

  return { init, open, close };
})();

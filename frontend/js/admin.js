/**
 * Admin Dashboard — Delux Radio
 * Handles auth, live status, drag-to-reorder queue, catalog, skip.
 */

const Admin = (() => {
  let _user = '';
  let _pw = '';
  let _pollTimer = null;
  let _progressTimer = null;
  let _songStartedAt = 0;
  let _songDuration  = 240;
  let _clockDrift    = 0;
  let _allSongs = [];
  let _dragSrcIndex = null;
  let _pendingOrder = null;   // new order after drag

  const $ = id => document.getElementById(id);

  // ── Auth ────────────────────────────────────────────────────────────────────
  function _initAuth() {
    const btn = $('auth-btn');
    const user = $('auth-user');
    const pw  = $('auth-pw');
    const err = $('auth-err');

    const attempt = async () => {
      const username = user.value.trim();
      const password = pw.value.trim();
      if (!username || !password) return;
      btn.disabled = true;
      btn.textContent = 'Verifying…';
      try {
        const res = await fetch('/api/admin/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });
        if (res.ok) {
          _user = username;
          _pw = password;
          sessionStorage.setItem('delux_admin_user', _user);
          sessionStorage.setItem('delux_admin_pw', _pw);
          _showDashboard();
        } else {
          err.textContent = '✖ Incorrect credentials. Try again.';
          pw.value = '';
          pw.focus();
        }
      } catch {
        err.textContent = '✖ Server unreachable.';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Sign In →';
      }
    };

    btn.addEventListener('click', attempt);
    pw.addEventListener('keydown', e => { if (e.key === 'Enter') attempt(); });
    user.addEventListener('keydown', e => { if (e.key === 'Enter') attempt(); });

    // Restore session
    const savedUser = sessionStorage.getItem('delux_admin_user');
    const savedPw = sessionStorage.getItem('delux_admin_pw');
    if (savedUser && savedPw) { 
      user.value = savedUser;
      pw.value = savedPw; 
      attempt(); 
    }
  }

  function _showDashboard() {
    $('auth-screen').style.display = 'none';
    $('dashboard').style.display   = 'block';
    _loadStatus();
    _loadCatalog();
    _loadRequests();
    _startPolling();
    _initSkip();
    _initRjToggle();
    _initRequests();
    _initLogout();
    _initAddSong();
  }

  function _initLogout() {
    $('btn-logout').addEventListener('click', () => {
      sessionStorage.removeItem('delux_admin_user');
      sessionStorage.removeItem('delux_admin_pw');
      location.reload();
    });
  }

  // ── API helpers ─────────────────────────────────────────────────────────────
  function _headers() {
    return { 'x-admin-username': _user, 'x-admin-password': _pw, 'Content-Type': 'application/json' };
  }

  async function _api(method, path, body) {
    const res = await fetch(`/api/admin${path}`, {
      method,
      headers: _headers(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  // ── Polling ──────────────────────────────────────────────────────────────────
  function _startPolling() {
    _loadStatus();
    _loadRequests();
    _pollTimer = setInterval(() => {
      _loadStatus();
      _loadRequests();
    }, 5000);   // refresh every 5s
    _progressTimer = setInterval(_tickProgress, 1000);
  }

  async function _loadStatus() {
    try {
      const data = await _api('GET', '/status');
      if (!data.success) return;
      const s = data.data;
      _applyStatus(s);
    } catch {}
  }

  function _applyStatus(s) {
    // Header stats
    $('hdr-listeners').textContent = s.listener_count || 0;
    $('hdr-mode').textContent      = s.mode || 'auto';

    // RJ toggle
    if (s.rj_enabled !== undefined) {
      const rjBtn = $('btn-toggle-rj');
      const rjLabel = $('rj-toggle-label');
      if (rjBtn && rjLabel) {
        if (s.rj_enabled) {
          rjBtn.className = 'btn-rj-toggle on';
          rjLabel.textContent = '🎙️ RJ: ON';
        } else {
          rjBtn.className = 'btn-rj-toggle off';
          rjLabel.textContent = '🎙️ RJ: OFF';
        }
      }
    }

    // Now Playing
    const song = s.current_song;
    if (song) {
      $('np-title').textContent  = song.title || '—';
      $('np-artist').textContent = [song.artist, song.movie].filter(Boolean).join(' · ');
      const thumb = $('np-thumb');
      if (song.youtube_video_id) {
        thumb.src = `https://img.youtube.com/vi/${song.youtube_video_id}/mqdefault.jpg`;
        thumb.style.display = '';
      } else {
        thumb.style.display = 'none';
      }
    }

    // Sync clock
    if (s.song_started_at > 0) _songStartedAt = s.song_started_at;
    if (s.song_duration   > 0) _songDuration  = s.song_duration;
    if (s.server_time     > 0) {
      _clockDrift = s.server_time - (Date.now() / 1000);
    }

    // Queue
    if (s.upcoming_queue) _renderQueue(s.upcoming_queue);

    // Enable skip
    $('btn-skip').disabled = false;
  }

  // ── Progress bar tick ────────────────────────────────────────────────────────
  function _tickProgress() {
    if (!_songStartedAt) return;
    const nowServer = (Date.now() / 1000) + _clockDrift;
    const elapsed  = Math.max(0, nowServer - _songStartedAt);
    const duration = _songDuration || 240;
    const pct      = Math.min(100, (elapsed / duration) * 100);

    $('np-bar').style.width    = `${pct}%`;
    $('np-elapsed').textContent = _fmtTime(elapsed);
    $('np-duration').textContent = _fmtTime(duration);
  }

  function _fmtTime(sec) {
    if (!sec || sec < 0) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  // ── Skip ─────────────────────────────────────────────────────────────────────
  function _initSkip() {
    $('btn-skip').addEventListener('click', async () => {
      $('btn-skip').disabled = true;
      try {
        await _api('POST', '/skip');
        _toast('⏭ Skipped to next song', 'ok');
        await _loadStatus();
      } catch {
        _toast('Failed to skip', 'err');
      } finally {
        setTimeout(() => { $('btn-skip').disabled = false; }, 2000);
      }
    });
  }

  // ── RJ On/Off Toggle ─────────────────────────────────────────────────────────
  function _initRjToggle() {
    const btn = $('btn-toggle-rj');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const res = await _api('POST', '/rj/toggle');
        const enabled = res.rj_enabled;
        btn.className = `btn-rj-toggle ${enabled ? 'on' : 'off'}`;
        const label = $('rj-toggle-label');
        if (label) label.textContent = enabled ? '🎙️ RJ: ON' : '🎙️ RJ: OFF';
        _toast(`🎙️ AI RJ announcements turned ${enabled ? 'ON' : 'OFF'}`, 'ok');
      } catch {
        _toast('Failed to toggle RJ state', 'err');
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ── Song Requests ────────────────────────────────────────────────────────────
  function _initRequests() {
    const btnRefresh = $('btn-refresh-requests');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', async () => {
        btnRefresh.disabled = true;
        await _loadRequests();
        _toast('Song requests refreshed', 'ok');
        btnRefresh.disabled = false;
      });
    }
  }

  async function _loadRequests() {
    try {
      const data = await _api('GET', '/requests');
      if (!data.success) return;
      _renderRequests(data.requests || []);
    } catch {
      const list = $('requests-list');
      if (list && !list.querySelector('.req-card')) {
        list.innerHTML = '<div class="queue-empty" style="color:var(--red);">Failed to load requests</div>';
      }
    }
  }

  function _renderRequests(requests) {
    const list = $('requests-list');
    const badge = $('requests-count');
    if (!list) return;

    if (badge) badge.textContent = requests ? requests.length : 0;

    if (!requests || requests.length === 0) {
      list.innerHTML = '<div class="queue-empty">No listener song requests yet</div>';
      return;
    }

    list.innerHTML = '';
    requests.forEach(r => {
      const item = document.createElement('div');
      item.className = 'req-card';

      const audioPlayer = r.rj_audio_url 
        ? `<div style="margin-top: 8px;"><audio controls preload="none" style="height: 28px; width: 100%; max-width: 280px;" src="${r.rj_audio_url}"></audio></div>`
        : '';

      const dedication = r.dedicated_to ? `<div class="req-dedication">❤️ Dedication for: <strong>${_esc(r.dedicated_to)}</strong></div>` : '';
      const emotionBadge = r.emotion_tag ? `<span style="font-size:11px; background:rgba(245,158,11,0.1); color:var(--amber-dk); padding:2px 6px; border-radius:4px; font-weight:600;">#${_esc(r.emotion_tag)}</span>` : '';
      const story = r.story ? `<div class="req-story">"${_esc(r.story)}"</div>` : '';

      const statusClass = (r.status || 'pending').toLowerCase();
      const canPlayNext = statusClass === 'queued' || statusClass === 'pending';

      const timeStr = r.created_at ? new Date(r.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';

      item.innerHTML = `
        <div class="req-header">
          <div>
            <div class="req-user">👤 ${_esc(r.requester_name || 'Anonymous')}</div>
            <div class="req-song-title">🎵 ${_esc(r.song_title || 'Unknown Song')}${r.song_artist ? ' · ' + _esc(r.song_artist) : ''}${r.movie ? ' (' + _esc(r.movie) + ')' : ''}</div>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            ${emotionBadge}
            <span class="req-badge ${statusClass}">${statusClass}</span>
          </div>
        </div>
        ${dedication}
        ${story}
        ${audioPlayer}
        <div class="req-footer">
          <span style="font-size:11px; color:var(--muted);">${timeStr}</span>
          <div class="req-actions">
            ${canPlayNext ? `<button class="btn-play-next" data-req-id="${r.id}" title="Queue this request to play immediately after current song">▶ Play Next</button>` : ''}
            <button class="btn-del-req" data-req-id="${r.id}" title="Remove request">✕ Remove</button>
          </div>
        </div>
      `;

      // Event listeners
      const playNextBtn = item.querySelector('.btn-play-next');
      if (playNextBtn) {
        playNextBtn.addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          const id = btn.dataset.reqId;
          btn.disabled = true;
          btn.textContent = '…';
          try {
            await _api('POST', `/requests/${id}/play-next`);
            _toast(`⚡ Request #${id} scheduled to Play Next!`, 'ok');
            await _loadRequests();
            await _loadStatus();
          } catch {
            _toast('Failed to schedule request to play next', 'err');
          } finally {
            btn.disabled = false;
            btn.textContent = '▶ Play Next';
          }
        });
      }

      const delBtn = item.querySelector('.btn-del-req');
      if (delBtn) {
        delBtn.addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          const id = btn.dataset.reqId;
          if (!confirm(`Delete request #${id}?`)) return;
          btn.disabled = true;
          try {
            await _api('DELETE', `/requests/${id}`);
            _toast(`Request #${id} removed`, 'ok');
            await _loadRequests();
            await _loadStatus();
          } catch {
            _toast('Failed to remove request', 'err');
            btn.disabled = false;
          }
        });
      }

      list.appendChild(item);
    });
  }

  // ── Queue ─────────────────────────────────────────────────────────────────────
  function _renderQueue(queue) {
    const list = $('queue-list');
    if (!queue || queue.length === 0) {
      list.innerHTML = '<div class="queue-empty">No upcoming songs</div>';
      $('btn-save').disabled = true;
      return;
    }

    list.innerHTML = '';
    queue.forEach((song, i) => {
      const item = document.createElement('div');
      item.className = 'queue-item';
      item.draggable = true;
      item.dataset.index = i;
      item.dataset.songId = song.id;

      const thumb = song.youtube_video_id
        ? `<img class="q-thumb" src="https://img.youtube.com/vi/${song.youtube_video_id}/default.jpg" alt="" />`
        : `<div class="q-thumb"></div>`;

      item.innerHTML = `
        <div class="q-rank ${i === 0 ? 'first' : ''}">${i + 1}</div>
        <span class="q-handle" title="Drag to reorder">⠿</span>
        ${thumb}
        <div class="q-info">
          <div class="q-title">${_esc(song.title)}</div>
          <div class="q-artist">${_esc(song.artist || '')}${song.movie ? ' · ' + _esc(song.movie) : ''}</div>
        </div>
        <button class="btn-rm" data-song-id="${song.id}" title="Remove from queue">✕</button>
      `;

      // Drag events
      item.addEventListener('dragstart', _onDragStart);
      item.addEventListener('dragover',  _onDragOver);
      item.addEventListener('dragleave', _onDragLeave);
      item.addEventListener('drop',      _onDrop);
      item.addEventListener('dragend',   _onDragEnd);

      // Remove button
      item.querySelector('.btn-rm').addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = parseInt(e.currentTarget.dataset.songId);
        await _removeFromQueue(id);
      });

      list.appendChild(item);
    });

    $('btn-save').disabled   = true;   // disabled until user drags
    $('btn-save').onclick     = _saveOrder;
    _pendingOrder = null;
  }

  // ── Drag and drop ─────────────────────────────────────────────────────────────
  function _onDragStart(e) {
    _dragSrcIndex = parseInt(this.dataset.index);
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  }

  function _onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    document.querySelectorAll('.queue-item.drag-over').forEach(el => el.classList.remove('drag-over'));
    this.classList.add('drag-over');
    return false;
  }

  function _onDragLeave() {
    this.classList.remove('drag-over');
  }

  function _onDrop(e) {
    e.stopPropagation();
    const destIndex = parseInt(this.dataset.index);
    if (_dragSrcIndex === null || _dragSrcIndex === destIndex) return;

    // Reorder the DOM visually
    const list  = $('queue-list');
    const items = [...list.querySelectorAll('.queue-item')];
    const moved = items.splice(_dragSrcIndex, 1)[0];
    items.splice(destIndex, 0, moved);

    // Re-render with new numbering
    items.forEach((el, i) => {
      el.dataset.index = i;
      el.querySelector('.q-rank').textContent  = i + 1;
      el.querySelector('.q-rank').className    = `q-rank ${i === 0 ? 'first' : ''}`;
      list.appendChild(el);
    });

    // Capture new order
    _pendingOrder = items.map(el => parseInt(el.dataset.songId));
    $('btn-save').disabled = false;
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    return false;
  }

  function _onDragEnd() {
    this.classList.remove('dragging');
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
  }

  async function _saveOrder() {
    if (!_pendingOrder) return;
    $('btn-save').disabled = true;
    $('btn-save').textContent = '⏳ Saving…';
    try {
      await _api('PUT', '/upcoming/reorder', { song_ids: _pendingOrder });
      _toast('✅ Queue order saved!', 'ok');
      _pendingOrder = null;
      await _loadStatus();
    } catch {
      _toast('Failed to save order', 'err');
      $('btn-save').disabled = false;
    } finally {
      $('btn-save').innerHTML = '💾 Save Queue Order';
    }
  }

  async function _removeFromQueue(songId) {
    try {
      await _api('DELETE', `/upcoming/${songId}`);
      _toast('Removed from queue', 'ok');
      await _loadStatus();
    } catch {
      _toast('Failed to remove', 'err');
    }
  }

  // ── Catalog ───────────────────────────────────────────────────────────────────
  async function _loadCatalog() {
    try {
      const data = await _api('GET', '/songs');
      if (!data.success) return;
      _allSongs = data.songs;
      $('catalog-count').textContent = `${_allSongs.length} songs`;
      _renderCatalog(_allSongs);
      $('cat-search').addEventListener('input', e => {
        const q = e.target.value.toLowerCase();
        const filtered = _allSongs.filter(s =>
          s.title.toLowerCase().includes(q) ||
          s.artist.toLowerCase().includes(q) ||
          (s.movie || '').toLowerCase().includes(q)
        );
        _renderCatalog(filtered);
      });
    } catch {
      $('cat-list').innerHTML = '<div style="text-align:center;color:#f87171;font-size:13px;padding:20px">Failed to load catalog</div>';
    }
  }

  function _renderCatalog(songs) {
    const list = $('cat-list');
    if (!songs.length) {
      list.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:13px;padding:20px">No songs found</div>';
      return;
    }
    list.innerHTML = '';
    songs.forEach(song => {
      const item = document.createElement('div');
      item.className = 'cat-item';
      item.innerHTML = `
        <div class="cat-info">
          <div class="cat-title">${_esc(song.title)}</div>
          <div class="cat-sub">${_esc(song.artist)}${song.movie ? ' · ' + _esc(song.movie) : ''} ${song.release_year ? '(' + song.release_year + ')' : ''}</div>
        </div>
        <div class="cat-actions">
          <button class="btn-outline btn-add-queue" data-song-id="${song.id}">+ Add to Queue</button>
          <button class="btn-delete-song" data-song-id="${song.id}" title="Delete song from catalog">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
          </button>
        </div>
      `;
      item.querySelector('.btn-add-queue').addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = '…';
        try {
          await _api('POST', '/upcoming/add', { song_id: song.id });
          _toast(`➕ "${song.title}" added to queue`, 'ok');
          await _loadStatus();
        } catch (err) {
          _toast('Could not add — queue may be full', 'err');
        } finally {
          btn.disabled = false;
          btn.textContent = '+ Add to Queue';
        }
      });

      item.querySelector('.btn-delete-song').addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        if (!confirm(`Are you sure you want to delete "${song.title}" from the catalog?`)) {
          return;
        }
        btn.disabled = true;
        try {
          await _api('DELETE', `/songs/${song.id}`);
          _toast(`🗑️ "${song.title}" deleted`, 'ok');
          _allSongs = _allSongs.filter(s => s.id !== song.id);
          $('catalog-count').textContent = `${_allSongs.length} songs`;
          item.remove();
          if (!_allSongs.length) {
            list.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:13px;padding:20px">No songs in catalog</div>';
          }
          await _loadStatus();
        } catch (err) {
          _toast(err.message || 'Failed to delete song', 'err');
          btn.disabled = false;
        }
      });
      list.appendChild(item);
    });
  }

  // ── Add Song Modal ────────────────────────────────────────────────────────────
  function _initAddSong() {
    const modal = $('add-song-modal');
    const form = $('add-song-form');
    
    $('btn-open-add-song').addEventListener('click', () => {
      modal.classList.add('show');
      $('new-title').focus();
    });

    $('btn-close-modal').addEventListener('click', () => {
      modal.classList.remove('show');
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.remove('show');
    });

    $('btn-fetch-yt').addEventListener('click', async () => {
      const ytInput = $('new-yt').value.trim();
      const err = $('new-error');
      if (!ytInput) return;
      
      let yt = ytInput;
      const ytMatch = yt.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/);
      if (ytMatch) yt = ytMatch[1];
      if (yt.length !== 11) {
        err.textContent = "Invalid YouTube Link or ID.";
        err.style.display = 'block';
        return;
      }
      
      const btn = $('btn-fetch-yt');
      btn.disabled = true;
      btn.textContent = '…';
      try {
        const data = await _api('GET', `/yt-info?url=https://www.youtube.com/watch?v=${yt}`);
        if (data.success) {
           let title = data.title || '';
           let artist = data.author || '';
           $('new-title').value = title;
           $('new-artist').value = artist;
           $('new-yt').value = yt;
           err.style.display = 'none';

           // Attempt to fetch Movie/Album and Year from iTunes
           try {
             let cleanTitle = title.replace(/\([^)]+\)|\[[^\]]+\]/g, ' ');
             cleanTitle = cleanTitle.split('|')[0];
             cleanTitle = cleanTitle.replace(/video|lyrical|full song|audio|official/gi, ' ').trim();
             
             const itunesRes = await fetch(`https://itunes.apple.com/search?term=${encodeURIComponent(cleanTitle)}&entity=song&limit=10`);
             if (itunesRes.ok) {
               const iData = await itunesRes.json();
               if (iData.results && iData.results.length > 0) {
                 let oldestRes = iData.results[0];
                 let oldestYear = 9999;
                 
                 for (const res of iData.results) {
                   if (res.releaseDate) {
                     const yr = parseInt(res.releaseDate.substring(0, 4));
                     if (yr < oldestYear) {
                       oldestYear = yr;
                       oldestRes = res;
                     }
                   }
                 }
                 
                 if (oldestRes.collectionName) {
                   let movie = oldestRes.collectionName.replace(/\(Original Motion Picture Soundtrack\)|\(Soundtrack\)|\(Original Soundtrack\)|\(Deluxe Edition\)/i, '').trim();
                   $('new-movie').value = movie;
                 }
                 if (oldestYear !== 9999) {
                   $('new-year').value = oldestYear;
                 }
               }
             }
           } catch (e) {
             console.log("iTunes fetch failed", e);
           }
        }
      } catch (e) {
        err.textContent = "Failed to fetch YouTube details.";
        err.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Fetch';
      }
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = $('btn-submit-song');
      const err = $('new-error');
      
      const title = $('new-title').value.trim();
      const artist = $('new-artist').value.trim();
      const movie = $('new-movie').value.trim();
      const year = parseInt($('new-year').value);
      let yt = $('new-yt').value.trim();
      
      if (!title || !artist || !year || !yt) return;
      
      const ytMatch = yt.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/);
      if (ytMatch) yt = ytMatch[1];
      if (yt.length !== 11) {
        err.textContent = "Invalid YouTube ID. Must be 11 characters.";
        err.style.display = 'block';
        return;
      }
      
      err.style.display = 'none';
      btn.disabled = true;
      btn.textContent = 'Adding…';
      
      try {
        await _api('POST', '/songs', {
          title, artist, movie, release_year: year, youtube_video_id: yt
        });
        _toast('Song added successfully!', 'ok');
        modal.classList.remove('show');
        form.reset();
        await _loadCatalog();
      } catch (error) {
        err.textContent = "Failed to add song. Try again.";
        err.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Add to Catalog';
      }
    });
  }

  // ── Toast ─────────────────────────────────────────────────────────────────────
  let _toastTimer = null;
  function _toast(msg, type = 'ok') {
    const el = $('toast');
    el.textContent = msg;
    el.className   = `toast ${type} show`;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { el.classList.remove('show'); }, 2800);
  }

  // ── Utils ─────────────────────────────────────────────────────────────────────
  function _esc(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── Boot ──────────────────────────────────────────────────────────────────────
  _initAuth();

})();

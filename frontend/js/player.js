/**
 * YouTube IFrame Player & Direct Audio Stream Integration — Delux Radio
 * Manages YouTube player state (for ambient visuals) and HTML5 Audio (for sound).
 * Features reliable multi-listener sync, metadata-aware seeking, and auto-fallback.
 */

const Player = (() => {
  // YouTube Visual Player
  let ytPlayer = null;
  let isReady = false;
  
  // HTML5 Audio Player (Bypasses mobile restrictions)
  const audioPlayer = new Audio();
  // DO NOT use crossOrigin attribute, googlevideo redirect does not send CORS
  
  let pendingVideoId = null;
  let pendingPlay = false;
  let pendingStart = 0;
  let currentVideoId = null;
  let targetSeekOffset = 0;
  let currentVolume = 80;
  let currentMuted = false;
  let fallbackYtAudio = false;

  // Callbacks
  let _onEndedCb = null;
  let _onPlayingCb = null;
  let _onErrorCb = null;

  // ── Audio Events ──
  audioPlayer.addEventListener('playing', () => {
    console.log('[Player] Audio Playing');
    // Ensure seek position if metadata event was missed
    if (targetSeekOffset > 0 && Math.abs(audioPlayer.currentTime - targetSeekOffset) > 2) {
      try {
        audioPlayer.currentTime = targetSeekOffset;
        console.log(`[Player] Synced playing audio to ${targetSeekOffset.toFixed(1)}s`);
      } catch (e) {}
    }
    targetSeekOffset = 0;
    if (_onPlayingCb) _onPlayingCb(currentVideoId);
  });

  audioPlayer.addEventListener('ended', () => {
    console.log('[Player] Audio Ended');
    if (_onEndedCb) _onEndedCb();
  });

  audioPlayer.addEventListener('error', (e) => {
    console.warn('[Player] Audio Stream Error:', e);
    // Fallback: If backend stream extraction fails, unmute YouTube visual player
    if (ytPlayer && isReady) {
      console.log('[Player] Falling back to YouTube native audio');
      fallbackYtAudio = true;
      try {
        if (!currentMuted) ytPlayer.unMute();
        ytPlayer.setVolume(currentVolume);
        ytPlayer.playVideo();
      } catch (err) {}
    }
    if (_onErrorCb) _onErrorCb(5); 
  });

  // Keep ambient visuals closely synced with audio playback
  let lastVisualSync = 0;
  audioPlayer.addEventListener('timeupdate', () => {
    const now = Date.now();
    if (now - lastVisualSync > 3000 && isReady && ytPlayer && !fallbackYtAudio) {
      lastVisualSync = now;
      try {
        const aTime = audioPlayer.currentTime;
        const vTime = ytPlayer.getCurrentTime();
        if (aTime > 0 && vTime !== undefined && Math.abs(aTime - vTime) > 2.5) {
          ytPlayer.seekTo(aTime, true);
        }
      } catch (e) {}
    }
  });

  // ── YouTube Visuals ──
  window.onYouTubeIframeAPIReady = function () {
    ytPlayer = new YT.Player('yt-player', {
      height: '100%',
      width: '100%',
      videoId: '',
      playerVars: {
        autoplay: 0,
        controls: 0,
        disablekb: 1,
        fs: 0,
        iv_load_policy: 3,
        modestbranding: 1,
        rel: 0,
        showinfo: 0,
        playsinline: 1,
        mute: 1, // Start muted while audioPlayer handles sound
        origin: location.origin,
      },
      events: {
        onReady: (event) => {
          isReady = true;
          event.target.mute(); // Enforce mute
          console.log('[Player] YouTube Visuals ready');
          if (pendingVideoId) {
            _doLoad(pendingVideoId, pendingPlay, pendingStart);
            pendingVideoId = null;
          }
        },
        onError: (e) => {
          console.warn('[Player] Visual YouTube error (Ignored):', e.data);
        }
      },
    });
  };

  function _applyAudioSeek(seconds) {
    if (seconds <= 0) return;
    targetSeekOffset = seconds;

    const performSeek = () => {
      try {
        if (audioPlayer.duration && !isNaN(audioPlayer.duration)) {
          const clamped = Math.min(seconds, Math.max(0, audioPlayer.duration - 1));
          audioPlayer.currentTime = clamped;
        } else {
          audioPlayer.currentTime = seconds;
        }
        console.log(`[Player] Audio seeked to ${seconds.toFixed(1)}s`);
      } catch (err) {
        console.warn('[Player] Audio seek error:', err);
      }
    };

    if (audioPlayer.readyState >= 1) {
      performSeek();
    } else {
      audioPlayer.addEventListener('loadedmetadata', performSeek, { once: true });
      audioPlayer.addEventListener('canplay', performSeek, { once: true });
    }
  }

  function _doLoad(videoId, autoplay, startSeconds) {
    const isSameVideo = (currentVideoId === videoId);
    currentVideoId = videoId;
    const targetOffset = Math.max(0, startSeconds || 0);

    // If it's already the same video, don't destroy and reload the audio stream!
    if (isSameVideo && audioPlayer.src && audioPlayer.src.includes(videoId)) {
      if (Math.abs(audioPlayer.currentTime - targetOffset) > 1.5) {
        _applyAudioSeek(targetOffset);
      }
      if (autoplay && audioPlayer.paused) {
        audioPlayer.play().catch(() => {});
      }
      if (ytPlayer && isReady) {
        ytPlayer.seekTo(targetOffset, true);
        if (autoplay) ytPlayer.playVideo();
      }
      return;
    }

    fallbackYtAudio = false;
    targetSeekOffset = targetOffset;

    // 1. Update Audio
    audioPlayer.src = `/api/radio/stream/${videoId}`;
    _applyAudioSeek(targetOffset);

    if (autoplay) {
      audioPlayer.play().catch(e => {
        console.warn("[Player] Audio blocked by browser:", e);
      });
    }

    // 2. Update Visuals
    if (ytPlayer && isReady) {
      const opts = targetOffset > 0 ? { videoId, startSeconds: Math.floor(targetOffset) } : videoId;
      if (autoplay) {
        ytPlayer.loadVideoById(opts);
      } else {
        ytPlayer.cueVideoById(opts);
      }
    }
  }

  // ── Public API ──

  function loadVideo(videoId, autoplay = true, startSeconds = 0) {
    if (!videoId) return;
    
    // We don't block audio loading if ytPlayer isn't ready!
    if (!isReady) {
      currentVideoId = videoId;
      fallbackYtAudio = false;
      targetSeekOffset = Math.max(0, startSeconds || 0);
      audioPlayer.src = `/api/radio/stream/${videoId}`;
      _applyAudioSeek(targetSeekOffset);
      if (autoplay) audioPlayer.play().catch(()=>{});
      
      pendingVideoId = videoId;
      pendingPlay = autoplay;
      pendingStart = startSeconds;
      return;
    }

    _doLoad(videoId, autoplay, startSeconds);
  }

  function seekTo(seconds) {
    const s = Math.max(0, seconds || 0);
    _applyAudioSeek(s);
    if (isReady && ytPlayer) {
      try { ytPlayer.seekTo(s, true); } catch (e) {}
    }
  }

  function getCurrentTime() {
    if (fallbackYtAudio && isReady && ytPlayer) {
      try { return ytPlayer.getCurrentTime() || 0; } catch (e) {}
    }
    if (audioPlayer && audioPlayer.currentTime > 0) {
      return audioPlayer.currentTime;
    }
    if (isReady && ytPlayer) {
      try { return ytPlayer.getCurrentTime() || 0; } catch (e) {}
    }
    return audioPlayer.currentTime || 0;
  }

  function play() {
    if (fallbackYtAudio && isReady && ytPlayer) {
      ytPlayer.playVideo();
    } else {
      audioPlayer.play().catch(()=>{});
      if (isReady && ytPlayer) ytPlayer.playVideo();
    }
  }

  function pause() {
    audioPlayer.pause();
    if (isReady && ytPlayer) ytPlayer.pauseVideo();
  }

  function setVolume(vol) {
    currentVolume = vol;
    audioPlayer.volume = Math.max(0, Math.min(100, vol)) / 100;
    if (isReady && ytPlayer && fallbackYtAudio) {
      try { ytPlayer.setVolume(vol); } catch (e) {}
    }
  }

  function setMuted(muted) {
    currentMuted = muted;
    audioPlayer.muted = muted;
    if (isReady && ytPlayer) {
      if (fallbackYtAudio) {
        if (muted) ytPlayer.mute(); else ytPlayer.unMute();
      }
    }
  }

  function isPlaying() {
    if (fallbackYtAudio && isReady && ytPlayer) {
      try { return ytPlayer.getPlayerState() === 1; } catch (e) { return false; }
    }
    return !audioPlayer.paused && audioPlayer.currentTime > 0;
  }

  function getDuration() {
    const d = audioPlayer.duration;
    if (d && !isNaN(d) && isFinite(d)) return d;
    if (isReady && ytPlayer) {
      try { return ytPlayer.getDuration() || 0; } catch { return 0; }
    }
    return 0;
  }

  function onEnded(cb) { _onEndedCb = cb; }
  function onPlaying(cb) { _onPlayingCb = cb; }
  function onError(cb) { _onErrorCb = cb; }

  return { loadVideo, play, pause, seekTo, getCurrentTime, setVolume, setMuted, isPlaying, getDuration, onEnded, onPlaying, onError };
})();

// Inject YouTube IFrame API script
(function () {
  const tag = document.createElement('script');
  tag.src = 'https://www.youtube.com/iframe_api';
  tag.async = true;
  const first = document.getElementsByTagName('script')[0];
  first.parentNode.insertBefore(tag, first);
})();

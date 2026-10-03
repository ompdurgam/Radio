"""
Audio Mixer — Delux Radio
Mixes RJ voice + background ambience using pydub + FFmpeg.
Creates cinematic layered audio for announcements.
"""
import os
import asyncio
from pathlib import Path
from typing import Optional

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets" / "music"
AUDIO_DIR = Path(__file__).parent.parent / "audio"


async def mix_rj_announcement(
    voice_path: str,
    output_path: str,
    bg_music_path: Optional[str] = None,
) -> bool:
    """
    Layer voice + background music into a cinematic announcement.
    Music is auto-ducked (-14dB) under the voice.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _mix_sync, voice_path, output_path, bg_music_path
    )
    return result


def _mix_sync(voice_path: str, output_path: str, bg_music_path: Optional[str]) -> bool:
    try:
        from pydub import AudioSegment, effects

        if not os.path.exists(voice_path):
            print(f"⚠️  Voice file not found: {voice_path}")
            return False

        voice = AudioSegment.from_file(voice_path)
        voice = effects.normalize(voice)

        # Add 500ms silence at start for atmosphere
        silence = AudioSegment.silent(duration=500)
        voice = silence + voice + AudioSegment.silent(duration=800)

        # Try to add background music
        bg_path = bg_music_path or _find_bg_music()
        if bg_path and os.path.exists(bg_path):
            bg = AudioSegment.from_file(bg_path)

            # Loop bg to cover voice duration
            total_needed = len(voice) + 2000
            if len(bg) < total_needed:
                repeats = (total_needed // len(bg)) + 2
                bg = bg * repeats
            bg = bg[:total_needed]

            # Fade in bg music
            bg = bg.fade_in(1500)

            # Duck music under voice (-14 dB gives radio feel)
            bg_ducked = bg - 14

            # Overlay voice on ducked music
            final = bg_ducked.overlay(voice, position=500)

            # Fade out at end
            final = final.fade_out(1500)
        else:
            # No background music — just voice with fade
            final = voice.fade_in(200).fade_out(800)

        final = effects.normalize(final)
        final.export(output_path, format="mp3", bitrate="128k")
        print(f"✅ Audio mixed → {output_path}")
        return True

    except ImportError:
        print("⚠️  pydub not installed. Copying raw voice file.")
        try:
            import shutil
            shutil.copy2(voice_path, output_path)
            return True
        except Exception:
            return False
    except Exception as e:
        print(f"❌ Audio mix error: {e}")
        # Last resort: just copy the voice
        try:
            import shutil
            shutil.copy2(voice_path, output_path)
            return True
        except Exception:
            return False


def _find_bg_music() -> Optional[str]:
    """Find a background ambience file in the assets directory."""
    if not ASSETS_DIR.exists():
        return None
    for ext in [".mp3", ".wav", ".ogg"]:
        for f in ASSETS_DIR.glob(f"*{ext}"):
            return str(f)
    return None

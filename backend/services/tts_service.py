"""
TTS Service — Delux Radio
Primary: Edge TTS (ultra-realistic Indian female voice 'en-IN-NeerjaNeural')
Secondary: gTTS (Google Translate TTS - Indian accent)
Fallbacks: Kokoro, pyttsx3
"""
import os
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

AUDIO_DIR = Path(__file__).parent.parent / "audio"
AUDIO_DIR.mkdir(exist_ok=True)


async def generate_voice(text: str, output_path: str) -> bool:
    """
    Generate TTS audio for the given text.
    Returns True on success, False on failure.
    """
    # 1. Try Edge TTS (highest quality, natural Indian FM RJ voice)
    if await _try_edge_tts(text, output_path):
        return True
    # 2. Try gTTS (Google TTS fallback)
    if await _try_gtts(text, output_path):
        return True
    # 3. Try Kokoro
    if await _try_kokoro(text, output_path):
        return True
    # 4. Fallback: pyttsx3
    if await _try_pyttsx3(text, output_path):
        return True
    print(f"❌ TTS failed for output: {output_path}")
    return False


async def _try_edge_tts(text: str, output_path: str) -> bool:
    """Edge TTS — authentic Indian female radio voice (Priya RJ)."""
    try:
        import edge_tts
        # en-IN-NeerjaNeural: warm Indian female voice, perfect for Bollywood radio
        communicate = edge_tts.Communicate(
            text=text,
            voice="en-IN-NeerjaNeural",
            rate="-4%",
            pitch="+2Hz"
        )
        await communicate.save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            print(f"✅ Edge TTS (Priya) → {output_path}")
            return True
        return False
    except ImportError:
        print("ℹ️ edge-tts not installed. Trying next fallback...")
        return False
    except Exception as e:
        print(f"⚠️ Edge TTS error: {e}")
        return False


async def _try_gtts(text: str, output_path: str) -> bool:
    """gTTS fallback — Google Translate TTS with Indian English accent."""
    try:
        from gtts import gTTS
        loop = asyncio.get_event_loop()

        def _run():
            tts = gTTS(text=text, lang="en", tld="co.in")
            tts.save(output_path)
            return True

        result = await loop.run_in_executor(None, _run)
        if result and os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            print(f"✅ gTTS → {output_path}")
            return True
        return False
    except ImportError:
        return False
    except Exception as e:
        print(f"⚠️ gTTS error: {e}")
        return False


async def _try_kokoro(text: str, output_path: str) -> bool:
    """Kokoro-82M TTS — realistic Indian English female voice."""
    try:
        import kokoro
        import soundfile as sf
        import numpy as np

        loop = asyncio.get_event_loop()

        def _run():
            pipeline = kokoro.KPipeline(lang_code='a')  # 'a' = American English (clear & warm)
            # Use af_heart voice — warm, feminine, expressive
            generator = pipeline(
                text,
                voice='af_heart',
                speed=0.88,  # Slightly slower for radio warmth
                split_pattern=r'\n+'
            )
            audio_chunks = []
            for _, _, audio in generator:
                audio_chunks.append(audio)
            if not audio_chunks:
                return False
            audio_data = np.concatenate(audio_chunks)
            sf.write(output_path, audio_data, 24000)
            return True

        result = await loop.run_in_executor(None, _run)
        if result:
            print(f"✅ Kokoro TTS → {output_path}")
        return result

    except ImportError:
        print("ℹ️  Kokoro not installed. Trying pyttsx3...")
        return False
    except Exception as e:
        print(f"⚠️  Kokoro error: {e}")
        return False


async def _try_pyttsx3(text: str, output_path: str) -> bool:
    """pyttsx3 fallback — basic but functional."""
    try:
        import pyttsx3

        loop = asyncio.get_event_loop()

        def _run():
            engine = pyttsx3.init()
            # Try to find a female voice
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'female' in voice.name.lower() or 'zira' in voice.name.lower() or 'hazel' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
            engine.setProperty('rate', 145)   # Slightly slower
            engine.setProperty('volume', 0.9)

            # pyttsx3 saves as wav
            wav_path = output_path.replace('.mp3', '.wav')
            engine.save_to_file(text, wav_path)
            engine.runAndWait()

            # Convert wav → mp3 if pydub available
            if os.path.exists(wav_path):
                try:
                    from pydub import AudioSegment
                    AudioSegment.from_wav(wav_path).export(output_path, format="mp3")
                    os.remove(wav_path)
                except Exception:
                    # Just use wav as the output
                    import shutil
                    shutil.move(wav_path, output_path)
                return True
            return False

        result = await loop.run_in_executor(None, _run)
        if result:
            print(f"✅ pyttsx3 TTS → {output_path}")
        return result

    except ImportError:
        print("⚠️  pyttsx3 not installed. TTS unavailable.")
        return False
    except Exception as e:
        print(f"⚠️  pyttsx3 error: {e}")
        return False


def get_audio_path(request_id: int) -> str:
    return str(AUDIO_DIR / f"rj_{request_id}.mp3")


def get_audio_url(request_id: int) -> str:
    return f"/audio/rj_{request_id}.mp3"

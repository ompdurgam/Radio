"""
AI Service — Delux Radio
Uses Ollama + Llama 3 to generate cinematic female RJ scripts.
Falls back to warm template scripts if Ollama is unavailable.
"""
import httpx
import json
import random
from typing import Optional

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3"

EMOTION_TAGS = {
    "romantic": ["❤️", "love", "sweetheart", "darling", "pyaar"],
    "nostalgic": ["school", "college", "childhood", "yaad", "purani"],
    "emotional": ["dil", "heart", "cry", "aansu", "miss"],
    "heartbreak": ["breakup", "separated", "gone", "lost", "left"],
    "friendship": ["friend", "yaar", "dost", "buddy", "together"],
    "family": ["mom", "maa", "dad", "papa", "sister", "bhai", "family"],
}


def classify_emotion(story: str) -> str:
    if not story:
        return "nostalgic"
    story_lower = story.lower()
    for emotion, keywords in EMOTION_TAGS.items():
        for kw in keywords:
            if kw in story_lower:
                return emotion
    return "nostalgic"


async def check_ollama_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def generate_rj_script(
    song_title: str,
    artist: str,
    requester_name: str,
    dedicated_to: Optional[str] = None,
    story: Optional[str] = None,
    emotion: str = "nostalgic"
) -> str:
    """
    Generate a warm cinematic RJ announcement script.
    Tries Ollama/Llama3 first, falls back to templates.
    """
    dedication_line = f"dedicated to {dedicated_to}" if dedicated_to else ""
    story_line = f"Their story: {story}" if story else ""

    prompt = f"""You are Priya — a warm, emotionally expressive, female Indian radio jockey on Delux Radio, a 90s Bollywood station.

A listener named {requester_name} has requested "{song_title}" by {artist}. {dedication_line}
{story_line}

Write a natural, heartfelt radio announcement script (maximum 120 words) as if speaking live on air:
- Sound like a real Indian female RJ hosting a nostalgic 90s station
- Use natural Hinglish (mix of Hindi/English words felt organic)
- Be emotionally connected to the story or memory
- Add warm pauses naturally in the text using "..."  
- End by introducing the song beautifully
- DO NOT use any asterisks, stage directions, or brackets — only spoken words
- Start directly with your voice, no "Script:" or preamble

Tone: warm, {emotion}, nostalgic, like talking to a dear friend on radio.
"""

    if await check_ollama_available():
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                )
                data = response.json()
                script = data.get("response", "").strip()
                if script and len(script) > 30:
                    return script
        except Exception as e:
            print(f"⚠️ Ollama error: {e}. Using template fallback.")

    # ─── Fallback template scripts ────────────────────────────────────────────
    return _generate_template_script(song_title, artist, requester_name, dedicated_to, story, emotion)


def _generate_template_script(
    song_title: str,
    artist: str,
    requester_name: str,
    dedicated_to: Optional[str],
    story: Optional[str],
    emotion: str
) -> str:
    templates_romantic = [
        f"Aap sun rahe hain Delux Radio... aur yeh waqt hai kuch khaas ke liye. {requester_name} ne request ki hai ek bahut hi pyaari song... aur yeh dedicated hai {dedicated_to or 'kisi khaas insan'} ke liye. Dil mein jo baat hoti hai na... woh kabhi words mein poori nahi utarti. Par yeh song... yeh kuch kehta zaroor hai. Suno dhyan se... {song_title}... {artist} ki awaaz mein.",
        f"Hello Delhi, hello Delux listeners... {requester_name} ne yeh khoobsurat request bheji hai{' for ' + dedicated_to if dedicated_to else ''}. Kuch rishte itne khaas hote hain... jo sirf ek song se hi samajh aate hain. Aur yeh song... yeh woh ehsaas hai. Presenting for you... the beautiful {song_title}.",
    ]
    templates_nostalgic = [
        f"Yeh Delux Radio hai... aur kuch yaadein hoti hain jo kabhi bhoolti nahi. {requester_name} ne aaj woh yaad taaza kar di hai{' for ' + dedicated_to if dedicated_to else ''}. {story or 'Kuch pal aisa hota hai jo dil mein bas jaata hai...'} Aur is pal ke liye... presenting the timeless {song_title} by {artist}.",
        f"Suniye dosto... {requester_name} ki yeh request sunke dil bhar aaya. Woh purane din... woh mohabbat bhari yaadein... sab kuch is ek song mein milta hai. Sirf aapke liye... {song_title}... {artist} ki awaaz mein.",
    ]
    templates_emotional = [
        f"Delux Radio pe aap ka swagat hai... aur aaj {requester_name} ki ek bahut dil se request aayi hai. Zindagi mein kuch lamhe aise hote hain jo hamesha ke liye dil mein reh jaate hain... {story or 'aur woh lamha in ke liye bahut khaas hai.'}  Presenting with lots of love... {song_title} by {artist}.",
    ]
    templates_generic = [
        f"Hello hello Delux family! {requester_name} ki request aayi hai station pe... aur hum to bas yahi kehna chahte hain — shukriya itna pyaar dene ke liye. Aaj ki yeh song sirf unke liye hai{' aur ' + dedicated_to + ' ke liye bhi' if dedicated_to else ''}. Enjoy karo... {song_title} by {artist}. Coming up on Delux Radio!",
    ]

    mapping = {
        "romantic": templates_romantic,
        "nostalgic": templates_nostalgic,
        "emotional": templates_emotional,
        "heartbreak": templates_emotional,
        "friendship": templates_nostalgic,
        "family": templates_emotional,
    }
    pool = mapping.get(emotion, templates_generic)
    return random.choice(pool)

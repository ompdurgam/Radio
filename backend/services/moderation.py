"""
Content Moderation Service — Delux Radio
Keyword-based filtering with optional Ollama AI backup.
"""
import re
from typing import Tuple

# Comprehensive banned word list (profanity, slurs, sexual, harassment, hate)
BANNED_PATTERNS = [
    r'\bfuck\b', r'\bfuck(ing|er|ed)?\b', r'\bshit\b', r'\bchutiya\b',
    r'\bbhenchod\b', r'\bmadarchod\b', r'\bbc\b', r'\bmc\b',
    r'\bbitch\b', r'\basshole\b', r'\bbastard\b', r'\bdamn\b',
    r'\bharamzada\b', r'\bhamarami\b', r'\brandi\b', r'\bchut\b',
    r'\blund\b', r'\bgand\b', r'\bsex\b', r'\bporn\b', r'\bnude\b',
    r'\bsexual\b', r'\bkill\b', r'\bmurder\b', r'\bhate\b',
    r'\bslut\b', r'\bwhore\b', r'\bnigg\w+\b', r'\bfagg\w+\b',
    r'\bterror\b', r'\bbomb\b', r'\bdie\b', r'\brapist\b',
    # Obfuscation attempts (l33t speak)
    r'\bf+u+c+k+\b', r'\bs+h+i+t+\b', r'\ba+s+s+\b',
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]

SPAM_PHRASES = [
    "http://", "https://", "www.", ".com", ".net", "click here",
    "buy now", "free money", "whatsapp", "telegram"
]


async def moderate_text(text: str) -> Tuple[bool, str]:
    """
    Returns (is_safe: bool, reason: str)
    True = safe, False = blocked
    """
    if not text or not text.strip():
        return True, "OK"

    text_stripped = text.strip()

    # Length check
    if len(text_stripped) > 1000:
        return False, "Message is too long (max 1000 characters)."

    # Banned patterns check
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text_stripped):
            return False, "Content contains inappropriate language."

    # Spam link check
    text_lower = text_stripped.lower()
    for phrase in SPAM_PHRASES:
        if phrase in text_lower:
            return False, "Links and promotional content are not allowed."

    # Repeated characters spam (e.g., "aaaaaaaaaaaaa")
    if re.search(r'(.)\1{10,}', text_stripped):
        return False, "Please don't spam repeated characters."

    # All caps aggressiveness
    letters = [c for c in text_stripped if c.isalpha()]
    if len(letters) > 10 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.85:
        return False, "Please don't use ALL CAPS."

    return True, "OK"


async def moderate_request(
    song_name: str,
    requester_name: str,
    dedicated_to: str | None,
    story: str | None
) -> Tuple[bool, str]:
    """Moderate all user-provided fields in a song request."""
    fields = {
        "Song name": song_name,
        "Your name": requester_name,
        "Dedication": dedicated_to or "",
        "Story": story or "",
    }
    for field_name, value in fields.items():
        if not value:
            continue
        safe, reason = await moderate_text(value)
        if not safe:
            return False, f"{field_name}: {reason}"

    return True, "OK"


async def moderate_chat(message: str) -> Tuple[bool, str]:
    """Moderate a chat message."""
    return await moderate_text(message)

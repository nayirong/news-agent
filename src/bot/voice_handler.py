"""
Voice message support: transcription (Whisper) and TTS replies (OpenAI TTS).

Requires OPENAI_API_KEY. Voice features are disabled if the key is absent.

TTS uses OpenAI's tts-1 model with response_format="opus" so replies arrive as
proper Telegram voice message bubbles (not audio file attachments).
"""
import io
import logging
import re

logger = logging.getLogger(__name__)


class _NamedBytesIO(io.BytesIO):
    """BytesIO with a .name attribute.

    io.BytesIO is a C-extension type and does not allow setting arbitrary
    attributes directly. The OpenAI SDK reads .name to detect the file codec,
    so we subclass to carry that metadata.
    """
    def __init__(self, name: str):
        super().__init__()
        self.name = name


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

async def transcribe_voice(bot, file_id: str) -> str:
    """Download a Telegram voice file and transcribe it with OpenAI Whisper."""
    from config.settings import settings

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set — voice transcription unavailable.")

    tg_file = await bot.get_file(file_id)
    buffer = _NamedBytesIO("voice.ogg")
    await tg_file.download_to_memory(buffer)
    buffer.seek(0)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=buffer,
        language=settings.WHISPER_LANGUAGE or None,
    )
    return transcript.text.strip()


# ---------------------------------------------------------------------------
# Markdown → plain spoken text
# ---------------------------------------------------------------------------

def strip_markdown_for_tts(text: str) -> str:
    """Convert markdown-formatted bot output into clean spoken text.

    Handles the specific patterns the news bot produces:
      📰 *[Topic — Headline]*: summary  →  Topic — Headline: summary
      📎 Source: https://...            →  (removed)
      **bold**, _italic_                →  plain text
      --- dividers                      →  (removed)
      bullet points                     →  natural sentence flow
    """
    # Remove source citation lines entirely (not useful when spoken)
    text = re.sub(r'📎\s*Source:?[^\n]*', '', text)

    # [link text](url) → link text
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)

    # Bare URLs
    text = re.sub(r'https?://\S+', '', text)

    # Bold **text** or *text*
    text = re.sub(r'\*{1,2}([^*\n]+)\*{1,2}', r'\1', text)

    # Italic _text_
    text = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', text)

    # Inline code
    text = re.sub(r'`[^`]+`', '', text)

    # Markdown headers
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)

    # Horizontal rules
    text = re.sub(r'^\s*-{3,}\s*$', '', text, flags=re.MULTILINE)

    # Bullet/list markers — strip, leave the content
    text = re.sub(r'^\s*[•\-\*]\s+', '', text, flags=re.MULTILINE)

    # Emojis and other non-ASCII (📰 📎 etc.)
    text = re.sub(r'[^\x00-\x7F]', '', text)

    # Multiple blank lines → sentence break
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)

    # Clean up punctuation artifacts from the above substitutions
    text = re.sub(r'\s*\.\s*\.\s*', '. ', text)   # ". ." → "."
    text = re.sub(r'\s+', ' ', text)               # collapse spaces

    return text.strip()


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

async def text_to_voice_opus(text: str) -> io.BytesIO:
    """Convert text to OGG/Opus audio using OpenAI TTS.

    Returns OGG/Opus bytes compatible with Telegram's sendVoice endpoint,
    so the reply appears as a voice message bubble rather than a file.

    The text is cleaned of markdown before synthesis so symbols like
    asterisks and dashes are not spoken aloud.
    """
    from config.settings import settings

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set — TTS unavailable.")

    spoken_text = strip_markdown_for_tts(text)
    if not spoken_text:
        raise ValueError("Nothing left to speak after stripping markdown.")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.audio.speech.create(
        model="tts-1",          # tts-1-hd for higher quality (slower + costs more)
        voice=settings.VOICE_NAME,
        input=spoken_text,
        response_format="opus", # OGG/Opus → Telegram voice message bubble
    )

    buf = io.BytesIO(response.content)
    buf.seek(0)
    return buf

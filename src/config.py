
import os
from dotenv import load_dotenv
from pathlib import Path
import shutil
from typing import Dict, List, Optional, TypedDict

class FormatInfo(TypedDict):
    ext: str
    label: str
    cb: str

# =============================
#      Загрузка окружения
# =============================
load_dotenv()

# =============================
#        Базовые пути
# =============================
BASE_DIR = Path(__file__).resolve().parent.parent  # корень проекта = .../Bot_WiseVoiceAI
# Папки для ресурсов внутри репо (создай их и положи файлы)
FONTS_DIR = BASE_DIR / "fonts"
IMAGES_DIR = BASE_DIR / "images"

# Относительные пути к ресурсам (если файла нет — обработай в коде по месту использования)
FONT_PATH: str = os.getenv("FONT_PATH", str(FONTS_DIR / "DejaVuSans.ttf"))
CUSTOM_THUMBNAIL_PATH: str = os.getenv("CUSTOM_THUMBNAIL_PATH", str(IMAGES_DIR / "to.png"))

# ffmpeg/ffprobe (кроссплатформенно)
try:
    from imageio_ffmpeg import get_ffmpeg_exe, get_ffprobe_exe
    FFMPEG_BIN: str = get_ffmpeg_exe()
    try:
        FFPROBE_BIN: str = get_ffprobe_exe()
    except Exception:
        FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"
except Exception:
    FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
    FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"

# чтобы yt-dlp/pydub/moviepy находили ffmpeg
os.environ["PATH"] = os.pathsep.join([
    os.path.dirname(FFMPEG_BIN) if os.path.dirname(FFMPEG_BIN) else "",
    os.environ.get("PATH","")
])
os.environ["FFMPEG_BINARY"] = FFMPEG_BIN
os.environ["FFPROBE_BINARY"] = FFPROBE_BIN

# ffmpeg: в Railway путь не задаём, используем imageio-ffmpeg или системный ffmpeg
FFMPEG_DIR: str = os.getenv("FFMPEG_PATH", "")

# =============================
#          Конфигурация
# =============================
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
ASSEMBLYAI_API_KEY: Optional[str] = os.getenv("ASSEMBLYAI_API_KEY")
OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")

# Опционально: включение/выключение платежей
ENABLE_PAYMENTS: bool = os.getenv("ENABLE_PAYMENTS", "false").lower() in ("1", "true", "yes")

YOOMONEY_WALLET: Optional[str] = os.getenv("YOOMONEY_WALLET")
YOOMONEY_CLIENT_ID: Optional[str] = os.getenv("YOOMONEY_CLIENT_ID")
YOOMONEY_CLIENT_SECRET: Optional[str] = os.getenv("YOOMONEY_CLIENT_SECRET")
PAYMENT_AMOUNT: str = os.getenv("PAYMENT_AMOUNT", "100")
YOOMONEY_REDIRECT_URI: str = os.getenv("YOOMONEY_REDIRECT_URI", "YOUR_REDIRECT_URI")

# =============================
#      Проверка окружения
# =============================
required_base = [
    "TELEGRAM_BOT_TOKEN",
    "ASSEMBLYAI_API_KEY",
    # "OPENROUTER_API_KEY",  # сделай обязательным, если реально используешь всегда
]

required_payments = [
    "YOOMONEY_WALLET",
    "YOOMONEY_CLIENT_ID",
    "YOOMONEY_CLIENT_SECRET",
]

missing = [k for k in required_base if not os.getenv(k)]

if ENABLE_PAYMENTS:
    missing += [k for k in required_payments if not os.getenv(k)]

if missing:
    raise ValueError(f"Отсутствуют переменные окружения: {', '.join(sorted(set(missing)))}")

# =============================
#            Константы
# =============================
ADMIN_USER_IDS: List[int] = [5628988881]

ASSEMBLYAI_BASE_URL: str = "https://api.assemblyai.com/v2"
HEADERS: Dict[str, str] = {"authorization": ASSEMBLYAI_API_KEY}
SEGMENT_DURATION: int = 60
MESSAGE_CHUNK_SIZE: int = 4000
API_TIMEOUT: int = 300
FREE_USER_FILE_LIMIT: int = 1_000_000_000
PAID_USER_FILE_LIMIT: int = 2_000_000_000
SUBSCRIPTION_DURATION_DAYS: int = 30
SUBSCRIPTION_AMOUNT: int = int(PAYMENT_AMOUNT)

# Поддерживаемые форматы выдачи
SUPPORTED_FORMATS: Dict[str, FormatInfo] = {
    "google": {"ext": ".docx", "label": "Google Docs", "cb": "set_format_google"},
    "word":   {"ext": ".docx", "label": "Word",        "cb": "set_format_word"},
    "pdf":    {"ext": ".pdf",  "label": "PDF документ","cb": "set_format_pdf"},
    "txt":    {"ext": ".txt",  "label": "TXT",         "cb": "set_format_txt"},
    "md":     {"ext": ".md",   "label": "Markdown файл","cb": "set_format_md"},
}
DEFAULT_FORMAT: str = "pdf"

# Расширяем PATH, если FFMPEG_DIR задан вручную (но обычно не требуется)
if FFMPEG_DIR:
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), FFMPEG_DIR])

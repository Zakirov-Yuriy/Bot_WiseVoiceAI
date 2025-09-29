# import os
# from dotenv import load_dotenv

# # =============================
# #      Загрузка окружения
# # =============================
# load_dotenv()

# # =============================
# #          Конфигурация
# # =============================
# TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')
# OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
# FFMPEG_DIR = os.getenv('FFMPEG_PATH', r"D:\Programming\ffmpeg-7.1.1-essentials_build\bin")
# FONT_PATH = os.getenv('FONT_PATH', r"C:\Users\zakco\PycharmProjects\WiseVoiceAI\DejaVuSans-ExtraLight.ttf")
# CUSTOM_THUMBNAIL_PATH = os.getenv('CUSTOM_THUMBNAIL_PATH')
# YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET')
# YOOMONEY_CLIENT_ID = os.getenv('YOOMONEY_CLIENT_ID')
# YOOMONEY_CLIENT_SECRET = os.getenv('YOOMONEY_CLIENT_SECRET')
# PAYMENT_AMOUNT = os.getenv('PAYMENT_AMOUNT', "100")
# YOOMONEY_REDIRECT_URI = os.getenv('YOOMONEY_REDIRECT_URI', 'YOUR_REDIRECT_URI')

# if not all([TELEGRAM_BOT_TOKEN, ASSEMBLYAI_API_KEY, OPENROUTER_API_KEY, YOOMONEY_WALLET, YOOMONEY_CLIENT_ID, YOOMONEY_CLIENT_SECRET]):
#     raise ValueError("Не все обязательные переменные окружения установлены")

# # =============================
# #            Константы
# # =============================
# ADMIN_USER_IDS = [5628988881]  # ID пользователей с полным доступом

# ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
# HEADERS = {"authorization": ASSEMBLYAI_API_KEY}
# SEGMENT_DURATION = 60
# MESSAGE_CHUNK_SIZE = 4000
# API_TIMEOUT = 300
# FREE_USER_FILE_LIMIT = 1_000_000_000
# PAID_USER_FILE_LIMIT = 2_000_000_000
# SUBSCRIPTION_DURATION_DAYS = 30
# SUBSCRIPTION_AMOUNT = int(PAYMENT_AMOUNT)

# # Поддерживаемые форматы выдачи
# SUPPORTED_FORMATS = {
#     "google": {"ext": ".docx", "label": "Google Docs", "cb": "set_format_google"},
#     "word":   {"ext": ".docx", "label": "Word",        "cb": "set_format_word"},
#     "pdf":    {"ext": ".pdf",  "label": "PDF документ", "cb": "set_format_pdf"},
#     "txt":    {"ext": ".txt",  "label": "TXT",         "cb": "set_format_txt"},
#     "md":     {"ext": ".md",   "label": "Markdown файл","cb": "set_format_md"},
# }
# DEFAULT_FORMAT = "pdf"

# # Добавление FFMPEG в PATH
# os.environ["PATH"] += os.pathsep + FFMPEG_DIR


import os
from dotenv import load_dotenv
from pathlib import Path

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
FONT_PATH = os.getenv("FONT_PATH", str(FONTS_DIR / "DejaVuSans-ExtraLight.ttf"))
CUSTOM_THUMBNAIL_PATH = os.getenv("CUSTOM_THUMBNAIL_PATH", str(IMAGES_DIR / "to.png"))

# ffmpeg: в Railway путь не задаём, используем imageio-ffmpeg или системный ffmpeg
FFMPEG_DIR = os.getenv("FFMPEG_PATH", "")

# =============================
#          Конфигурация
# =============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Опционально: включение/выключение платежей
ENABLE_PAYMENTS = os.getenv("ENABLE_PAYMENTS", "false").lower() in ("1", "true", "yes")

YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET")
YOOMONEY_CLIENT_ID = os.getenv("YOOMONEY_CLIENT_ID")
YOOMONEY_CLIENT_SECRET = os.getenv("YOOMONEY_CLIENT_SECRET")
PAYMENT_AMOUNT = os.getenv("PAYMENT_AMOUNT", "100")
YOOMONEY_REDIRECT_URI = os.getenv("YOOMONEY_REDIRECT_URI", "YOUR_REDIRECT_URI")

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
ADMIN_USER_IDS = [5628988881]

ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
HEADERS = {"authorization": ASSEMBLYAI_API_KEY}
SEGMENT_DURATION = 60
MESSAGE_CHUNK_SIZE = 4000
API_TIMEOUT = 300
FREE_USER_FILE_LIMIT = 1_000_000_000
PAID_USER_FILE_LIMIT = 2_000_000_000
SUBSCRIPTION_DURATION_DAYS = 30
SUBSCRIPTION_AMOUNT = int(PAYMENT_AMOUNT)

# Поддерживаемые форматы выдачи
SUPPORTED_FORMATS = {
    "google": {"ext": ".docx", "label": "Google Docs", "cb": "set_format_google"},
    "word":   {"ext": ".docx", "label": "Word",        "cb": "set_format_word"},
    "pdf":    {"ext": ".pdf",  "label": "PDF документ","cb": "set_format_pdf"},
    "txt":    {"ext": ".txt",  "label": "TXT",         "cb": "set_format_txt"},
    "md":     {"ext": ".md",   "label": "Markdown файл","cb": "set_format_md"},
}
DEFAULT_FORMAT = "pdf"

# Расширяем PATH, если FFMPEG_DIR задан вручную (но обычно не требуется)
if FFMPEG_DIR:
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), FFMPEG_DIR])

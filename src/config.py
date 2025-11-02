
import os
from dotenv import load_dotenv
from pathlib import Path
import shutil
from typing import Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings

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

class AppSettings(BaseSettings):
    """Application settings with validation using Pydantic"""

    # =============================
    #          API Keys
    # =============================
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    assemblyai_api_key: str = Field(..., env="ASSEMBLYAI_API_KEY")
    openrouter_api_key_list: List[str] = Field(default_factory=list, env=None)
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", env="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="z-ai/glm-4.5-air:free", env="OPENROUTER_MODEL")
    telegram_phone: str = Field(..., env="TELEGRAM_PHONE")
    telegram_api_id: int = Field(..., env="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., env="TELEGRAM_API_HASH")

    # =============================
    #        Payment Settings
    # =============================
    enable_payments: bool = Field(default=False, env="ENABLE_PAYMENTS")
    yoomoney_wallet: Optional[str] = Field(None, env="YOOMONEY_WALLET")
    yoomoney_client_id: Optional[str] = Field(None, env="YOOMONEY_CLIENT_ID")
    yoomoney_client_secret: Optional[str] = Field(None, env="YOOMONEY_CLIENT_SECRET")
    payment_amount: int = Field(default=100, env="PAYMENT_AMOUNT")
    yoomoney_redirect_uri: Optional[str] = Field(None, env="YOOMONEY_REDIRECT_URI")
    yoomoney_base_url: str = Field(default="https://yoomoney.ru", env="YOOMONEY_BASE_URL")

    # =============================
    #        Admin Settings
    # =============================
    admin_user_ids: List[int] = Field(default=[], env="ADMIN_USER_IDS")

    # =============================
    #        API Settings
    # =============================
    assemblyai_base_url: str = Field(default="https://api.assemblyai.com/v2", env="ASSEMBLYAI_BASE_URL")
    segment_duration: int = Field(default=60, env="SEGMENT_DURATION", ge=1, le=300)
    message_chunk_size: int = Field(default=4000, env="MESSAGE_CHUNK_SIZE", ge=1000, le=4096)
    api_timeout: int = Field(default=300, env="API_TIMEOUT", ge=30, le=1800)

    # =============================
    #        User Limits
    # =============================
    free_user_file_limit: int = Field(default=1_000_000_000, env="FREE_USER_FILE_LIMIT", ge=1)
    paid_user_file_limit: int = Field(default=2_000_000_000, env="PAID_USER_FILE_LIMIT", ge=1)
    subscription_duration_days: int = Field(default=30, env="SUBSCRIPTION_DURATION_DAYS", ge=1, le=365)

    # =============================
    #        Database Settings
    # =============================
    database_url: str = Field(default="mysql+pymysql://user:password@localhost/bot_wisevoiceai", env="DATABASE_URL")

    # =============================
    #        Redis Settings
    # =============================
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_cache_ttl: int = Field(default=3600, env="REDIS_CACHE_TTL", ge=300, le=86400)  # 1 hour default
    redis_user_cache_ttl: int = Field(default=1800, env="REDIS_USER_CACHE_TTL", ge=300, le=3600)  # 30 min default

    # =============================
    #        Celery Settings
    # =============================
    celery_broker_url: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")

    # =============================
    #        Monitoring Settings
    # =============================
    sentry_dsn: Optional[str] = Field(None, env="SENTRY_DSN")
    prometheus_port: int = Field(default=8000, env="PROMETHEUS_PORT", ge=8000, le=9000)

    # =============================
    #        Bot Settings
    # =============================
    bot_username: str = Field(default="Transcribe_to_bot", env="BOT_USERNAME")
    max_file_size_mb: int = Field(default=20, env="MAX_FILE_SIZE_MB", ge=1, le=100)
    free_trials_count: int = Field(default=2, env="FREE_TRIALS_COUNT", ge=0, le=10)

    # =============================
    #        File Paths
    # =============================
    font_path: str = Field(default=str(FONTS_DIR / "DejaVuSans.ttf"), env="FONT_PATH")
    custom_thumbnail_path: str = Field(default=str(IMAGES_DIR / "to.png"), env="CUSTOM_THUMBNAIL_PATH")
    ffmpeg_path: str = Field(default="", env="FFMPEG_PATH")

    # =============================
    #        Circuit Breaker
    # =============================
    circuit_breaker_failure_threshold: int = Field(default=5, env="CIRCUIT_BREAKER_FAILURE_THRESHOLD", ge=1, le=20)
    circuit_breaker_recovery_timeout: int = Field(default=60, env="CIRCUIT_BREAKER_RECOVERY_TIMEOUT", ge=10, le=3600)

    # =============================
    #        UI Settings
    # =============================
    default_format: str = Field(default="pdf", env="DEFAULT_FORMAT")
    thumbnail_size: tuple = Field(default=(320, 320), env="THUMBNAIL_SIZE")
    thumbnail_color: tuple = Field(default=(230, 50, 50), env="THUMBNAIL_COLOR")
    support_username: str = Field(default="@Zak_Yuri", env="SUPPORT_USERNAME")
    supported_audio_formats: List[str] = Field(default=["mp3", "m4a", "flac", "wav", "ogg", "opus"], env="SUPPORTED_AUDIO_FORMATS")
    supported_video_formats: List[str] = Field(default=["mp4", "avi", "mov", "mkv", "webm", "flv"], env="SUPPORTED_VIDEO_FORMATS")

    # =============================
    #        Security Settings
    # =============================
    max_file_size_mb: int = Field(default=100, env="MAX_FILE_SIZE_MB", ge=1, le=1000)
    enable_file_validation: bool = Field(default=True, env="ENABLE_FILE_VALIDATION")
    enable_audit_logging: bool = Field(default=True, env="ENABLE_AUDIT_LOGGING")
    api_key_rotation_enabled: bool = Field(default=True, env="API_KEY_ROTATION_ENABLED")
    api_key_max_usage: int = Field(default=1000, env="API_KEY_MAX_USAGE", ge=100, le=10000)
    api_key_rotation_interval_hours: int = Field(default=1, env="API_KEY_ROTATION_INTERVAL_HOURS", ge=1, le=24)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @validator("admin_user_ids", pre=True)
    def parse_admin_user_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        elif isinstance(v, int):
            return [v]
        return v

    @validator("thumbnail_size", pre=True)
    def parse_thumbnail_size(cls, v):
        if isinstance(v, str):
            return tuple(int(x.strip()) for x in v.split(",") if x.strip())
        return v

    @validator("thumbnail_color", pre=True)
    def parse_thumbnail_color(cls, v):
        if isinstance(v, str):
            return tuple(int(x.strip()) for x in v.split(",") if x.strip())
        return v

    @validator("supported_audio_formats", pre=True)
    def parse_supported_audio_formats(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @validator("supported_video_formats", pre=True)
    def parse_supported_video_formats(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @validator("openrouter_api_key_list", pre=True)
    def parse_openrouter_api_key_list(cls, v):
        keys = []
        # Новый список ключей
        env_value = os.getenv("OPENROUTER_API_KEYS", "")
        if env_value:
            keys.extend(x.strip() for x in env_value.split(",") if x.strip())
        # Для обратной совместимости с одиночным ключом
        old_key = os.getenv("OPENROUTER_API_KEY", "")
        if old_key and old_key.strip():
            keys.append(old_key.strip())
        return keys if keys else v if isinstance(v, list) else []

# Create settings instance
settings = AppSettings()

# =============================
#      Проверка окружения
# =============================
def validate_settings():
    """Validate required settings based on enabled features"""
    errors = []

    # Always required
    if not settings.telegram_bot_token:
        errors.append("TELEGRAM_BOT_TOKEN")
    if not settings.assemblyai_api_key:
        errors.append("ASSEMBLYAI_API_KEY")

    # Payment required if enabled
    if settings.enable_payments:
        if not settings.yoomoney_wallet:
            errors.append("YOOMONEY_WALLET")
        if not settings.yoomoney_client_id:
            errors.append("YOOMONEY_CLIENT_ID")
        if not settings.yoomoney_client_secret:
            errors.append("YOOMONEY_CLIENT_SECRET")
        if not settings.yoomoney_redirect_uri:
            errors.append("YOOMONEY_REDIRECT_URI")

    if errors:
        raise ValueError(f"Отсутствуют переменные окружения: {', '.join(sorted(set(errors)))}")

# Validate on import
validate_settings()

# =============================
#        Dynamic Properties
# =============================

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

# Headers for API requests
HEADERS: Dict[str, str] = {"authorization": settings.assemblyai_api_key}

# Поддерживаемые форматы выдачи
SUPPORTED_FORMATS: Dict[str, FormatInfo] = {
    "google": {"ext": ".docx", "label": "Google Docs", "cb": "set_format_google"},
    "word":   {"ext": ".docx", "label": "Word",        "cb": "set_format_word"},
    "pdf":    {"ext": ".pdf",  "label": "PDF документ","cb": "set_format_pdf"},
    "txt":    {"ext": ".txt",  "label": "TXT",         "cb": "set_format_txt"},
    "md":     {"ext": ".md",   "label": "Markdown файл","cb": "set_format_md"},
}

# Расширяем PATH, если FFMPEG_DIR задан вручную (но обычно не требуется)
if settings.ffmpeg_path:
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), settings.ffmpeg_path])

# =============================
#        Backward Compatibility
# =============================
# Keep old variable names for backward compatibility
TELEGRAM_BOT_TOKEN: str = settings.telegram_bot_token
ASSEMBLYAI_API_KEY: str = settings.assemblyai_api_key
OPENROUTER_API_KEYS: List[str] = settings.openrouter_api_key_list
OPENROUTER_BASE_URL: str = settings.openrouter_base_url
OPENROUTER_MODEL: str = settings.openrouter_model
TELEGRAM_PHONE: str = settings.telegram_phone
TELEGRAM_API_ID: int = settings.telegram_api_id
TELEGRAM_API_HASH: str = settings.telegram_api_hash
ENABLE_PAYMENTS: bool = settings.enable_payments
YOOMONEY_WALLET: Optional[str] = settings.yoomoney_wallet
YOOMONEY_CLIENT_ID: Optional[str] = settings.yoomoney_client_id
YOOMONEY_CLIENT_SECRET: Optional[str] = settings.yoomoney_client_secret
PAYMENT_AMOUNT: int = settings.payment_amount
YOOMONEY_REDIRECT_URI: str = settings.yoomoney_redirect_uri
YOOMONEY_BASE_URL: str = settings.yoomoney_base_url
ADMIN_USER_IDS: List[int] = settings.admin_user_ids
ASSEMBLYAI_BASE_URL: str = settings.assemblyai_base_url
SEGMENT_DURATION: int = settings.segment_duration
MESSAGE_CHUNK_SIZE: int = settings.message_chunk_size
API_TIMEOUT: int = settings.api_timeout
FREE_USER_FILE_LIMIT: int = settings.free_user_file_limit
PAID_USER_FILE_LIMIT: int = settings.paid_user_file_limit
SUBSCRIPTION_DURATION_DAYS: int = settings.subscription_duration_days
SUBSCRIPTION_AMOUNT: int = settings.payment_amount
DEFAULT_FORMAT: str = settings.default_format
FONT_PATH: str = settings.font_path
CUSTOM_THUMBNAIL_PATH: str = settings.custom_thumbnail_path
FFMPEG_DIR: str = settings.ffmpeg_path
THUMBNAIL_COLOR: tuple = settings.thumbnail_color
SUPPORT_USERNAME: str = settings.support_username
SUPPORTED_AUDIO_FORMATS: List[str] = settings.supported_audio_formats
SUPPORTED_VIDEO_FORMATS: List[str] = settings.supported_video_formats
DATABASE_URL: str = settings.database_url
REDIS_URL: str = settings.redis_url
REDIS_CACHE_TTL: int = settings.redis_cache_ttl
REDIS_USER_CACHE_TTL: int = settings.redis_user_cache_ttl
CELERY_BROKER_URL: str = settings.celery_broker_url
CELERY_RESULT_BACKEND: str = settings.celery_result_backend
SENTRY_DSN: Optional[str] = settings.sentry_dsn
PROMETHEUS_PORT: int = settings.prometheus_port

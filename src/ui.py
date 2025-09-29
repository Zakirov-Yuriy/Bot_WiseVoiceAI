import time
import logging
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .localization import get_string
from .config import SUPPORTED_FORMATS, DEFAULT_FORMAT

logger = logging.getLogger(__name__)

# Хранение выборов пользователя
# {user_id: {'speakers': bool, 'plain': bool, 'timecodes': bool, 'message_id': int, 'file_path': str}}
user_selections = {}

# Персональные настройки формата выдачи: {user_id: {"format": "pdf"}}
user_settings = {}


class ProgressManager:
    """Менеджер для управления прогрессом"""

    def __init__(self):
        self.last_update_times = {}
        self.last_progress_values = {}
        self.min_update_interval = 3.0
        self.min_progress_change = 0.05

    async def update_progress(self, progress, message, lang='ru'):
        """Обновление прогресса отображаемого пользователю"""
        try:
            message_id = message.message_id
            current_time = time.time()
            last_update = self.last_update_times.get(message_id, 0)
            last_progress = self.last_progress_values.get(message_id, -1)

            if isinstance(progress, str):
                await message.edit_text(progress)
                self.last_update_times[message_id] = current_time
                return

            if (current_time - last_update < self.min_update_interval and
                    progress < 0.99 and
                    abs(progress - last_progress) < self.min_progress_change):
                return

            progress = max(0.0, min(1.0, float(progress)))
            bar_length = 10
            filled = int(progress * bar_length)
            bar = '🟪' * filled + '⬜' * (bar_length - filled)
            percent = int(progress * 100)

            if progress < 0.3:
                emoji = "📥"
                text = f"{emoji} {get_string('downloading_video', lang, bar=bar, percent=percent)}"
            elif progress < 0.7:
                emoji = "⚙️"
                text = f"{emoji} {get_string('processing_audio', lang, bar=bar, percent=percent)}"
            else:
                emoji = "📊"
                text = f"{emoji} Форматирование...\n{bar} {percent}%"

            try:
                await message.edit_text(text)
                self.last_update_times[message_id] = current_time
                self.last_progress_values[message_id] = progress
            except Exception as e:
                if "message is not modified" not in str(e):
                    logger.warning(f"Не удалось обновить прогресс: {str(e)}")
        except Exception as e:
            logger.warning(f"Ошибка обновления прогресса: {str(e)}")


progress_manager = ProgressManager()


def ensure_user_settings(user_id: int):
    if user_id not in user_settings:
        user_settings[user_id] = {"format": DEFAULT_FORMAT}


def create_menu_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оформить подписка", callback_data="subscribe")],
        [InlineKeyboardButton(text=get_string('settings', 'ru'), callback_data="settings")]
    ])
    logger.info("Создано меню с кнопками")
    return keyboard


def create_transcription_selection_keyboard(user_id: int):
    selections = user_selections.get(user_id, {'speakers': False, 'plain': False, 'timecodes': False})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"{'✅' if selections['speakers'] else '⬜'} {get_string('caption_with_speakers', 'ru')}",
                callback_data="select_speakers"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{'✅' if selections['plain'] else '⬜'} {get_string('caption_plain', 'ru')}",
                callback_data="select_plain"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{'✅' if selections['timecodes'] else '⬜'} {get_string('caption_with_timecodes', 'ru')}",
                callback_data="select_timecodes"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_string('confirm_selection', 'ru'),
                callback_data="confirm_selection"
            )
        ]
    ])
    logger.info(f"Создано меню выбора транскрипции для user_id {user_id}")
    return keyboard


def create_settings_keyboard(user_id: int):
    ensure_user_settings(user_id)
    fmt = user_settings[user_id].get("format", DEFAULT_FORMAT)

    def row(fmt_key):
        checked = "✅ " if fmt == fmt_key else ""
        return [InlineKeyboardButton(text=f"{checked}{SUPPORTED_FORMATS[fmt_key]['label']}",
                                     callback_data=SUPPORTED_FORMATS[fmt_key]['cb'])]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        row("google"),
        row("word"),
        row("pdf"),
        row("txt"),
        row("md"),
        [InlineKeyboardButton(text=get_string('back', 'ru'), callback_data="settings_back")]
    ])
    return keyboard

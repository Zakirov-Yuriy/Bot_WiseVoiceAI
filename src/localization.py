# =============================
#           Локализация
# =============================
locales = {
    'ru': {
        'welcome': "Привет! Отправьте мне аудиофайл или ссылку на YouTube для транскрибации.",
        'downloading_video': "Скачивание видео... {bar} {percent}",
        'processing_audio': "Обработка аудио... {bar} {percent}%",
        'uploading_file': "Загружаю файл для обработки...",
        'no_speech': "Не удалось распознать речь в аудио",
        'error': "Произошла ошибка: {error}",
        'done': "Обработка завершена!",
        'caption_with_speakers': "Транскрипция с распознаванием спикеров",
        'caption_plain': "Транскрипция (текст без спикеров)",
        'caption_with_timecodes': "Транскрипт с тайм-кодами",
        'invalid_link': "Пожалуйста, отправьте действительную ссылку на YouTube",
        'unsupported_format': "Неподдерживаемый формат файла",
        'try_again': "Отправляйте ссылки или файлы прямо сюда ⬇️ — и бот сделает транскрибацию за вас",
        'timeout_error': "Превышено время ожидания обработки",
        'telegram_timeout': "Таймаут соединения с Telegram",
        'no_trials': "Вы использовали 2 бесплатные попытки.\nОформите подписку: /subscribe",
        'file_too_large': "Файл слишком большой ({size} байт). Лимит: {limit} байт. Оформите подписку для увеличения лимита.",
        'menu': "Выберите команду из меню:",
        'payment_success': "🎉 Подписка успешно оформлена! Доступ открыт до {expiry_date}.",
        'payment_failed': "❌ Ошибка обработки платежа. Попробуйте снова или свяжитесь с поддержкой.",
        'select_transcription': "Выберите типы транскрипции:",
        'no_selection': "Пожалуйста, выберите хотя бы один тип транскрипции.",
        'confirm_selection': "Подтвердить выбор",
        'settings': "⚙️ Настройки",
        'settings_choose': (
            "Выберите предпочитаемый формат для получения транскрипции:\n\n"
            "• Google Docs – редактируемый документ в облаке\n"
            "• Word – документ Word для редактирования\n"
            "• PDF – удобный для чтения и печати\n"
            "• TXT – простой текстовый файл\n"
            "• Markdown – файл в формате .md"
        ),
        'back': "← Назад"
    },
    'en': {
        'welcome': "Hi! Send me an audio file or YouTube link for transcription.",
        'downloading_video': "Downloading video... {bar} {percent}",
        'processing_audio': "Processing audio... {bar} {percent}%",
        'uploading_file': "Uploading file for processing...",
        'no_speech': "No speech detected in the audio",
        'error': "An error occurred: {error}",
        'done': "Processing complete!",
        'caption_with_speakers': "Transcript with speaker identification",
        'caption_plain': "Transcript (plain text)",
        'caption_with_timecodes': "Transcript with timecodes",
        'invalid_link': "Please provide a valid YouTube link",
        'unsupported_format': "Unsupported file format",
        'try_again': "Send links or files here ⬇️ and the bot will transcribe them for you",
        'timeout_error': "Processing timeout exceeded",
        'telegram_timeout': "Telegram connection timeout",
        'no_trials': "You have used your 2 free trials.\nSubscribe: /subscribe",
        'file_too_large': "File too large ({size} bytes). Limit: {limit} bytes. Subscribe to increase the limit.",
        'menu': "Select a command from the menu:",
        'payment_success': "🎉 Subscription successfully activated! Access granted until {expiry_date}.",
        'payment_failed': "❌ Payment processing error. Try again or contact support.",
        'select_transcription': "Select transcription types:",
        'no_selection': "Please select at least one transcription type.",
        'confirm_selection': "Confirm selection",
        'settings': "⚙️ Settings",
        'settings_choose': (
            "Choose your preferred transcript format:\n\n"
            "• Google Docs – editable in Google Drive\n"
            "• Word – editable .docx\n"
            "• PDF – easy to read/print\n"
            "• TXT – plain text file\n"
            "• Markdown – .md"
        ),
        'back': "← Back"
    }
}

def get_string(key: str, lang: str = 'ru', **kwargs) -> str:
    lang_dict = locales.get(lang, locales['ru'])
    text = lang_dict.get(key, key)
    return text.format(**kwargs) if kwargs else text

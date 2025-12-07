import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramBadRequest

from src.config import TELEGRAM_BOT_TOKEN
from src.database import init_db
from src.handlers import register_handlers
from src.di import init_container
from src.cache import init_cache, close_cache
from src.metrics import init_metrics
from src.monitoring import init_sentry, SentryMiddleware
from src.middleware import RateLimitMiddleware, LoggingMiddleware, UserContextMiddleware
from src.celery_app import celery_app
from src.logging_config import setup_logging
from src.config import settings

# =============================
#        Логирование
# =============================
logger = setup_logging(
    level=settings.log_level,
    json_format=settings.log_json_format,
    log_file=settings.log_file,
    component=settings.log_component
)

# =============================
#         Команды меню
# =============================
COMMANDS = {
    "ru": [
        types.BotCommand(command="start",        description="Главное меню | Home"),
        types.BotCommand(command="user",         description="Информация о пользователе | User info"),
        types.BotCommand(command="subscription", description="Купить подписку | Get subscription"),
        types.BotCommand(command="settings",     description="Настройки | Settings"),
        types.BotCommand(command="support",      description="Поддержка | Support"),
    ],
    "en": [
        types.BotCommand(command="start",        description="Home"),
        types.BotCommand(command="user",         description="User info"),
        types.BotCommand(command="subscription", description="Get subscription"),
        types.BotCommand(command="settings",     description="Settings"),
        types.BotCommand(command="support",      description="Support"),
    ],
}

async def setup_commands(bot: Bot) -> None:
    logger.info(f"Регистрация команд меню: {COMMANDS['ru']}")
    await bot.set_my_commands(COMMANDS["ru"])
    await bot.set_my_commands(COMMANDS["ru"], language_code="ru")
    await bot.set_my_commands(COMMANDS["en"], language_code="en")
    logger.info("Команды меню зарегистрированы")
    try:
        await bot.set_chat_menu_button(menu_button=types.MenuButtonCommands())
        logger.info("Кнопка меню установлена")
    except TelegramBadRequest as e:
        logger.warning(f"Не удалось установить кнопку меню: {e}")

# =============================
#            main
# =============================
async def main():
    # Initialize monitoring and metrics
    init_sentry()
    init_metrics()

    # Initialize cache
    await init_cache()

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Setup middleware
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(UserContextMiddleware())
    dp.update.middleware(RateLimitMiddleware())
    dp.update.middleware(SentryMiddleware())

    await init_db()
    init_container()  # Initialize dependency injection container
    await setup_commands(bot)
    register_handlers(dp, bot)

    logger.info("Бот запущен с поддержкой кеширования, очередей, rate limiting и мониторинга")
    try:
        await dp.start_polling(bot)
    finally:
        # Cleanup
        await close_cache()


if __name__ == "__main__":
    asyncio.run(main())

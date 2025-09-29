import asyncio
import logging
from aiogram import Bot, Dispatcher, types

from src.config import TELEGRAM_BOT_TOKEN
from src.database import init_db
from src.handlers import register_handlers

# =============================
#        Логирование
# =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =============================
#         Команды меню
# =============================
COMMANDS = {
    "ru": [
        types.BotCommand(command="start",        description="Главное меню | Home"),
        types.BotCommand(command="subscription", description="Купить подписку | Get subscription"),
        types.BotCommand(command="settings",     description="Настройки | Settings"),
        types.BotCommand(command="support",      description="Поддержка | Support"),
    ],
    "en": [
        types.BotCommand(command="start",        description="Home"),
        types.BotCommand(command="subscription", description="Get subscription"),
        types.BotCommand(command="settings",     description="Settings"),
        types.BotCommand(command="support",      description="Support"),
    ],
}

async def setup_commands(bot: Bot):
    await bot.set_my_commands(COMMANDS["ru"])
    await bot.set_my_commands(COMMANDS["ru"], language_code="ru")
    await bot.set_my_commands(COMMANDS["en"], language_code="en")
    try:
        await bot.set_chat_menu_button(menu_button=types.MenuButtonCommands())
    except Exception as e:
        logger.warning(f"Не удалось установить кнопку меню: {e}")

# =============================
#            main
# =============================
async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    await init_db()
    await setup_commands(bot)
    register_handlers(dp, bot)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

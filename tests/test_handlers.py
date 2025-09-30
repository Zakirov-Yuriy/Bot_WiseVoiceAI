import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, User, Chat

from src.handlers import start_handler
from src import ui # Import ui to mock its functions

@pytest_asyncio.fixture
async def bot():
    """A mocked bot instance."""
    # This fixture is not strictly needed for this test anymore,
    # but it's good practice to have it for other tests.
    return Bot(
        token="1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        default=DefaultBotProperties(parse_mode="HTML")
    )

@pytest.mark.asyncio
@patch('src.handlers.ui.create_menu_keyboard')
@patch('aiogram.types.Message.answer', new_callable=AsyncMock)
async def test_start_handler(mock_answer, mock_create_keyboard):
    """Test the /start command handler by mocking message.answer."""
    mock_create_keyboard.return_value = None # We don't care about the keyboard in this test

    chat = Chat(id=123, type="private")
    user = User(id=123, is_bot=False, first_name="Test")
    message = Message(
        message_id=1,
        date=1672531200,
        chat=chat,
        from_user=user,
        text="/start"
    )

    await start_handler(message)

    # The expected text from the handler
    expected_text = (
        "🎉 *Привет!*\n\n"
        "У вас есть *2 бесплатные попытки* попробовать сервис.\n\n"
        "⚡️ Если ваш файл весит больше *20 МБ* — загрузите его в одно из популярных облачных хранилищ и отправьте мне ссылку:\n\n"
        "• [Google Drive](https://drive.google.com/)\n"
        "• [Dropbox](https://www.dropbox.com/)\n"
        "• [OneDrive](https://onedrive.live.com/)\n\n"
        "👉 Важно:\n"
        "• Файл должен быть *доступен по ссылке для всех*.\n"
        "• Размер не больше *5 ГБ*.\n\n"
        "После этого просто пришлите мне ссылку, и я все сделаю за вас 🙌"
    )

    # Assert that the mocked 'answer' method was called once
    mock_answer.assert_called_once()
    
    # Get the arguments from the mock call
    call_args = mock_answer.call_args
    
    # Assert the text and parse_mode
    assert call_args.args[0] == expected_text
    assert call_args.kwargs['parse_mode'] == 'Markdown'

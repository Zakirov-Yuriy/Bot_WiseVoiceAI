import pytest
from aiogram.types import InlineKeyboardMarkup

from src import ui
from src.localization import get_string

def test_create_menu_keyboard():
    """Tests the creation of the main menu keyboard."""
    keyboard = ui.create_menu_keyboard()
    assert isinstance(keyboard, InlineKeyboardMarkup)
    
    # Check button texts and callback data
    assert keyboard.inline_keyboard[0][0].text == "💳 Оформить подписка"
    assert keyboard.inline_keyboard[0][0].callback_data == "subscribe"
    assert keyboard.inline_keyboard[1][0].text == get_string('settings', 'ru')
    assert keyboard.inline_keyboard[1][0].callback_data == "settings"

def test_create_transcription_selection_keyboard():
    """Tests the transcription selection keyboard."""
    user_id = 123
    
    # Test with default (all false) selections
    ui.user_selections[user_id] = {'speakers': False, 'plain': False, 'timecodes': False}
    keyboard = ui.create_transcription_selection_keyboard(user_id)
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert "⬜" in keyboard.inline_keyboard[0][0].text
    assert "⬜" in keyboard.inline_keyboard[1][0].text
    assert "⬜" in keyboard.inline_keyboard[2][0].text
    assert keyboard.inline_keyboard[3][0].callback_data == "confirm_selection"

    # Test with one selection as true
    ui.user_selections[user_id]['speakers'] = True
    keyboard = ui.create_transcription_selection_keyboard(user_id)
    assert "✅" in keyboard.inline_keyboard[0][0].text
    assert "⬜" in keyboard.inline_keyboard[1][0].text
    
    # Clean up
    del ui.user_selections[user_id]

def test_create_settings_keyboard():
    """Tests the settings keyboard creation."""
    user_id = 456
    
    # Test with default settings
    ui.user_settings = {} # Reset for predictable test
    keyboard = ui.create_settings_keyboard(user_id)
    assert isinstance(keyboard, InlineKeyboardMarkup)
    
    # The default format is 'pdf', so it should be checked
    pdf_button_text = keyboard.inline_keyboard[2][0].text
    assert "✅" in pdf_button_text
    
    # Check another button to ensure it's not checked
    word_button_text = keyboard.inline_keyboard[1][0].text
    assert "✅" not in word_button_text
    
    # Check the back button
    assert keyboard.inline_keyboard[5][0].callback_data == "settings_back"

    # Test with a different setting
    ui.user_settings[user_id] = {"format": "word"}
    keyboard = ui.create_settings_keyboard(user_id)
    word_button_text = keyboard.inline_keyboard[1][0].text
    assert "✅" in word_button_text
    
    # Clean up
    del ui.user_settings[user_id]

def test_ensure_user_settings():
    """Tests the function that ensures user settings exist."""
    user_id = 789
    ui.user_settings = {} # Reset
    
    # Should create settings for a new user
    ui.ensure_user_settings(user_id)
    assert user_id in ui.user_settings
    assert ui.user_settings[user_id]['format'] == ui.DEFAULT_FORMAT
    
    # Should not overwrite existing settings
    ui.user_settings[user_id]['format'] = 'txt'
    ui.ensure_user_settings(user_id)
    assert ui.user_settings[user_id]['format'] == 'txt'
    
    # Clean up
    del ui.user_settings[user_id]

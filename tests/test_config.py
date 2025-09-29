import pytest
import os
import importlib

def test_config_loads_successfully(monkeypatch, mocker):
    """
    Tests that the config module loads without errors when all
    environment variables are set.
    """
    # Prevent .env file from interfering with the test
    mocker.patch('dotenv.load_dotenv')

    # Set all required environment variables to dummy values
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'dummy')
    monkeypatch.setenv('ASSEMBLYAI_API_KEY', 'dummy')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'dummy')
    monkeypatch.setenv('YOOMONEY_WALLET', 'dummy')
    monkeypatch.setenv('YOOMONEY_CLIENT_ID', 'dummy')
    monkeypatch.setenv('YOOMONEY_CLIENT_SECRET', 'dummy')

    # We need to reload the module to re-trigger the checks
    from src import config
    importlib.reload(config)
    # No exception means the test passes

def test_config_raises_error_on_missing_env_var(monkeypatch, mocker):
    """
    Tests that a ValueError is raised if a required environment
    variable is missing.
    """
    # Prevent .env file from interfering with the test
    mocker.patch('dotenv.load_dotenv')
    
    # Ensure all variables are set initially
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'dummy')
    monkeypatch.setenv('ASSEMBLYAI_API_KEY', 'dummy')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'dummy')
    monkeypatch.setenv('YOOMONEY_WALLET', 'dummy')
    monkeypatch.setenv('YOOMONEY_CLIENT_ID', 'dummy')
    monkeypatch.setenv('YOOMONEY_CLIENT_SECRET', 'dummy')

    # Unset one of the required variables
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN')

    # Expect a ValueError when reloading the config module
    with pytest.raises(ValueError, match="Не все обязательные переменные окружения установлены"):
        from src import config
        importlib.reload(config)

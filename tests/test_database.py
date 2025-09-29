import pytest
import sqlite3
import time
import asyncio
from unittest.mock import MagicMock, patch, call, AsyncMock

from src import database
from src.config import SUBSCRIPTION_DURATION_DAYS, ADMIN_USER_IDS

# Mocking the database connection and cursor
@pytest.fixture
def mock_db_cursor():
    """Provides a mock for sqlite3 cursor and connection."""
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock(spec=sqlite3.Cursor)
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock commit and close methods
    mock_conn.commit = MagicMock()
    mock_conn.close = MagicMock()
    
    # Mock fetchone to return None initially, simulating a new user
    mock_cursor.fetchone.return_value = None
    
    # Mock execute to capture calls
    mock_cursor.execute = MagicMock()
    
    # Mock sqlite3.connect to return our mock connection
    with patch('sqlite3.connect', return_value=mock_conn) as mock_connect:
        yield mock_conn, mock_cursor, mock_connect

@pytest.mark.asyncio
async def test_init_db(mock_db_cursor):
    """Tests the initialization of the database."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    
    await database.init_db()
    
    # Check if connect was called
    mock_connect.assert_called_once_with('users.db')
    
    # Check if cursor was obtained
    mock_conn.cursor.assert_called_once()
    
    # Check if execute was called with the correct CREATE TABLE statement
    expected_create_table_sql = '''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                trials_used INTEGER DEFAULT 0,
                is_paid BOOLEAN DEFAULT FALSE,
                subscription_expiry INTEGER DEFAULT 0
            )
        '''
    mock_cursor.execute.assert_any_call(expected_create_table_sql)
    
    # Check if commit and close were called
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

@pytest.mark.asyncio
async def test_check_user_trials_admin(mock_db_cursor):
    """Tests check_user_trials for an admin user."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    
    admin_id = ADMIN_USER_IDS[0] if ADMIN_USER_IDS else 9999
    
    can_use, is_paid = await database.check_user_trials(admin_id)
    
    assert can_use is True
    assert is_paid is True
    
    # Ensure no DB operations were performed for admin
    mock_connect.assert_not_called()
    mock_cursor.execute.assert_not_called()
    mock_conn.commit.assert_not_called()
    mock_conn.close.assert_not_called()

@pytest.mark.asyncio
async def test_check_user_trials_new_user(mock_db_cursor):
    """Tests check_user_trials for a new user."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    user_id = 1001
    
    # Mock fetchone to return None (new user)
    mock_cursor.fetchone.return_value = None
    
    can_use, is_paid = await database.check_user_trials(user_id)
    
    assert can_use is True  # New users get 2 free trials
    assert is_paid is False
    
    # Check DB operations: INSERT for new user
    mock_connect.assert_called_once_with('users.db')
    mock_conn.cursor.assert_called_once()
    
    expected_insert_sql = 'INSERT INTO users (user_id, trials_used, is_paid, subscription_expiry) VALUES (?, 0, FALSE, 0)'
    mock_cursor.execute.assert_any_call(expected_insert_sql, (user_id,))
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

@pytest.mark.asyncio
async def test_check_user_trials_with_trials(mock_db_cursor, monkeypatch):
    """Tests check_user_trials for a user with trials remaining."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    user_id = 1002
    
    # Mock fetchone to return data for a user with trials
    mock_cursor.fetchone.return_value = (1, False, 0) # trials_used=1, is_paid=False, expiry=0
    
    # Mock time.time() to control subscription expiry
    mock_time = MagicMock()
    monkeypatch.setattr(time, 'time', mock_time)
    mock_time.return_value = 1678886400 # Some arbitrary time
    
    can_use, is_paid = await database.check_user_trials(user_id)
    
    assert can_use is True
    assert is_paid is False
    
    mock_connect.assert_called_once_with('users.db')
    mock_conn.cursor.assert_called_once()
    expected_select_sql = 'SELECT trials_used, is_paid, subscription_expiry FROM users WHERE user_id = ?'
    mock_cursor.execute.assert_any_call(expected_select_sql, (user_id,))
    mock_conn.close.assert_called_once()
    # No UPDATE or INSERT should happen here, only SELECT
    assert mock_cursor.execute.call_count == 1 # Only the SELECT call

@pytest.mark.asyncio
async def test_check_user_trials_expired_subscription(mock_db_cursor, monkeypatch):
    """Tests check_user_trials for a user with an expired subscription."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    user_id = 1003
    
    # Mock time.time() to control current time
    mock_time = MagicMock()
    mock_time.return_value = 1678886400 + 2000  # Ensure it's after expired_time
    monkeypatch.setattr(time, 'time', mock_time)

    # Mock fetchone to return data for a user with an expired subscription
    expired_time = int(time.time()) - 1000 # Expired 1000 seconds ago
    mock_cursor.fetchone.return_value = (0, True, expired_time) # trials_used=0, is_paid=True, expiry=expired_time
    
    can_use, is_paid = await database.check_user_trials(user_id)
    
    assert can_use is True # Should revert to trials if subscription expired
    assert is_paid is False # is_paid should be updated to False
    
    mock_connect.assert_called_once_with('users.db')
    mock_conn.cursor.assert_called_once()
    expected_select_sql = 'SELECT trials_used, is_paid, subscription_expiry FROM users WHERE user_id = ?'
    mock_cursor.execute.assert_any_call(expected_select_sql, (user_id,))
    
    # Check that the subscription was reset
    expected_update_sql = 'UPDATE users SET is_paid = FALSE, subscription_expiry = 0 WHERE user_id = ?'
    mock_cursor.execute.assert_any_call(expected_update_sql, (user_id,))
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

@pytest.mark.asyncio
async def test_check_user_trials_active_subscription(mock_db_cursor, monkeypatch):
    """Tests check_user_trials for a user with an active subscription."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    user_id = 1004
    
    # Mock fetchone to return data for a user with an active subscription
    active_expiry_time = int(time.time()) + 1000 # Active for another 1000 seconds
    mock_cursor.fetchone.return_value = (0, True, active_expiry_time) # trials_used=0, is_paid=True, expiry=active_expiry_time
    
    # Mock time.time() to control current time
    # Set it to a fixed value that is guaranteed to be after the expired_time
    mock_time = MagicMock(return_value=1678886400 + 2000) # Ensure it's after expired_time
    monkeypatch.setattr(time, 'time', mock_time)
    
    can_use, is_paid = await database.check_user_trials(user_id)
    
    assert can_use is True
    assert is_paid is True
    
    mock_connect.assert_called_once_with('users.db')
    mock_conn.cursor.assert_called_once()
    expected_select_sql = 'SELECT trials_used, is_paid, subscription_expiry FROM users WHERE user_id = ?'
    mock_cursor.execute.assert_any_call(expected_select_sql, (user_id,))
    mock_conn.close.assert_called_once()
    # No UPDATE or INSERT should happen here, only SELECT
    assert mock_cursor.execute.call_count == 1 # Only the SELECT call

@pytest.mark.asyncio
async def test_increment_trials(mock_db_cursor):
    """Tests the increment_trials function."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    user_id = 2001

    await database.increment_trials(user_id)

    mock_connect.assert_called_once_with('users.db')
    mock_conn.cursor.assert_called_once()
    expected_update_sql = 'UPDATE users SET trials_used = trials_used + 1 WHERE user_id = ?'
    mock_cursor.execute.assert_called_once_with(expected_update_sql, (user_id,))
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

@pytest.mark.asyncio
async def test_activate_subscription(mock_db_cursor, monkeypatch):
    """Tests the activate_subscription function."""
    mock_conn, mock_cursor, mock_connect = mock_db_cursor
    user_id = 2002

    # Mock time.time() to control the expiry time
    mock_time = MagicMock(return_value=1678886400)
    monkeypatch.setattr(time, 'time', mock_time)
    expected_expiry_time = int(time.time()) + SUBSCRIPTION_DURATION_DAYS * 24 * 60 * 60

    expiry_time = await database.activate_subscription(user_id)

    assert expiry_time == expected_expiry_time
    mock_connect.assert_called_once_with('users.db')
    mock_conn.cursor.assert_called_once()
    expected_update_sql = 'UPDATE users SET is_paid = TRUE, subscription_expiry = ? WHERE user_id = ?'
    mock_cursor.execute.assert_called_once_with(expected_update_sql, (expected_expiry_time, user_id))
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

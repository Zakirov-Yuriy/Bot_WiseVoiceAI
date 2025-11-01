#!/usr/bin/env python3
"""
Test script to verify MySQL connection and basic operations
"""
import asyncio
import logging
from src.database import init_db, get_user_data, check_user_trials
from src.config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mysql_connection():
    """Test MySQL connection and basic database operations"""
    try:
        logger.info("Testing MySQL connection...")
        logger.info(f"DATABASE_URL: {DATABASE_URL}")

        # Test database initialization
        logger.info("Initializing database...")
        await init_db()
        logger.info("✅ Database initialized successfully")

        # Test creating a test user
        logger.info("Testing user creation...")
        can_use, is_paid = await check_user_trials(123456789)  # Test user ID
        logger.info(f"✅ User creation test passed: can_use={can_use}, is_paid={is_paid}")

        # Test getting user data
        logger.info("Testing user data retrieval...")
        user_data = await get_user_data(123456789)
        if user_data:
            logger.info(f"✅ User data retrieval test passed: {user_data.user_id}")
        else:
            logger.error("❌ User data retrieval test failed")

        logger.info("🎉 All MySQL connection tests passed!")

    except Exception as e:
        logger.error(f"❌ MySQL connection test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_mysql_connection())

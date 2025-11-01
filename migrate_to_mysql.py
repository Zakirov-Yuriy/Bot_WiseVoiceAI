#!/usr/bin/env python3
"""
Script to migrate data from SQLite to MySQL
"""
import asyncio
import sqlite3
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, insert
from src.models import User
from src.config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_sqlite_to_mysql():
    """Migrate data from SQLite users.db.backup to MySQL"""

    # SQLite connection
    sqlite_conn = sqlite3.connect('users.db.backup')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # MySQL async engine
    mysql_engine = create_async_engine(
        DATABASE_URL.replace("mysql+pymysql://", "mysql+aiomysql://"),
        echo=False,
        pool_pre_ping=True,
    )

    mysql_session = async_sessionmaker(mysql_engine, expire_on_commit=False)

    try:
        # Get all users from SQLite
        sqlite_cursor.execute('SELECT * FROM users')
        sqlite_users = sqlite_cursor.fetchall()

        logger.info(f"Found {len(sqlite_users)} users in SQLite database")

        async with mysql_session() as session:
            migrated_count = 0
            skipped_count = 0

            for sqlite_user in sqlite_users:
                user_data = dict(sqlite_user)

                # Check if user already exists in MySQL
                stmt = select(User).where(User.user_id == user_data['user_id'])
                result = await session.execute(stmt)
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    logger.info(f"User {user_data['user_id']} already exists in MySQL, skipping")
                    skipped_count += 1
                    continue

                # Create new user in MySQL
                user = User(
                    user_id=user_data['user_id'],
                    trials_used=user_data['trials_used'],
                    is_paid=user_data['is_paid'],
                    subscription_expiry=user_data['subscription_expiry'],
                    referrer_id=user_data['referrer_id'],
                    referral_code=user_data['referral_code'],
                    free_weeks=user_data['free_weeks']
                )

                session.add(user)
                migrated_count += 1

                # Commit every 100 users to avoid memory issues
                if migrated_count % 100 == 0:
                    await session.commit()
                    logger.info(f"Migrated {migrated_count} users so far...")

            # Final commit
            await session.commit()

            logger.info(f"Migration completed! Migrated: {migrated_count}, Skipped: {skipped_count}")

    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_sqlite_to_mysql())

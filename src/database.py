import time
import logging
import random
import string
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, insert, func
from sqlalchemy.exc import IntegrityError
from .models import User, UserData
from .config import SUBSCRIPTION_DURATION_DAYS, ADMIN_USER_IDS, DATABASE_URL

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    DATABASE_URL.replace("mysql+pymysql://", "mysql+aiomysql://"),
    echo=False,
    pool_pre_ping=True,
)

# Create async session factory
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db() -> None:
    """Initialize database - create tables if they don't exist"""
    try:
        async with engine.begin() as conn:
            # Create tables
            await conn.run_sync(User.metadata.create_all)
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise

async def check_user_trials(user_id: int, username: Optional[str] = None) -> tuple[bool, bool]:
    if user_id in ADMIN_USER_IDS:
        logger.info(f"User {user_id} is an admin, granting full access.")
        return True, True

    async with async_session() as session:
        # Try to get existing user
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            # Create new user
            user = User(
                user_id=user_id,
                username=username,
                trials_used=0,
                transcription_count=0,
                is_paid=False,
                subscription_expiry=0,
                referrer_id=None,
                referral_code=None,
                free_weeks=0
            )
            session.add(user)
            await session.commit()
            trials_used = 0
            is_paid = False
        else:
            # Update username if provided and different
            if username and user.username != username:
                user.username = username
                await session.commit()

            trials_used = user.trials_used
            is_paid = user.is_paid
            subscription_expiry = user.subscription_expiry

            # Check if subscription expired
            if is_paid and subscription_expiry > 0 and time.time() > subscription_expiry:
                user.is_paid = False
                user.subscription_expiry = 0
                await session.commit()
                is_paid = False
                logger.info(f"Подписка для user_id {user_id} истекла")

        can_use = is_paid or trials_used < 3  # Ограничение: 3 бесплатные попытки для неплатных пользователей
        logger.info(f"User {user_id}: can_use={can_use}, is_paid={is_paid}, trials_used={trials_used}")
        return can_use, is_paid

async def increment_trials(user_id: int) -> None:
    async with async_session() as session:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(trials_used=User.trials_used + 1)
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Попытки для user {user_id} обновлены")

async def increment_transcription_count(user_id: int) -> None:
    """Increment the transcription count for a user"""
    async with async_session() as session:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(transcription_count=User.transcription_count + 1)
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Количество транскрибаций для user {user_id} увеличено")

async def activate_subscription(user_id: int, weeks: int = SUBSCRIPTION_DURATION_DAYS, username: Optional[str] = None) -> int:
    async with async_session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            # Create user if doesn't exist
            user = User(
                user_id=user_id,
                username=username,
                trials_used=0,
                transcription_count=0,
                is_paid=True,
                subscription_expiry=0,
                referrer_id=None,
                referral_code=None,
                free_weeks=0
            )
            session.add(user)
        else:
            # Update username if provided
            if username and user.username != username:
                user.username = username

        current_expiry = user.subscription_expiry if user.subscription_expiry else 0
        start_time = max(int(time.time()), current_expiry) if current_expiry > int(time.time()) else int(time.time())
        expiry_time = start_time + weeks * 24 * 60 * 60

        user.is_paid = True
        user.subscription_expiry = expiry_time
        await session.commit()

        logger.info(f"Подписка активирована/продлена для user_id {user_id} до {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry_time))}")
        return expiry_time

async def get_user_data(user_id: int) -> Optional[UserData]:
    async with async_session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            return UserData(
                user_id=user.user_id,
                username=user.username,
                trials_used=user.trials_used,
                transcription_count=user.transcription_count,
                is_paid=user.is_paid,
                subscription_expiry=user.subscription_expiry,
                referrer_id=user.referrer_id,
                referral_code=user.referral_code,
                free_weeks=user.free_weeks
            )
        return None

async def update_user_referral_code(user_id: int, referral_code: str) -> None:
    async with async_session() as session:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(referral_code=referral_code)
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Реферальный код {referral_code} обновлен для user_id {user_id}")

async def update_user_referrer(user_id: int, referrer_id: int) -> None:
    async with async_session() as session:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(referrer_id=referrer_id)
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Реферер {referrer_id} установлен для user_id {user_id}")

async def add_free_weeks_to_referrer(referrer_id: int, weeks_to_add: int) -> None:
    async with async_session() as session:
        stmt = select(User).where(User.user_id == referrer_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            current_free_weeks = user.free_weeks or 0
            current_expiry = user.subscription_expiry or 0

            new_free_weeks = current_free_weeks + weeks_to_add

            start_time = max(int(time.time()), current_expiry) if current_expiry > int(time.time()) else int(time.time())
            new_expiry_time = start_time + new_free_weeks * 24 * 60 * 60

            user.free_weeks = new_free_weeks
            user.subscription_expiry = new_expiry_time
            user.is_paid = True
            await session.commit()

            logger.info(f"Рефереру {referrer_id} добавлено {weeks_to_add} бесплатных недель. Новая подписка до {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_expiry_time))}")

async def consume_free_week(user_id: int) -> bool:
    async with async_session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user and user.free_weeks and user.free_weeks > 0:
            user.free_weeks = user.free_weeks - 1
            await session.commit()
            logger.info(f"У пользователя {user_id} использована одна бесплатная неделя. Осталось: {user.free_weeks}")
            return True
        return False

async def generate_and_set_referral_code(user_id: int) -> Optional[str]:
    user_data = await get_user_data(user_id)
    if user_data and user_data.referral_code:
        logger.info(f"У пользователя {user_id} уже есть реферальный код.")
        return user_data.referral_code

    async with async_session() as session:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

            # Check if code already exists
            stmt = select(User).where(User.referral_code == code)
            result = await session.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user is None:
                # Code is unique, update user
                update_stmt = (
                    update(User)
                    .where(User.user_id == user_id)
                    .values(referral_code=code)
                )
                await session.execute(update_stmt)
                await session.commit()
                logger.info(f"Сгенерирован и установлен реферальный код {code} для user_id {user_id}")
                return code

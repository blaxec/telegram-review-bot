# file: database/db_manager.py

import datetime
import logging # <-- ДОБАВЛЕН ИМПОРТ
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, update, and_, delete
from sqlalchemy.orm import selectinload
from typing import Union

from database.models import Base, User, Review, Link
from config import DATABASE_URL

logger = logging.getLogger(__name__) # <-- ДОБАВЛЕН ЛОГГЕР

# Убираем создание engine и async_session отсюда
engine = None
async_session = None


async def init_db():
    global engine, async_session
    
    # Создаем engine и сессию здесь, когда DATABASE_URL уже точно определен
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def ensure_user_exists(user_id: int, username: str, referrer_id: int = None):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                new_user = User(id=user_id, username=username, referrer_id=referrer_id)
                session.add(new_user)

async def get_user(user_id: int) -> Union[User, None]:
    async with async_session() as session:
        return await session.get(User, user_id)

async def get_user_balance(user_id: int) -> tuple[float, float]:
    user = await get_user(user_id)
    # ИЗМЕНЕНО: Добавлено логирование для отладки
    if user:
        logger.info(f"DB get_user_balance for user {user_id}: Found user. Raw balance: '{user.balance}' (type: {type(user.balance)})")
        return (user.balance, user.hold_balance)
    else:
        logger.warning(f"DB get_user_balance for user {user_id}: User not found. Returning (0.0, 0.0)")
        return (0.0, 0.0)

async def update_balance(user_id: int, amount: float):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                user.balance += amount

async def get_referrer_info(user_id: int) -> str:
    user = await get_user(user_id)
    if user and user.referrer_id:
        referrer = await get_user(user.referrer_id)
        return f"@{referrer.username}" if referrer and referrer.username else f"ID: {user.referrer_id}"
    return "-"

async def find_user_by_identifier(identifier: str) -> Union[int, None]:
    async with async_session() as session:
        try:
            user_id = int(identifier)
            query = select(User.id).where(User.id == user_id)
        except (ValueError, TypeError):
            username = identifier.lstrip('@')
            query = select(User.id).where(User.username == username)
        result = await session.execute(query)
        return result.scalar_one_or_none()

async def transfer_stars(sender_id: int, recipient_id: int, amount: float) -> bool:
    async with async_session() as session:
        async with session.begin():
            sender = await session.get(User, sender_id)
            recipient = await session.get(User, recipient_id)
            if not sender or not recipient or sender.balance < amount:
                return False
            sender.balance -= amount
            recipient.balance += amount
        return True

async def get_referrals(user_id: int) -> list:
    async with async_session() as session:
        query = select(User.username).where(User.referrer_id == user_id)
        result = await session.execute(query)
        return result.scalars().all()
        
async def get_referral_earnings(user_id: int) -> float:
    user = await get_user(user_id)
    return user.referral_earnings if user else 0.0

async def claim_referral_earnings(user_id: int):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user and user.referral_earnings > 0:
                user.balance += user.referral_earnings
                user.referral_earnings = 0

async def check_platform_cooldown(user_id: int, platform: str) -> Union[datetime.timedelta, None]:
    user = await get_user(user_id)
    if not user:
        return None
    cooldown_field = f"{platform}_cooldown_until"
    cooldown_end_time = getattr(user, cooldown_field, None)
    if cooldown_end_time and cooldown_end_time > datetime.datetime.utcnow():
        return cooldown_end_time - datetime.datetime.utcnow()
    return None

async def set_platform_cooldown(user_id: int, platform: str, hours: int):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                cooldown_field = f"{platform}_cooldown_until"
                setattr(user, cooldown_field, datetime.datetime.utcnow() + datetime.timedelta(hours=hours))

async def add_user_warning(user_id: int, platform: str, hours_block: int = 24) -> int:
    current_warnings = 0
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return 0
            user.warnings += 1
            current_warnings = user.warnings
            if user.warnings >= 3:
                cooldown_field = f"{platform}_cooldown_until"
                setattr(user, cooldown_field, datetime.datetime.utcnow() + datetime.timedelta(hours=hours_block))
                user.warnings = 0
    return current_warnings

async def create_review_draft(user_id: int, link_id: int, platform: str, text: str, admin_message_id: int) -> int:
    review_id = 0
    async with async_session() as session:
        async with session.begin():
            new_review = Review(
                user_id=user_id,
                link_id=link_id,
                platform=platform,
                status='pending',
                review_text=text,
                admin_message_id=admin_message_id
            )
            session.add(new_review)
            await session.flush()
            review_id = new_review.id
    return review_id

async def move_review_to_hold(review_id: int, amount: float, hold_days: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review or review.status != 'pending':
                return False
            
            user = await session.get(User, review.user_id)
            if not user:
                return False

            review.status = 'on_hold'
            review.amount = amount
            review.hold_until = datetime.datetime.utcnow() + datetime.timedelta(days=hold_days)
            user.hold_balance += amount
        return True

async def get_user_hold_reviews(user_id: int) -> list:
    async with async_session() as session:
        query = select(Review).where(and_(Review.user_id == user_id, Review.status == 'on_hold'))
        result = await session.execute(query)
        return result.scalars().all()

async def get_review_by_id(review_id: int) -> Union[Review, None]:
    async with async_session() as session:
        query = select(Review).where(Review.id == review_id).options(selectinload(Review.link))
        result = await session.execute(query)
        return result.scalar_one_or_none()

async def admin_reject_review(review_id: int) -> Union[Review, None]:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review or review.status not in ['pending', 'on_hold']:
                return None
            
            user = await session.get(User, review.user_id)
            if user and review.status == 'on_hold':
                user.hold_balance -= review.amount
            
            review.status = 'rejected'
            return review

async def admin_approve_review(review_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review or review.status != 'on_hold':
                return False
            user = await session.get(User, review.user_id)
            if user:
                user.hold_balance -= review.amount
                user.balance += review.amount
            review.status = 'approved'
        return True

async def get_all_hold_reviews() -> list[Review]:
    async with async_session() as session:
        query = select(Review).where(Review.status == 'on_hold')
        result = await session.execute(query)
        return result.scalars().all()

async def db_add_reference(url: str, platform: str) -> bool:
    async with async_session() as session:
        async with session.begin():
            exists_query = select(Link.id).where(Link.url == url)
            result = await session.execute(exists_query)
            if result.scalar_one_or_none():
                return False
            new_link = Link(url=url, platform=platform)
            session.add(new_link)
        return True

async def db_get_available_reference(platform: str) -> Union[Link, None]:
    async with async_session() as session:
        async with session.begin():
            query = select(Link).where(
                Link.platform == platform,
                Link.status == 'available'
            ).limit(1).with_for_update()
            result = await session.execute(query)
            link = result.scalar_one_or_none()
            return link

async def db_update_link_status(link_id: int, status: str, user_id: int | None = None):
    async with async_session() as session:
        async with session.begin():
            stmt = update(Link).where(Link.id == link_id).values(
                status=status, 
                assigned_to_user_id=user_id,
                assigned_at=datetime.datetime.utcnow() if status == 'assigned' else None
            )
            await session.execute(stmt)

async def db_get_all_references(platform: str) -> list[Link]:
    async with async_session() as session:
        query = select(Link).where(Link.platform == platform)
        result = await session.execute(query)
        return result.scalars().all()

async def db_delete_reference(link_id: int):
    async with async_session() as session:
        async with session.begin():
            unlink_stmt = update(Review).where(Review.link_id == link_id).values(link_id=None)
            await session.execute(unlink_stmt)
            
            delete_stmt = delete(Link).where(Link.id == link_id)
            await session.execute(delete_stmt)

async def db_get_link_by_id(link_id: int) -> Union[Link, None]:
    async with async_session() as session:
        return await session.get(Link, link_id)
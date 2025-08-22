# file: telegram-review-bot-main/database/db_manager.py

import datetime
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, update, and_, delete, func, desc, case
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from typing import Union, List, Tuple

from database.models import Base, User, Review, Link, WithdrawalRequest, PromoCode, PromoActivation, SupportTicket
from config import DATABASE_URL, Durations, Limits

logger = logging.getLogger(__name__)

engine = None
async_session = None


async def init_db():
    global engine, async_session
    
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def ensure_user_exists(user_id: int, username: str, referrer_id: int = None):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                valid_referrer_id = None
                if referrer_id:
                    referrer_user = await session.get(User, referrer_id)
                    if referrer_user:
                        valid_referrer_id = referrer_id
                    else:
                        logger.warning(
                            f"User {user_id} tried to register with non-existent referrer_id {referrer_id}. "
                            f"Proceeding without referral."
                        )
                
                new_user = User(id=user_id, username=username, referrer_id=valid_referrer_id)
                session.add(new_user)


async def get_user(user_id: int) -> Union[User, None]:
    async with async_session() as session:
        return await session.get(User, user_id, options=[selectinload(User.reviews)])

async def get_user_balance(user_id: int) -> tuple[float, float]:
    user = await get_user(user_id)
    if user:
        return (user.balance, user.hold_balance)
    else:
        logger.warning(f"DB get_user_balance for user {user_id}: User not found. Returning (0.0, 0.0)")
        return (0.0, 0.0)

async def toggle_anonymity(user_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return False
            user.is_anonymous_in_stats = not user.is_anonymous_in_stats
            new_status = user.is_anonymous_in_stats
            return new_status

async def update_balance(user_id: int, amount: float):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                user.balance += amount

async def update_username(user_id: int, new_username: str):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                user.username = new_username

async def add_referral_earning(user_id: int, amount: float):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user and user.referrer_id:
                referrer = await session.get(User, user.referrer_id)
                if referrer:
                    referrer.referral_earnings += amount
                    logger.info(f"Added {amount} stars to referrer {referrer.id} from user {user_id}")

async def get_referrer_info(user_id: int) -> str:
    async with async_session() as session:
        query_referrer_id = select(User.referrer_id).where(User.id == user_id)
        result_referrer_id = await session.execute(query_referrer_id)
        referrer_id = result_referrer_id.scalar_one_or_none()

        if referrer_id:
            query_username = select(User.username).where(User.id == referrer_id)
            result_username = await session.execute(query_username)
            username = result_username.scalar_one_or_none()
            return f"@{username}" if username else f"ID: {referrer_id}"
        
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

async def add_user_warning(user_id: int, platform: str, hours_block: int = Durations.COOLDOWN_WARNING_BLOCK_HOURS) -> int:
    current_warnings = 0
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return 0
            user.warnings += 1
            current_warnings = user.warnings
            if user.warnings >= Limits.WARNINGS_THRESHOLD_FOR_BAN:
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

async def move_review_to_hold(review_id: int, amount: float, hold_minutes: int) -> bool:
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
            review.hold_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=hold_minutes)
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

async def admin_approve_review(review_id: int) -> Union[Review, None]:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review or review.status != 'on_hold':
                return None
            user = await session.get(User, review.user_id)
            if user:
                user.hold_balance -= review.amount
                user.balance += review.amount
            review.status = 'approved'
            return review

async def get_all_hold_reviews() -> list[Review]:
    async with async_session() as session:
        query = select(Review).where(Review.status == 'on_hold').options(selectinload(Review.link))
        result = await session.execute(query)
        return result.scalars().all()

async def db_add_reference(url: str, platform: str) -> bool:
    async with async_session() as session:
        async with session.begin():
            new_link = Link(url=url, platform=platform)
            session.add(new_link)
        return True

async def db_get_available_reference(platform: str) -> Union[Link, None]:
    async with async_session() as session:
        async with session.begin():
            stmt = select(Link.id).where(
                Link.platform == platform,
                Link.status == 'available'
            ).limit(1).with_for_update(skip_locked=True)
            
            result = await session.execute(stmt)
            link_id = result.scalar_one_or_none()
            
            if link_id:
                link_obj = await session.get(Link, link_id)
                return link_obj
            return None

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

async def create_withdrawal_request(user_id: int, amount: float, recipient_info: str, comment: str = None) -> Union[int, None]:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user or user.balance < amount:
                return None
            
            user.balance -= amount
            
            new_request = WithdrawalRequest(
                user_id=user_id,
                amount=amount,
                recipient_info=recipient_info,
                comment=comment
            )
            session.add(new_request)
            await session.flush()
            return new_request.id

async def get_withdrawal_request(request_id: int) -> Union[WithdrawalRequest, None]:
    async with async_session() as session:
        return await session.get(WithdrawalRequest, request_id, options=[selectinload(WithdrawalRequest.user)])

async def approve_withdrawal_request(request_id: int) -> Union[WithdrawalRequest, None]:
    async with async_session() as session:
        async with session.begin():
            request = await session.get(WithdrawalRequest, request_id)
            if not request or request.status != 'pending':
                return None
            request.status = 'approved'
            return request

async def reject_withdrawal_request(request_id: int) -> Union[WithdrawalRequest, None]:
    async with async_session() as session:
        async with session.begin():
            request = await session.get(WithdrawalRequest, request_id)
            if not request or request.status != 'pending':
                return None
            
            user = await session.get(User, request.user_id)
            if user:
                user.balance += request.amount
            
            request.status = 'rejected'
            return request

async def reset_user_cooldowns(user_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return False
            
            user.google_cooldown_until = None
            user.yandex_with_text_cooldown_until = None
            user.yandex_without_text_cooldown_until = None
            user.gmail_cooldown_until = None
            user.blocked_until = None
            user.warnings = 0
            logger.info(f"All cooldowns and warnings have been reset for user {user_id}.")
            return True

async def get_top_10_users() -> List[Tuple[str, float, int]]:
    async with async_session() as session:
        query = (
            select(
                case(
                    (User.is_anonymous_in_stats, "Анонимный пользователь"),
                    else_=User.username
                ).label("display_name"),
                User.balance,
                func.count(Review.id).label("approved_reviews")
            )
            .join(Review, and_(User.id == Review.user_id, Review.status == 'approved'), isouter=True)
            .group_by(User.id)
            .order_by(desc(User.balance))
            .limit(10)
        )
        
        result = await session.execute(query)
        return result.all()

# --- Функции для работы с промокодами ---

async def create_promo_code(code: str, condition: str, reward: float, total_uses: int) -> Union[PromoCode, None]:
    async with async_session() as session:
        async with session.begin():
            existing = await session.execute(select(PromoCode).where(func.upper(PromoCode.code) == func.upper(code)))
            if existing.scalar_one_or_none():
                return None
            
            new_promo = PromoCode(
                code=code,
                condition=condition,
                reward=reward,
                total_uses=total_uses
            )
            session.add(new_promo)
            await session.flush()
            await session.refresh(new_promo)
            return new_promo

async def get_promo_by_code(code: str) -> Union[PromoCode, None]:
    async with async_session() as session:
        result = await session.execute(select(PromoCode).where(func.upper(PromoCode.code) == func.upper(code)))
        return result.scalar_one_or_none()

async def get_user_promo_activation(user_id: int, promo_code_id: int) -> Union[PromoActivation, None]:
    async with async_session() as session:
        result = await session.execute(
            select(PromoActivation).where(
                and_(
                    PromoActivation.user_id == user_id,
                    PromoActivation.promo_code_id == promo_code_id
                )
            )
        )
        return result.scalar_one_or_none()

async def find_pending_promo_activation(user_id: int, condition: str = '%') -> Union[PromoActivation, None]:
    async with async_session() as session:
        base_query = select(PromoActivation).join(PromoCode).where(
            and_(
                PromoActivation.user_id == user_id,
                PromoActivation.status == 'pending_condition'
            )
        )

        if condition != '%':
            query = base_query.where(PromoCode.condition == condition)
        else:
            query = base_query

        result = await session.execute(
            query.options(selectinload(PromoActivation.promo_code)).limit(1)
        )
        return result.scalar_one_or_none()
        
async def create_promo_activation(user_id: int, promo: PromoCode, status: str) -> PromoActivation:
    async with async_session() as session:
        async with session.begin():
            new_activation = PromoActivation(
                user_id=user_id,
                promo_code_id=promo.id,
                status=status
            )
            session.add(new_activation)
            if status == 'completed':
                promo.current_uses += 1
            await session.flush()
            await session.refresh(new_activation)
            return new_activation

async def delete_promo_activation(activation_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            activation = await session.get(PromoActivation, activation_id)
            if not activation:
                return False
            await session.delete(activation)
            return True

async def complete_promo_activation(activation_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            activation = await session.get(PromoActivation, activation_id, options=[selectinload(PromoActivation.promo_code)])
            if not activation or activation.status != 'pending_condition':
                return False
            
            activation.status = 'completed'
            activation.promo_code.current_uses += 1
            return True

# --- Функции для системы поддержки ---

async def create_support_ticket(user_id: int, username: str, question: str, admin_message_ids: dict) -> SupportTicket:
    async with async_session() as session:
        async with session.begin():
            new_ticket = SupportTicket(
                user_id=user_id,
                username=username,
                question=question,
                admin_message_id_1=admin_message_ids.get(0),
                admin_message_id_2=admin_message_ids.get(1)
            )
            session.add(new_ticket)
            await session.flush()
            await session.refresh(new_ticket)
            return new_ticket

async def get_support_ticket(ticket_id: int) -> Union[SupportTicket, None]:
    async with async_session() as session:
        return await session.get(SupportTicket, ticket_id)

async def claim_support_ticket(ticket_id: int, admin_id: int) -> Union[SupportTicket, None]:
    async with async_session() as session:
        async with session.begin():
            ticket = await session.get(SupportTicket, ticket_id)
            if not ticket or ticket.status != 'open':
                return None
            
            ticket.status = 'claimed'
            ticket.admin_id = admin_id
            return ticket

async def close_support_ticket(ticket_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            ticket = await session.get(SupportTicket, ticket_id)
            if not ticket:
                return False
            
            ticket.status = 'closed'
            return True

# --- ИЗМЕНЕНИЕ: Новые функции для системы бана и просроченных ссылок ---

async def reset_all_expired_links() -> int:
    """Сбрасывает статус всех 'expired' ссылок на 'available'."""
    async with async_session() as session:
        async with session.begin():
            stmt = update(Link).where(Link.status == 'expired').values(status='available')
            result = await session.execute(stmt)
            return result.rowcount

async def ban_user(user_id: int) -> bool:
    """Устанавливает пользователю флаг is_banned = True."""
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return False
            user.is_banned = True
            return True

async def unban_user(user_id: int) -> bool:
    """Устанавливает пользователю флаг is_banned = False."""
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return False
            user.is_banned = False
            return True

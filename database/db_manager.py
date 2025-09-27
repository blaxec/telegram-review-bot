## file: telegram-review-bot-main/database/db_manager.py

import datetime
import logging
from typing import Union, List, Tuple, Dict, Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, update, and_, delete, func, desc, case, insert
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from database.models import (Base, User, Review, Link, WithdrawalRequest, 
                             PromoCode, PromoActivation, SupportTicket,
                             RewardSetting, SystemSetting, OperationHistory, UnbanRequest,
                             InternshipApplication, InternshipTask, InternshipMistake)
from config import DATABASE_URL, Durations, Limits, TRANSFER_COMMISSION_PERCENT

logger = logging.getLogger(__name__)

engine = None
async_session = None


async def init_db():
    global engine, async_session
    
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- Операции с историей ---
async def log_operation(session, user_id: int, op_type: str, amount: float, description: str):
    """Записывает операцию в историю. Использует переданную сессию."""
    new_op = OperationHistory(
        user_id=user_id,
        operation_type=op_type,
        amount=amount,
        description=description
    )
    session.add(new_op)

async def get_operation_history(user_id: int, limit: int = 6) -> List[OperationHistory]:
    """Получает последние N операций пользователя за 24 часа."""
    async with async_session() as session:
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        query = (
            select(OperationHistory)
            .where(
                and_(
                    OperationHistory.user_id == user_id,
                    OperationHistory.created_at >= time_threshold
                )
            )
            .order_by(desc(OperationHistory.created_at))
            .limit(limit)
        )
        result = await session.execute(query)
        return result.scalars().all()

# --- Операции с пользователями ---
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
        return await session.get(User, user_id, options=[selectinload(User.reviews), selectinload(User.internship_tasks)])


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

async def update_balance(user_id: int, amount: float, op_type: str = None, description: str = None):
    """Обновляет баланс и опционально логирует операцию."""
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                user.balance += amount
                if op_type:
                    await log_operation(session, user_id, op_type, amount, description)


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
    """Переводит звезды с учетом комиссии."""
    async with async_session() as session:
        async with session.begin():
            sender = await session.get(User, sender_id)
            recipient = await session.get(User, recipient_id)
            
            commission = amount * (TRANSFER_COMMISSION_PERCENT / 100)
            total_to_deduct = amount + commission
            
            if not sender or not recipient or sender.balance < total_to_deduct:
                return False
                
            sender.balance -= total_to_deduct
            recipient.balance += amount
            
            await log_operation(session, sender_id, "TRANSFER_SENT", -amount, f"Получатель: {recipient.username or recipient_id}")
            if commission > 0:
                await log_operation(session, sender_id, "FINE", -commission, f"Комиссия за перевод")
            await log_operation(session, recipient_id, "TRANSFER_RECEIVED", amount, f"Отправитель: {sender.username or sender_id}")

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
                earnings = user.referral_earnings
                user.balance += earnings
                user.referral_earnings = 0
                await log_operation(session, user_id, "TOP_REWARD", earnings, "Сбор реферальных наград")


async def check_platform_cooldown(user_id: int, platform: str) -> Union[datetime.timedelta, None]:
    user = await get_user(user_id)
    if not user:
        return None
    cooldown_field = f"{platform}_cooldown_until"
    cooldown_end_time = getattr(user, cooldown_field, None)
    if cooldown_end_time and cooldown_end_time > datetime.datetime.utcnow():
        return cooldown_end_time - datetime.datetime.utcnow()
    return None

async def set_platform_cooldown(user_id: int, platform: str, hours: float) -> Union[datetime.datetime, None]:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                cooldown_field = f"{platform}_cooldown_until"
                end_time = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
                setattr(user, cooldown_field, end_time)
                return end_time
            return None

async def add_user_warning(user_id: int, platform: str, hours_block: int = Durations.COOLDOWN_WARNING_BLOCK_HOURS) -> int:
    current_warnings = 0
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id, with_for_update=True)
            if not user:
                return 0
            user.warnings += 1
            current_warnings = user.warnings
            if user.warnings >= Limits.WARNINGS_THRESHOLD_FOR_BAN:
                cooldown_field = f"{platform}_cooldown_until"
                setattr(user, cooldown_field, datetime.datetime.utcnow() + datetime.timedelta(hours=hours_block))
                user.warnings = 0
    return current_warnings

async def create_review_draft(user_id: int, link_id: int, platform: str, text: str, admin_message_id: int, screenshot_file_id: str = None, attached_photo_file_id: str = None) -> int:
    review_id = 0
    async with async_session() as session:
        async with session.begin():
            new_review = Review(
                user_id=user_id,
                link_id=link_id,
                platform=platform,
                status='pending',
                review_text=text,
                admin_message_id=admin_message_id,
                screenshot_file_id=screenshot_file_id,
                attached_photo_file_id=attached_photo_file_id
            )
            session.add(new_review)
            await session.flush()
            review_id = new_review.id
    return review_id

async def db_update_review_admin_message_id(review_id: int, admin_message_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review:
                logger.error(f"Attempted to update admin_message_id for non-existent review {review_id}")
                return False
            review.admin_message_id = admin_message_id
            return True


async def move_review_to_hold(review_id: int, amount: float, hold_minutes: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review or review.status != 'pending':
                logger.error(f"Failed to move review {review_id} to hold. Status was not 'pending'.")
                return False
            
            user = await session.get(User, review.user_id)
            if not user:
                logger.error(f"Failed to move review {review_id} to hold. User {review.user_id} not found.")
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
        query = select(Review).where(Review.id == review_id).options(selectinload(Review.link), selectinload(Review.user))
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
            if not review or review.status not in ['on_hold', 'awaiting_confirmation']:
                logger.warning(f"Admin approve failed for review {review_id}. Status was {review.status}, not 'awaiting_confirmation' or 'on_hold'.")
                return None
            
            user = await session.get(User, review.user_id)
            if user:
                if user.hold_balance >= review.amount:
                    user.hold_balance -= review.amount
                else:
                    logger.warning(f"User {user.id} hold balance ({user.hold_balance}) is less than review amount ({review.amount}) for review {review_id}. Setting hold to 0.")
                    user.hold_balance = 0
                
                user.balance += review.amount
                await log_operation(session, user.id, "REVIEW_APPROVED", review.amount, f"Отзыв #{review.id} ({review.platform})")

            review.status = 'approved'
            return review

async def get_all_hold_reviews() -> list[Review]:
    async with async_session() as session:
        query = select(Review).where(Review.status == 'on_hold').options(selectinload(Review.link))
        result = await session.execute(query)
        return result.scalars().all()

async def db_add_reference(url: str, platform: str, is_fast_track: bool = False, requires_photo: bool = False) -> bool:
    async with async_session() as session:
        async with session.begin():
            new_link = Link(url=url, platform=platform, is_fast_track=is_fast_track, requires_photo=requires_photo)
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

async def db_get_paginated_references(platform: str, page: int, limit: int, filter_type: str = "all") -> Tuple[int, List[Link]]:
    async with async_session() as session:
        base_query = select(Link).where(Link.platform == platform)
        count_query = select(func.count(Link.id)).where(Link.platform == platform)
        
        if filter_type == 'fast':
            base_query = base_query.where(Link.is_fast_track == True)
            count_query = count_query.where(Link.is_fast_track == True)
        elif filter_type == 'photo':
            base_query = base_query.where(Link.requires_photo == True)
            count_query = count_query.where(Link.requires_photo == True)
        elif filter_type == 'regular':
            base_query = base_query.where(Link.is_fast_track == False, Link.requires_photo == False)
            count_query = count_query.where(Link.is_fast_track == False, Link.requires_photo == False)

        total_count = await session.scalar(count_query)
        
        paginated_query = base_query.order_by(desc(Link.id)).offset((page - 1) * limit).limit(limit)
        result = await session.execute(paginated_query)
        links = result.scalars().all()
        
        return total_count, links
        
async def db_get_link_stats(platform: str) -> Dict[str, int]:
    async with async_session() as session:
        query = (
            select(
                Link.status,
                func.count(Link.id)
            )
            .where(Link.platform == platform)
            .group_by(Link.status)
        )
        result = await session.execute(query)
        stats = {status: count for status, count in result.all()}
        
        total_query = select(func.count(Link.id)).where(Link.platform == platform)
        total_count = await session.scalar(total_query)
        stats['total'] = total_count
        
        return stats

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
            await log_operation(session, user_id, "WITHDRAWAL", -amount, f"Запрос на вывод для {recipient_info}")
            
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
                await log_operation(session, user.id, "WITHDRAWAL", request.amount, "Отклонение запроса на вывод")
            
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

async def get_top_10_users() -> List[Tuple[int, str, float, int]]:
    async with async_session() as session:
        query = (
            select(
                User.id,
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

async def get_promo_by_code(code: str, for_update: bool = False) -> Union[PromoCode, None]:
    async with async_session() as session:
        async with session.begin():
            stmt = select(PromoCode).where(func.upper(PromoCode.code) == func.upper(code))
            if for_update:
                stmt = stmt.with_for_update()
            
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

async def get_promo_by_id(promo_id: int) -> Union[PromoCode, None]:
    async with async_session() as session:
        return await session.get(PromoCode, promo_id)

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
        
async def create_promo_activation(user_id: int, promo_id: int, status: str) -> PromoActivation:
    async with async_session() as session:
        async with session.begin():
            new_activation = PromoActivation(
                user_id=user_id,
                promo_code_id=promo_id,
                status=status
            )
            session.add(new_activation)
            if status == 'completed':
                promo_to_update = await session.get(PromoCode, promo_id, with_for_update=True)
                if promo_to_update:
                    promo_to_update.current_uses += 1
                else:
                    logger.error(f"Could not increment promo uses for id {promo_id} as it was not found.")
                    raise IntegrityError("Promo code not found during activation.", params=None, orig=None)

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
            
            promo_to_update = await session.get(PromoCode, activation.promo_code_id, with_for_update=True)
            if promo_to_update.current_uses >= promo_to_update.total_uses:
                logger.warning(f"Promo '{promo_to_update.code}' has no uses left, but user {activation.user_id} tried to complete it.")
                return False

            activation.status = 'completed'
            promo_to_update.current_uses += 1
            return True

# --- Функции для системы поддержки ---
async def create_support_ticket(user_id: int, username: str, question: str, admin_message_ids: dict, photo_file_id: str = None) -> SupportTicket:
    async with async_session() as session:
        async with session.begin():
            new_ticket = SupportTicket(
                user_id=user_id,
                username=username,
                question=question,
                admin_message_id_1=admin_message_ids.get(0),
                admin_message_id_2=admin_message_ids.get(1),
                photo_file_id=photo_file_id
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

async def add_support_warning_and_cooldown(user_id: int, hours: int = None) -> int:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return 0
            
            user.support_warnings += 1
            current_warnings = user.support_warnings

            if hours is not None and hours > 0:
                user.support_cooldown_until = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
            
            return current_warnings

# --- Функции для верификации после холда ---
async def get_reviews_past_hold() -> List[Review]:
    async with async_session() as session:
        now = datetime.datetime.utcnow()
        query = select(Review).where(
            and_(
                Review.status == 'on_hold',
                Review.hold_until <= now
            )
        )
        result = await session.execute(query)
        return result.scalars().all()

async def update_review_status(review_id: int, new_status: str) -> bool:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review:
                return False
            review.status = new_status
            return True

async def save_confirmation_screenshot(review_id: int, file_id: str) -> bool:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review:
                return False
            review.confirmation_screenshot_file_id = file_id
            return True

async def cancel_hold(review_id: int) -> Optional[Review]:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id, options=[selectinload(Review.user)])
            if not review or review.status != 'awaiting_confirmation':
                return None
            
            user = review.user
            if user and review.amount:
                if user.hold_balance >= review.amount:
                    user.hold_balance -= review.amount
                else:
                    user.hold_balance = 0
            
            review.status = 'rejected'
            return review

async def admin_reject_final_confirmation(review_id: int) -> Optional[Review]:
    async with async_session() as session:
        async with session.begin():
            review = await session.get(Review, review_id)
            if not review or review.status != 'awaiting_confirmation':
                return None
            
            user = await session.get(User, review.user_id)
            if user and review.amount:
                if user.hold_balance >= review.amount:
                    user.hold_balance -= review.amount
                else:
                    user.hold_balance = 0

            review.status = 'rejected'
            return review

# --- Функции для системы бана и просроченных ссылок ---
async def db_find_and_expire_old_assigned_links(hours_threshold: int = 24) -> List[Link]:
    async with async_session() as session:
        async with session.begin():
            threshold_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_threshold)
            
            select_stmt = select(Link.id).where(
                Link.status == 'assigned',
                Link.assigned_at < threshold_time
            )
            result = await session.execute(select_stmt)
            link_ids_to_expire = result.scalars().all()

            if not link_ids_to_expire:
                return []
            
            select_objects_stmt = select(Link).where(Link.id.in_(link_ids_to_expire))
            result_objects = await session.execute(select_objects_stmt)
            expired_links = result_objects.scalars().all()

            update_stmt = update(Link).where(
                Link.id.in_(link_ids_to_expire)
            ).values(
                status='expired',
                assigned_to_user_id=None,
                assigned_at=None
            )
            await session.execute(update_stmt)
            
            return expired_links


async def reset_all_expired_links() -> int:
    async with async_session() as session:
        async with session.begin():
            stmt = update(Link).where(Link.status == 'expired').values(status='available')
            result = await session.execute(stmt)
            return result.rowcount

async def ban_user(user_id: int, reason: str) -> bool:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return False
            user.is_banned = True
            user.ban_reason = reason
            user.banned_at = datetime.datetime.utcnow()
            return True

async def unban_user(user_id: int, is_first_unban: bool = False) -> bool:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return False
            user.is_banned = False
            user.ban_reason = None
            user.banned_at = None
            if is_first_unban:
                user.unban_count += 1
            return True

async def update_last_unban_request_time(user_id: int):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if user:
                user.last_unban_request_at = datetime.datetime.utcnow()

# --- Функции для системы амнистии ---
async def create_unban_request(user_id: int, reason: str) -> Optional[UnbanRequest]:
    async with async_session() as session:
        async with session.begin():
            new_request = UnbanRequest(user_id=user_id, reason=reason, status='pending')
            session.add(new_request)
            await session.flush()
            await session.refresh(new_request)
            return new_request

async def get_pending_unban_requests(page: int = 1, limit: int = 5) -> List[UnbanRequest]:
    async with async_session() as session:
        query = (
            select(UnbanRequest)
            .where(UnbanRequest.status == 'pending')
            .options(selectinload(UnbanRequest.user))
            .order_by(UnbanRequest.created_at)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await session.execute(query)
        return result.scalars().all()

async def get_pending_unban_requests_count() -> int:
    async with async_session() as session:
        query = select(func.count(UnbanRequest.id)).where(UnbanRequest.status == 'pending')
        result = await session.execute(query)
        return result.scalar_one()

async def get_unban_request_by_id(request_id: int) -> Optional[UnbanRequest]:
    async with async_session() as session:
        return await session.get(UnbanRequest, request_id, options=[selectinload(UnbanRequest.user)])

async def update_unban_request_status(request_id: int, status: str, admin_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            request = await session.get(UnbanRequest, request_id)
            if not request:
                return False
            request.status = status
            request.reviewed_by_admin_id = admin_id
            return True
            
async def get_unban_request_by_status(user_id: int, status: str) -> Optional[UnbanRequest]:
    async with async_session() as session:
        query = select(UnbanRequest).where(
            UnbanRequest.user_id == user_id,
            UnbanRequest.status == status
        ).order_by(desc(UnbanRequest.created_at)).limit(1)
        result = await session.execute(query)
        return result.scalar_one_or_none()

# --- Функции для реферальной системы ---
async def set_user_referral_path(user_id: int, path: str, subpath: str = None) -> bool:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user or user.referral_path:
                return False
            user.referral_path = path
            user.referral_subpath = subpath
            return True
            
# --- Функции для управления наградами ---
async def get_reward_settings() -> List[RewardSetting]:
    async with async_session() as session:
        result = await session.execute(select(RewardSetting).order_by(RewardSetting.place))
        return result.scalars().all()

async def update_reward_settings(settings: List[Dict[str, Union[int, float]]]):
    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(RewardSetting))
            if settings:
                objects = [RewardSetting(**s) for s in settings]
                session.add_all(objects)

async def get_system_setting(key: str) -> Optional[str]:
    async with async_session() as session:
        setting = await session.get(SystemSetting, key)
        return setting.value if setting else None

async def set_system_setting(key: str, value: str):
    async with async_session() as session:
        async with session.begin():
            setting = await session.get(SystemSetting, key)
            if setting:
                setting.value = value
            else:
                new_setting = SystemSetting(key=key, value=value)
                session.add(new_setting)

# --- Функции для DND, списков банов и промо ---
async def toggle_dnd_status(admin_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            admin = await session.get(User, admin_id)
            if not admin:
                return False
            admin.dnd_enabled = not admin.dnd_enabled
            return admin.dnd_enabled

async def get_active_admins(admin_ids: List[int]) -> List[int]:
    async with async_session() as session:
        query = select(User.id).where(User.id.in_(admin_ids), User.dnd_enabled == False)
        result = await session.execute(query)
        return result.scalars().all()

async def get_pending_tasks_count() -> Dict[str, int]:
    async with async_session() as session:
        reviews_query = select(func.count(Review.id)).where(Review.status.in_(['pending', 'awaiting_confirmation']))
        tickets_query = select(func.count(SupportTicket.id)).where(SupportTicket.status == 'open')
        
        reviews_count = await session.execute(reviews_query)
        tickets_count = await session.execute(tickets_query)
        
        return {
            "reviews": reviews_count.scalar_one(),
            "tickets": tickets_count.scalar_one(),
        }

async def get_banned_users(page: int = 1, limit: int = 6) -> List[User]:
    async with async_session() as session:
        query = (
            select(User)
            .where(User.is_banned == True)
            .order_by(desc(User.banned_at))
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await session.execute(query)
        return result.scalars().all()

async def get_banned_users_count() -> int:
    async with async_session() as session:
        query = select(func.count(User.id)).where(User.is_banned == True)
        result = await session.execute(query)
        return result.scalar_one()

async def get_all_promo_codes(page: int = 1, limit: int = 6) -> List[PromoCode]:
    async with async_session() as session:
        query = (
            select(PromoCode)
            .where(PromoCode.current_uses < PromoCode.total_uses)
            .order_by(desc(PromoCode.created_at))
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await session.execute(query)
        return result.scalars().all()

async def get_promo_codes_count() -> int:
    async with async_session() as session:
        query = select(func.count(PromoCode.id)).where(PromoCode.current_uses < PromoCode.total_uses)
        result = await session.execute(query)
        return result.scalar_one()

async def delete_promo_code(promo_id: int) -> bool:
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                delete(PromoActivation).where(PromoActivation.promo_code_id == promo_id)
            )
            result = await session.execute(
                delete(PromoCode).where(PromoCode.id == promo_id)
            )
            return result.rowcount > 0

# --- Функции для системы стажировок ---

async def create_internship_application(user_id: int, username: str, age: str, hours: str, platforms: str) -> Optional[InternshipApplication]:
    async with async_session() as session:
        async with session.begin():
            new_app = InternshipApplication(
                user_id=user_id,
                username=username,
                age=age,
                hours_per_day=hours,
                platforms=platforms
            )
            session.add(new_app)
            await session.flush()
            await session.refresh(new_app)
            return new_app

async def get_internship_application(user_id: int) -> Optional[InternshipApplication]:
    async with async_session() as session:
        result = await session.execute(
            select(InternshipApplication).where(InternshipApplication.user_id == user_id)
        )
        return result.scalar_one_or_none()

async def get_internship_stats_counts() -> Dict[str, int]:
    async with async_session() as session:
        pending_apps_q = select(func.count(InternshipApplication.id)).where(InternshipApplication.status == 'pending')
        candidates_q = select(func.count(InternshipApplication.id)).where(InternshipApplication.status == 'approved')
        interns_q = select(func.count(User.id)).where(User.is_intern == True)
        
        pending_apps_res = await session.execute(pending_apps_q)
        candidates_res = await session.execute(candidates_q)
        interns_res = await session.execute(interns_q)
        
        return {
            "applications": pending_apps_res.scalar_one(),
            "candidates": candidates_res.scalar_one(),
            "interns": interns_res.scalar_one()
        }

async def get_paginated_applications(status: str, page: int = 1, limit: int = 5) -> Tuple[List[InternshipApplication], int]:
    async with async_session() as session:
        query = select(InternshipApplication).where(InternshipApplication.status == status).order_by(InternshipApplication.created_at)
        count_query = select(func.count(InternshipApplication.id)).where(InternshipApplication.status == status)
        
        total_count = await session.scalar(count_query)
        
        paginated_query = query.offset((page - 1) * limit).limit(limit)
        result = await session.execute(paginated_query)
        apps = result.scalars().all()
        
        return apps, total_count

async def get_paginated_interns(page: int = 1, limit: int = 5) -> Tuple[List[User], int]:
    async with async_session() as session:
        query = select(User).where(User.is_intern == True).options(selectinload(User.internship_tasks)).order_by(User.id)
        count_query = select(func.count(User.id)).where(User.is_intern == True)

        total_count = await session.scalar(count_query)

        paginated_query = query.offset((page - 1) * limit).limit(limit)
        result = await session.execute(paginated_query)
        interns = result.scalars().unique().all()
        
        return interns, total_count

async def get_application_by_id(app_id: int) -> Optional[InternshipApplication]:
    async with async_session() as session:
        return await session.get(InternshipApplication, app_id)

async def update_application_status(app_id: int, new_status: str) -> bool:
    async with async_session() as session:
        async with session.begin():
            app = await session.get(InternshipApplication, app_id)
            if not app:
                return False
            app.status = new_status
            return True

async def get_active_intern_task(intern_id: int) -> Optional[InternshipTask]:
    async with async_session() as session:
        result = await session.execute(
            select(InternshipTask).where(
                InternshipTask.intern_id == intern_id,
                InternshipTask.status == 'active'
            )
        )
        return result.scalar_one_or_none()

async def find_available_intern(platform_family: str) -> Optional[User]:
    async with async_session() as session:
        candidate_ids_query = select(InternshipApplication.user_id).where(
            InternshipApplication.platforms.like(f"%{platform_family}%")
        )
        candidate_ids_result = await session.execute(candidate_ids_query)
        candidate_ids = candidate_ids_result.scalars().all()

        if not candidate_ids:
            return None

        query = select(User).join(
            InternshipTask, User.id == InternshipTask.intern_id, isouter=True
        ).where(
            User.id.in_(candidate_ids),
            User.is_intern == True,
            User.is_busy_intern == False,
        ).order_by(
            InternshipTask.last_task_at.asc().nulls_first()
        ).limit(1)
        
        result = await session.execute(query)
        return result.scalar_one_or_none()

async def set_intern_busy_status(intern_id: int, is_busy: bool):
    async with async_session() as session:
        async with session.begin():
            user_stmt = update(User).where(User.id == intern_id).values(is_busy_intern=is_busy)
            await session.execute(user_stmt)

            if is_busy:
                task_stmt = update(InternshipTask).where(
                    InternshipTask.intern_id == intern_id,
                    InternshipTask.status == 'active'
                ).values(last_task_at=datetime.datetime.utcnow())
                await session.execute(task_stmt)

async def create_intern_task(intern_id: int, platform: str, task_type: str, goal_count: int, salary: float) -> Optional[InternshipTask]:
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, intern_id)
            if not user: return None

            user.is_intern = True
            
            new_task = InternshipTask(
                intern_id=intern_id,
                platform=platform,
                task_type=task_type,
                goal_count=goal_count,
                estimated_salary=salary
            )
            session.add(new_task)
            await session.flush()
            await session.refresh(new_task)
            return new_task

async def fire_intern(intern_id: int, reason: str):
    async with async_session() as session:
        async with session.begin():
            user = await session.get(User, intern_id, options=[selectinload(User.internship_tasks)])
            if not user or not user.is_intern:
                return

            user.is_intern = False
            user.is_busy_intern = False

            active_task = next((t for t in user.internship_tasks if t.status == 'active'), None)
            if active_task:
                active_task.status = 'fired'

async def get_intern_mistakes(intern_id: int, page: int = 1, limit: int = 5) -> Tuple[List[InternshipMistake], int]:
    async with async_session() as session:
        query = select(InternshipMistake).where(InternshipMistake.intern_id == intern_id).order_by(desc(InternshipMistake.created_at))
        count_query = select(func.count(InternshipMistake.id)).where(InternshipMistake.intern_id == intern_id)
        
        total_count = await session.scalar(count_query)
        
        paginated_query = query.offset((page - 1) * limit).limit(limit)
        result = await session.execute(paginated_query)
        mistakes = result.scalars().all()
        
        return mistakes, total_count

async def complete_internship(task: InternshipTask) -> float:
    async with async_session() as session:
        async with session.begin():
            intern = await session.get(User, task.intern_id, options=[selectinload(User.internship_application)])
            if not intern:
                return 0.0

            task_to_update = await session.get(InternshipTask, task.id)
            if not task_to_update:
                return 0.0

            task_to_update.status = 'completed'
            intern.is_intern = False
            intern.is_busy_intern = False
            if intern.internship_application:
                intern.internship_application.status = 'archived_success'
            
            penalty = task.error_count * (task.estimated_salary / task.goal_count) * 2
            final_salary = task.estimated_salary - penalty
            
            if final_salary > 0:
                intern.balance += final_salary
                await log_operation(session, intern.id, "TOP_REWARD", final_salary, "Зарплата за стажировку")
            
            return final_salary

async def process_intern_decision(review_id: int, is_approved: bool, reason: Optional[str] = None):
    async with async_session() as session:
        async with session.begin():
            # Находим, какой стажер работал над этим отзывом
            review = await session.get(Review, review_id, options=[selectinload(Review.user)])
            if not review or not review.user.is_busy_intern:
                return # Это не была задача стажера

            intern = review.user
            intern.is_busy_intern = False
            
            task = await get_active_intern_task(intern.id)
            if not task: return

            mentor_decision_is_correct = is_approved

            if mentor_decision_is_correct:
                task.current_progress += 1
            else:
                task.error_count += 1
                penalty_amount = (task.estimated_salary / task.goal_count) * 2
                new_mistake = InternshipMistake(
                    intern_task_id=task.id,
                    intern_id=intern.id,
                    review_id=review_id,
                    reason=reason or "Причина не указана",
                    penalty_amount=penalty_amount
                )
                session.add(new_mistake)

            if task.current_progress >= task.goal_count:
                await complete_internship(task)
# file: logic/deposit_logic.py

import logging
import datetime
from math import floor
from aiogram import Bot
from database import db_manager
from config import DEPOSIT_PLANS

logger = logging.getLogger(__name__)

async def process_deposits(bot: Bot):
    """
    Проверяет все активные депозиты, начисляет проценты и закрывает истекшие.
    Запускается по расписанию.
    """
    try:
        now = datetime.datetime.utcnow()
        active_deposits = await db_manager.get_all_active_deposits()
        
        for deposit in active_deposits:
            plan = DEPOSIT_PLANS.get(deposit.deposit_plan_id)
            if not plan:
                logger.error(f"Deposit {deposit.id} has an unknown plan_id '{deposit.deposit_plan_id}'. Skipping.")
                continue

            # --- 1. Начисление процентов ---
            time_since_last_accrual = now - deposit.last_accrual_at
            period_duration = datetime.timedelta(hours=plan['period_hours'])
            
            # Определяем, сколько полных периодов прошло
            intervals_passed = floor(time_since_last_accrual / period_duration)
            
            if intervals_passed > 0:
                new_balance = deposit.current_balance
                for _ in range(intervals_passed):
                    new_balance *= (1 + plan['rate_percent'] / 100.0)
                
                new_last_accrual_at = deposit.last_accrual_at + (intervals_passed * period_duration)
                
                await db_manager.update_deposit_balance(deposit.id, new_balance, new_last_accrual_at)
                logger.info(f"Accrued interest for deposit {deposit.id} ({intervals_passed} intervals). New balance: {new_balance:.2f}")

        # --- 2. Закрытие депозитов ---
        # Повторно запрашиваем депозиты, чтобы получить обновленные данные
        deposits_to_close = await db_manager.get_deposits_to_close()
        
        for deposit in deposits_to_close:
            plan = DEPOSIT_PLANS.get(deposit.deposit_plan_id)
            if not plan: continue

            # Финальное начисление, если необходимо
            remaining_time = deposit.closes_at - deposit.last_accrual_at
            period_duration = datetime.timedelta(hours=plan['period_hours'])
            remaining_intervals = floor(remaining_time / period_duration) if remaining_time.total_seconds() > 0 else 0

            final_balance = deposit.current_balance
            if remaining_intervals > 0:
                for _ in range(remaining_intervals):
                    final_balance *= (1 + plan['rate_percent'] / 100.0)

            # Закрываем депозит
            await db_manager.close_deposit(deposit.id, final_balance)
            
            try:
                await bot.send_message(
                    deposit.user_id,
                    f"✅ Ваш депозит '{plan['name']}' на итоговую сумму {final_balance:.2f} ⭐ успешно закрыт. Средства зачислены на основной баланс."
                )
                logger.info(f"Closed deposit {deposit.id} for user {deposit.user_id}. Final amount: {final_balance:.2f}")
            except Exception as e:
                logger.error(f"Failed to notify user {deposit.user_id} about closed deposit {deposit.id}: {e}")

    except Exception as e:
        logger.exception("An error occurred during the process_deposits job.")
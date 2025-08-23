# file: logic/promo_logic.py

from database import db_manager, models
import logging

logger = logging.getLogger(__name__)

async def activate_promo_code_logic(user_id: int, code: str) -> tuple[str, models.PromoCode | None]:
    """
    Основная логика активации промокода.
    Возвращает кортеж: (статус_сообщения, объект_промокода_или_None).
    """
    # 0. Проверить, нет ли у пользователя уже активного промокода с условием
    any_pending_activation = await db_manager.find_pending_promo_activation(user_id)
    if any_pending_activation:
        message = (
            "❌ У вас уже есть активный промокод, требующий выполнения задания. "
            "Вы не можете активировать новый, пока не выполните или не отмените текущее задание."
        )
        return message, None

    # 1. Найти промокод в базе с блокировкой строки для предотвращения гонки состояний
    promo = await db_manager.get_promo_by_code(code, for_update=True)
    if not promo:
        return "❌ Промокод не найден. Проверьте правильность ввода.", None

    # 2. Проверить, не закончились ли активации
    if promo.current_uses >= promo.total_uses:
        return "😔 К сожалению, лимит активаций для этого промокода исчерпан.", None

    # 3. Проверить, не активировал ли этот пользователь его ранее
    existing_activation = await db_manager.get_user_promo_activation(user_id, promo.id)
    if existing_activation:
        return "❗️ Вы уже активировали этот промокод.", None
        
    # 4. Обработка условий
    # Если условие не требуется
    if promo.condition == "no_condition":
        # Создаем активацию и обновляем баланс в одной транзакции
        await db_manager.create_promo_activation(user_id, promo, status='completed')
        await db_manager.update_balance(user_id, promo.reward)
        logger.info(f"User {user_id} activated promo '{promo.code}' with no condition. Rewarded {promo.reward} stars.")
        return f"✅ Промокод успешно активирован! Вам начислено {promo.reward} ⭐.", promo
    
    # Если условие требуется
    else:
        await db_manager.create_promo_activation(user_id, promo, status='pending_condition')
        logger.info(f"User {user_id} activated promo '{promo.code}'. Pending condition: {promo.condition}.")
        
        condition_map = {
            "google_review": "написать и получить одобрение на отзыв в Google Картах",
            "yandex_review": "написать и получить одобрение на отзыв в Yandex Картах",
            "gmail_account": "создать и получить одобрение на аккаунт Gmail"
        }
        condition_text = condition_map.get(promo.condition, "неизвестное условие")
        
        message = (
            f"✅ Промокод `{promo.code}` принят!\n\n"
            f"💰 Для получения **{promo.reward} ⭐** вам необходимо **{condition_text}**.\n\n"
            f"Вы готовы приступить к выполнению задания?"
        )
        return message, promo

async def check_and_apply_promo_reward(user_id: int, condition_completed: str, bot):
    """
    Проверяет, есть ли у пользователя ожидающий промокод с этим условием,
    и если есть, начисляет награду.
    """
    activation = await db_manager.find_pending_promo_activation(user_id, condition_completed)
    
    if activation:
        # Пытаемся завершить активацию. Эта функция вернет False, если лимит исчерпан.
        success = await db_manager.complete_promo_activation(activation.id)
        
        if success:
            promo = activation.promo_code
            await db_manager.update_balance(user_id, promo.reward)
            
            try:
                await bot.send_message(
                    user_id,
                    f"🎉 Вы выполнили условие промокода **'{promo.code}'**! "
                    f"Вам дополнительно начислено **{promo.reward} ⭐**."
                )
                logger.info(f"User {user_id} completed promo '{promo.code}' condition. Rewarded {promo.reward} stars.")
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} about completed promo: {e}")
        else:
             logger.warning(f"User {user_id} completed condition for promo '{activation.promo_code.code}', but it has no uses left.")
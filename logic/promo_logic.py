
# file: logic/promo_logic.py

from database import db_manager
import logging

logger = logging.getLogger(__name__)

async def activate_promo_code_logic(user_id: int, code: str) -> str:
    """
    Основная логика активации промокода. Проверяет все условия и возвращает
    сообщение для пользователя.
    """
    # 1. Найти промокод в базе
    promo = await db_manager.get_promo_by_code(code)
    if not promo:
        return "❌ Промокод не найден. Проверьте правильность ввода."

    # 2. Проверить, не закончились ли активации
    if promo.current_uses >= promo.total_uses:
        return "😔 К сожалению, лимит активаций для этого промокода исчерпан."

    # 3. Проверить, не активировал ли этот пользователь его ранее
    existing_activation = await db_manager.get_user_promo_activation(user_id, promo.id)
    if existing_activation:
        return "❗️ Вы уже активировали этот промокод."
        
    # 4. Обработка условий
    condition_map = {
        "no_condition": "Без условия",
        "google_review": "Написать и получить одобрение на отзыв в Google Картах",
        "yandex_review": "Написать и получить одобрение на отзыв в Yandex Картах",
        "gmail_account": "Создать и получить одобрение на аккаунт Gmail"
    }
    
    # Если условие не требуется
    if promo.condition == "no_condition":
        await db_manager.update_balance(user_id, promo.reward)
        await db_manager.create_promo_activation(user_id, promo, status='completed')
        logger.info(f"User {user_id} activated promo '{promo.code}' with no condition. Rewarded {promo.reward} stars.")
        return f"✅ Промокод успешно активирован! Вам начислено {promo.reward} ⭐."
    
    # Если условие требуется
    else:
        await db_manager.create_promo_activation(user_id, promo, status='pending_condition')
        condition_text = condition_map.get(promo.condition, "Неизвестное условие")
        logger.info(f"User {user_id} activated promo '{promo.code}'. Pending condition: {promo.condition}.")
        return (
            f"✅ Промокод принят!\n\n"
            f"💰 Вы получите: **{promo.reward} ⭐**\n"
            f"📝 После выполнения условия: **{condition_text}**.\n\n"
            f"Награда будет начислена автоматически, как только вы выполните это задание и оно будет одобрено."
        )

async def check_and_apply_promo_reward(user_id: int, condition_completed: str, bot):
    """
    Проверяет, есть ли у пользователя ожидающий промокод с этим условием,
    и если есть, начисляет награду.
    """
    activation = await db_manager.find_pending_promo_activation(user_id, condition_completed)
    
    if activation:
        promo = await db_manager.get_promo_by_code(activation.promo_code.code)
        if promo and promo.current_uses < promo.total_uses:
            await db_manager.update_balance(user_id, promo.reward)
            await db_manager.complete_promo_activation(activation.id)
            
            try:
                await bot.send_message(
                    user_id,
                    f"🎉 Вы выполнили условие промокода **'{promo.code}'**! "
                    f"Вам дополнительно начислено **{promo.reward} ⭐**."
                )
                logger.info(f"User {user_id} completed promo '{promo.code}' condition. Rewarded {promo.reward} stars.")
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} about completed promo: {e}")
        elif promo:
             logger.warning(f"User {user_id} completed condition for promo '{promo.code}', but it has no uses left.")
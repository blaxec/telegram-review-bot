# file: logic/reward_logic.py
import logging
import datetime
from aiogram import Bot
from database import db_manager

logger = logging.getLogger(__name__)

async def distribute_rewards(bot: Bot):
    """
    Проверяет, пришло ли время награждать топ, и выполняет награждение.
    Запускается по расписанию (например, каждый час).
    """
    try:
        timer_hours_str = await db_manager.get_system_setting("reward_timer_hours")
        next_reward_ts_str = await db_manager.get_system_setting("next_reward_timestamp")

        if not timer_hours_str:
            return # Награждение не настроено

        timer_hours = int(timer_hours_str)
        next_reward_ts = float(next_reward_ts_str) if next_reward_ts_str else 0
        
        current_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

        # Если время еще не пришло, выходим
        if current_ts < next_reward_ts:
            return

        logger.info("Reward distribution cycle started.")
        
        # Получаем настройки и топ пользователей
        reward_settings = await db_manager.get_reward_settings()
        rewards_map = {s.place: s.reward_amount for s in reward_settings if s.reward_amount > 0}
        top_users = await db_manager.get_top_10_users()

        if not rewards_map or not top_users:
            logger.info("No rewards configured or no users in top. Skipping distribution.")
        else:
            for i, (user_id, display_name, _, _) in enumerate(top_users):
                place = i + 1
                if place in rewards_map:
                    reward = rewards_map[place]
                    await db_manager.update_balance(user_id, reward)
                    try:
                        await bot.send_message(
                            user_id,
                            f"🎉 Поздравляем! Вы заняли **{place}-е место** в топе и получаете награду в **{reward} ⭐**!"
                        )
                        logger.info(f"Rewarded user {user_id} ({display_name}) with {reward} stars for place {place}.")
                    except Exception as e:
                        logger.error(f"Failed to notify user {user_id} about reward: {e}")
        
        # Устанавливаем время следующей выдачи
        new_next_reward_ts = current_ts + (timer_hours * 3600)
        await db_manager.set_system_setting("next_reward_timestamp", str(new_next_reward_ts))
        logger.info(f"Reward distribution cycle finished. Next cycle scheduled for {datetime.datetime.fromtimestamp(new_next_reward_ts, tz=datetime.timezone.utc)} UTC.")

    except Exception as e:
        logger.exception("An error occurred during the reward distribution cycle.")
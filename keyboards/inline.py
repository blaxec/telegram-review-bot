# file: keyboards/inline.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import Rewards, GOOGLE_API_KEYS
# НОВЫЕ ИМПОРТЫ
from aiogram import Bot
from logic import admin_roles

# --- /start и навигация ---

def get_agreement_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='✅ Я согласен и принимаю условия', callback_data='agree_agreement')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_action')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Раздел "Профиль" ---

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='🎁 Вывод звезд', callback_data='profile_withdraw')],
        [InlineKeyboardButton(text='💸 Передача звезд', callback_data='profile_transfer')],
        [InlineKeyboardButton(text='🔗 Реферальная система', callback_data='profile_referral')],
        [InlineKeyboardButton(text='⏳ Холд', callback_data='profile_hold')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Раздел "Статистика" ---

def get_stats_keyboard(is_anonymous: bool) -> InlineKeyboardMarkup:
    anonymity_text = "🙈 Стать анонимным" if not is_anonymous else "🐵 Показать в топе"
    buttons = [
        [InlineKeyboardButton(text=anonymity_text, callback_data='profile_toggle_anonymity')],
        [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Передача звезд ---
def get_transfer_amount_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='🔢 Ввести сумму', callback_data='transfer_amount_other')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_transfer_show_nick_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='👍 Да', callback_data='transfer_show_nick_yes')],
        [InlineKeyboardButton(text='🙈 Нет (Анонимно)', callback_data='transfer_show_nick_no')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_ask_comment_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='✍️ Да', callback_data=f'{prefix}_ask_comment_yes')],
        [InlineKeyboardButton(text='🙅‍♂️ Нет', callback_data=f'{prefix}_ask_comment_no')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Вывод звезд ---
def get_withdraw_amount_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text='15 ⭐', callback_data='withdraw_amount_15'),
            InlineKeyboardButton(text='25 ⭐', callback_data='withdraw_amount_25'),
        ],
        [
            InlineKeyboardButton(text='50 ⭐', callback_data='withdraw_amount_50'),
            InlineKeyboardButton(text='100 ⭐', callback_data='withdraw_amount_100'),
        ],
        [InlineKeyboardButton(text='🔢 Другая сумма', callback_data='withdraw_amount_other')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_withdraw_recipient_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='👤 Себе', callback_data='withdraw_recipient_self')],
        [InlineKeyboardButton(text='👥 Указать пользователя', callback_data='withdraw_recipient_other')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Реферальная система ---
def get_referral_info_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='👥 Мои рефералы', callback_data='profile_referrals_list')],
        [InlineKeyboardButton(text='💰 Забрать из копилки', callback_data='profile_claim_referral_stars')],
        [InlineKeyboardButton(text='⬅️ Назад в профиль', callback_data='go_profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='go_profile')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_referral_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='profile_referral')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_referral_path_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🌍 Google-Отзывы ({Rewards.REFERRAL_GOOGLE_REVIEW}⭐/отзыв)", callback_data="confirm_ref_path:google")
    builder.button(text=f"📧 Gmail-Аккаунты ({Rewards.REFERRAL_GMAIL_ACCOUNT}⭐/аккаунт)", callback_data="confirm_ref_path:gmail")
    builder.button(text="🗺️ Яндекс-Отзывы (выбрать)", callback_data="ref_path:yandex")
    builder.button(text="⬅️ Назад в профиль", callback_data="go_profile")
    builder.adjust(1)
    return builder.as_markup()

def get_yandex_subpath_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"С текстом ({Rewards.REFERRAL_YANDEX_WITH_TEXT}⭐/отзыв)", callback_data="confirm_ref_path:yandex:with_text")
    builder.button(text=f"Без текста ({Rewards.REFERRAL_YANDEX_WITHOUT_TEXT}⭐/отзыв)", callback_data="confirm_ref_path:yandex:without_text")
    builder.button(text="⬅️ Назад к выбору пути", callback_data="back_to_ref_path_selection")
    builder.adjust(2,1)
    return builder.as_markup()

# --- Раздел "Заработок" ---

def get_earning_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✍️ Написание отзыва', callback_data='earning_write_review')
    builder.button(text='📧 Сделать аккаунт Gmail', callback_data='earning_create_gmail')
    builder.button(text='⬅️ Назад', callback_data='go_main_menu')
    builder.adjust(1)
    return builder.as_markup()

def get_write_review_platform_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🌍 Google карты', callback_data='review_google_maps')
    builder.button(text='🗺️ Yandex карты', callback_data='review_yandex_maps')
    builder.button(text='🚀 Zoon', callback_data='review_zoon')
    builder.button(text='💼 Avito', callback_data='review_avito')
    builder.button(text='🛠️ Yandex услуги', callback_data='review_yandex_services')
    builder.button(text='⬅️ Назад', callback_data='earning_menu')
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


# --- Google Отзывы ---

def get_google_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='✅ Выполнено', callback_data='google_review_done')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_ask_profile_screenshot_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='❓ Где взять профиль?', callback_data='google_get_profile_screenshot')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_back_from_instructions_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='google_back_to_profile_screenshot')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_last_reviews_check_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='❓ Где найти последние отзывы', callback_data='google_last_reviews_where')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_back_from_last_reviews_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='google_back_to_last_reviews')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_continue_writing_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='➡️ Продолжить', callback_data='google_continue_writing_review')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_liking_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='👍 Выполнено', callback_data='google_confirm_liking_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_confirmation_keyboard(platform: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='👍 Выполнено', callback_data=f'{platform}_confirm_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Yandex Отзывы ---
def get_yandex_review_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='С текстом (50 ⭐)', callback_data='yandex_review_type:with_text')],
        [InlineKeyboardButton(text='Без текста (15 ⭐)', callback_data='yandex_review_type:without_text')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='earning_write_review')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_yandex_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='📸 Я готов(а) отправить скриншот', callback_data='yandex_ready_to_screenshot')],
        [InlineKeyboardButton(text='💡 Как повысить уровень знатока', callback_data='yandex_how_to_be_expert')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
    
def get_yandex_ask_profile_screenshot_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='❌ Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_yandex_continue_writing_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='➡️ Продолжить', callback_data='yandex_continue_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_yandex_liking_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='👍 Выполнено', callback_data='yandex_confirm_liking_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Gmail ---
def get_gmail_cooldown_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='📱 У меня есть другое устройство', callback_data='gmail_another_phone')],
        [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_gmail_verification_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='❓ Как создать аккаунт?', callback_data='gmail_how_to_create')],
        [InlineKeyboardButton(text='📤 Отправить на проверку', callback_data='gmail_send_for_verification')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_gmail_back_to_verification_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='⬅️ Назад к заданию', callback_data='gmail_back_to_verification')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
    
# --- Админские клавиатуры ---

def get_admin_verification_keyboard(user_id: int, context: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    ocr_contexts = ['yandex_profile_screenshot', 'google_last_reviews', 'google_profile']
    if context in ocr_contexts and GOOGLE_API_KEYS:
        builder.button(text="🤖 Проверить с ИИ", callback_data=f"admin_ocr:{context}:{user_id}")

    builder.button(text="✅ Подтвердить", callback_data=f"admin_verify:confirm:{context}:{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin_verify:reject:{context}:{user_id}")
    builder.button(text="⚠️ Выдать предупреждение", callback_data=f"admin_verify:warn:{context}:{user_id}")
    builder.adjust(1, 2, 1)
    return builder.as_markup()

def get_admin_provide_text_keyboard(platform: str, user_id: int, link_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✍️ Написать текст вручную', callback_data=f'admin_provide_text:{platform}:{user_id}:{link_id}')
    builder.button(text='🤖 Сгенерировать с ИИ', callback_data=f'admin_ai_generate_start:{platform}:{user_id}:{link_id}')
    builder.adjust(1)
    return builder.as_markup()

def get_ai_moderation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Отправить пользователю', callback_data='ai_moderation:send')
    builder.button(text='🔄 Сгенерировать заново', callback_data='ai_moderation:regenerate')
    builder.button(text='✍️ Написать вручную', callback_data='ai_moderation:manual')
    builder.button(text='❌ Отмена', callback_data='cancel_action')
    builder.adjust(1)
    return builder.as_markup()

def get_ai_error_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🔄 Сгенерировать заново', callback_data='ai_moderation:regenerate')
    builder.button(text='✍️ Написать вручную', callback_data='ai_moderation:manual')
    builder.adjust(1)
    return builder.as_markup()


def get_admin_refs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Google Карты", callback_data="admin_refs:select_platform:google_maps")
    builder.button(text="Яндекс (с текстом)", callback_data="admin_refs:select_platform:yandex_with_text")
    builder.button(text="Яндекс (без текста)", callback_data="admin_refs:select_platform:yandex_without_text")
    builder.button(text="🔄 Найти и пометить просроченные", callback_data="admin_refs:expire_manual")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_platform_refs_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=f"admin_refs:stats:{platform}")
    builder.button(text="📄 Показать список", callback_data=f"admin_refs:list:{platform}")
    builder.button(text="➕ Добавить ссылки", callback_data=f"admin_refs:add:{platform}")
    builder.button(text="⬅️ Назад к выбору платформ", callback_data="admin_refs:back_to_selection")
    builder.adjust(1)
    return builder.as_markup()

def get_back_to_platform_refs_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад', callback_data=f'admin_refs:select_platform:{platform}')
    return builder.as_markup()

def get_admin_refs_list_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🗑️ Удалить ссылку из базы', callback_data=f'admin_refs:delete_start:{platform}')
    builder.button(text='↪️ Вернуть ссылку в доступные', callback_data=f'admin_refs:return_start:{platform}')
    builder.button(text='⬅️ Назад к меню платформы', callback_data=f'admin_refs:select_platform:{platform}')
    builder.adjust(1)
    return builder.as_markup()

def get_admin_hold_review_keyboard(review_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text='✅ Одобрить', callback_data=f'admin_hold_approve:{review_id}'),
            InlineKeyboardButton(text='❌ Отклонить', callback_data=f'admin_hold_reject:{review_id}')
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_gmail_data_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Отправить данные', callback_data=f'admin_gmail_send_data:{user_id}')
    builder.button(text='❌ Отклонить', callback_data=f'admin_verify:reject:gmail_data_request:{user_id}')
    builder.button(text='⚠️ Выдать предупреждение', callback_data=f'admin_verify:warn:gmail_data_request:{user_id}')
    builder.adjust(2,1)
    return builder.as_markup()

def get_admin_gmail_final_check_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text='✅ Подтвердить', callback_data=f'admin_gmail_confirm_account:{user_id}'),
            InlineKeyboardButton(text='❌ Отклонить', callback_data=f'admin_gmail_reject_account:{user_id}')
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_final_verdict_keyboard(review_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text='✅ Одобрить (в холд)', callback_data=f'admin_final_approve:{review_id}'),
            InlineKeyboardButton(text='❌ Отклонить', callback_data=f'admin_final_reject:{review_id}')
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_final_verification_keyboard(review_id: int) -> InlineKeyboardMarkup:
    """Кнопки для финального подтверждения отзыва после холда."""
    buttons = [
        [
            InlineKeyboardButton(text='✅ Одобрить и выплатить', callback_data=f'final_verify_approve:{review_id}'),
            InlineKeyboardButton(text='❌ Отклонить', callback_data=f'final_verify_reject:{review_id}')
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_withdrawal_keyboard(request_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_withdraw_approve:{request_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_withdraw_reject:{request_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reward_settings_menu_keyboard(current_timer_hours: int) -> InlineKeyboardMarkup:
    """Меню управления настройками наград."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить кол-во призовых мест", callback_data="reward_setting:set_places")
    builder.button(text="💰 Изменить награды", callback_data="reward_setting:set_amounts")
    builder.button(text=f"⏰ Таймер выдачи (сейчас: {current_timer_hours} ч)", callback_data="reward_setting:set_timer")
    builder.button(text="⬅️ Назад", callback_data="cancel_action")
    builder.adjust(1)
    return builder.as_markup()

# --- Клавиатуры для поддержки ---
def get_support_admin_keyboard(ticket_id: int, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✍️ Ответить на вопрос', callback_data=f'support_answer:{ticket_id}')
    builder.button(text='⚠️ Выдать предупреждение', callback_data=f'support_warn:{ticket_id}:{user_id}')
    builder.adjust(1)
    return builder.as_markup()

def get_unban_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для админа с запросом на разбан."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"unban_reject:{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Клавиатуры для промокодов ---

def get_promo_condition_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Без условия", callback_data="promo_cond:no_condition")
    builder.button(text="🌍 Отзыв Google", callback_data="promo_cond:google_review")
    builder.button(text="🗺️ Отзыв Yandex", callback_data="promo_cond:yandex_review")
    builder.button(text="📧 Создание Gmail", callback_data="promo_cond:gmail_account")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup()

def get_promo_conditional_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с выбором: начать или отказаться от задания для промокода."""
    buttons = [
        [InlineKeyboardButton(text="✅ Начать задание", callback_data="promo_start_task")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data="promo_decline_task")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_to_earning_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_to_earning')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_support_photo_choice_keyboard() -> InlineKeyboardMarkup:
    """Предлагает пользователю прикрепить фото к тикету."""
    buttons = [
        [InlineKeyboardButton(text="🖼️ Да, прикрепить фото", callback_data="support_add_photo:yes")],
        [InlineKeyboardButton(text="✉️ Нет, отправить как есть", callback_data="support_add_photo:no")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- НОВЫЙ РАЗДЕЛ: Клавиатуры для управления ролями ---

async def get_roles_main_menu() -> InlineKeyboardMarkup:
    """Главное меню управления ролями."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📍 Яндекс.Карты", callback_data="roles_cat:yandex")
    builder.button(text="🌍 Google Maps", callback_data="roles_cat:google")
    builder.button(text="📧 Gmail", callback_data="roles_cat:gmail")
    builder.button(text="📦 Другие задачи", callback_data="roles_cat:other")
    builder.button(text="⚙ Текущие настройки", callback_data="roles_show_current")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

async def get_roles_yandex_menu() -> InlineKeyboardMarkup:
    """Меню выбора типа задач для Яндекс."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 С текстом", callback_data="roles_subcat:yandex_text")
    builder.button(text="🚫 Без текста", callback_data="roles_subcat:yandex_no_text")
    builder.button(text="◀ Назад", callback_data="roles_back:main")
    builder.adjust(2, 1)
    return builder.as_markup()

async def get_task_switching_keyboard(bot: Bot, category: str, subcategory: str = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками для переключения задач в категории."""
    builder = InlineKeyboardBuilder()
    
    tasks_to_show = []
    if category == "yandex" and subcategory == "text":
        tasks_to_show = [
            (admin_roles.YANDEX_TEXT_PROFILE_CHECK_ADMIN, await admin_roles.get_yandex_text_profile_admin()),
            (admin_roles.YANDEX_TEXT_ISSUE_TEXT_ADMIN, await admin_roles.get_yandex_text_issue_admin()),
            (admin_roles.YANDEX_TEXT_FINAL_CHECK_ADMIN, await admin_roles.get_yandex_text_final_admin()),
        ]
    elif category == "yandex" and subcategory == "no_text":
        tasks_to_show = [
            (admin_roles.YANDEX_NO_TEXT_PROFILE_CHECK_ADMIN, await admin_roles.get_yandex_no_text_profile_admin()),
            (admin_roles.YANDEX_NO_TEXT_FINAL_CHECK_ADMIN, await admin_roles.get_yandex_no_text_final_admin()),
        ]
    elif category == "google":
         tasks_to_show = [
            (admin_roles.GOOGLE_PROFILE_CHECK_ADMIN, await admin_roles.get_google_profile_admin()),
            (admin_roles.GOOGLE_LAST_REVIEWS_CHECK_ADMIN, await admin_roles.get_google_reviews_admin()),
            (admin_roles.GOOGLE_ISSUE_TEXT_ADMIN, await admin_roles.get_google_issue_admin()),
            (admin_roles.GOOGLE_FINAL_CHECK_ADMIN, await admin_roles.get_google_final_admin()),
        ]
    elif category == "gmail":
        tasks_to_show = [
            (admin_roles.GMAIL_DEVICE_MODEL_CHECK_ADMIN, await admin_roles.get_gmail_device_admin()),
            (admin_roles.GMAIL_ISSUE_DATA_ADMIN, await admin_roles.get_gmail_data_admin()),
            (admin_roles.GMAIL_FINAL_CHECK_ADMIN, await admin_roles.get_gmail_final_admin()),
        ]
    elif category == "other":
        tasks_to_show = [
            (admin_roles.OTHER_HOLD_REVIEW_ADMIN, await admin_roles.get_other_hold_admin())
        ]
    
    for key, admin_id in tasks_to_show:
        description = admin_roles.ROLE_DESCRIPTIONS.get(key, "Неизвестная задача")
        admin_name = await admin_roles.get_admin_username(bot, admin_id)
        builder.button(text=f"{description}: {admin_name}", callback_data=f"roles_switch:{key}")
    
    back_target = "yandex" if category == "yandex" and subcategory else "main"
    if category == "yandex" and not subcategory:
        back_target = "main"
    elif category == "yandex" and subcategory:
        back_target = "yandex"
        
    builder.button(text="◀ Назад", callback_data=f"roles_back:{back_target}")
    builder.adjust(1)
    return builder.as_markup()

def get_current_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура под сообщением с текущими настройками."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить сообщение", callback_data="roles_delete_msg")
    return builder.as_markup()
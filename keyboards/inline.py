# file: keyboards/inline.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- /start и навигация ---

def get_agreement_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Согласен с прочитанным', callback_data='agree_agreement')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Раздел "Профиль" ---

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Вывод звезд', callback_data='profile_withdraw')],
        [InlineKeyboardButton(text='Передача звезд', callback_data='profile_transfer')],
        [InlineKeyboardButton(text='Реферальная ссылка', callback_data='profile_referral')],
        [InlineKeyboardButton(text='Холд', callback_data='profile_hold')],
        [InlineKeyboardButton(text='Назад', callback_data='go_main_menu')]
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
        [InlineKeyboardButton(text='Ввести сумму', callback_data='transfer_amount_other')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_transfer_show_nick_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Да', callback_data='transfer_show_nick_yes')],
        [InlineKeyboardButton(text='Нет (Анонимно)', callback_data='transfer_show_nick_no')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_ask_comment_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Да', callback_data=f'{prefix}_ask_comment_yes')],
        [InlineKeyboardButton(text='Нет', callback_data=f'{prefix}_ask_comment_no')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Вывод звезд ---
def get_withdraw_amount_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text='15', callback_data='withdraw_amount_15'),
            InlineKeyboardButton(text='25', callback_data='withdraw_amount_25'),
        ],
        [
            InlineKeyboardButton(text='50', callback_data='withdraw_amount_50'),
            InlineKeyboardButton(text='100', callback_data='withdraw_amount_100'),
        ],
        [InlineKeyboardButton(text='Другая сумма', callback_data='withdraw_amount_other')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_withdraw_recipient_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Себе', callback_data='withdraw_recipient_self')],
        [InlineKeyboardButton(text='Указать пользователя', callback_data='withdraw_recipient_other')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Реферальная система ---
def get_referral_info_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Мои рефералы', callback_data='profile_referrals_list')],
        [InlineKeyboardButton(text='Забрать звезды', callback_data='profile_claim_referral_stars')],
        [InlineKeyboardButton(text='Назад', callback_data='go_profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Назад', callback_data='go_profile')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Раздел "Заработок" ---

def get_earning_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Написание отзыва', callback_data='earning_write_review')
    builder.button(text='Сделать аккаунт Gmail', callback_data='earning_create_gmail')
    builder.button(text='Назад', callback_data='go_main_menu')
    builder.adjust(1)
    return builder.as_markup()

def get_write_review_platform_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Google карты', callback_data='review_google_maps')
    builder.button(text='Yandex карты', callback_data='review_yandex_maps')
    builder.button(text='Zoon', callback_data='review_zoon')
    builder.button(text='Avito', callback_data='review_avito')
    builder.button(text='Назад', callback_data='earning_menu')
    builder.adjust(2)
    return builder.as_markup()


# --- Google Отзывы ---

def get_google_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Выполнено', callback_data='google_review_done')],
        [InlineKeyboardButton(text='Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_ask_profile_screenshot_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Где взять профиль?', callback_data='google_get_profile_screenshot')],
        [InlineKeyboardButton(text='Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
    
def get_invalid_input_keyboard(platform: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Повторить', callback_data=f'{platform}_repeat_photo')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_photo_upload')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_last_reviews_check_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Где найти последние отзывы', callback_data='google_last_reviews_where')],
        [InlineKeyboardButton(text='Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_continue_writing_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Продолжить', callback_data='google_continue_writing_review')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_liking_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Выполнено', callback_data='google_confirm_liking_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_confirmation_keyboard(platform: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Выполнено', callback_data=f'{platform}_confirm_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Yandex Отзывы ---
def get_yandex_review_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='С текстом (50 ⭐)', callback_data='yandex_review_type:with_text')],
        [InlineKeyboardButton(text='Без текста (15 ⭐)', callback_data='yandex_review_type:without_text')],
        [InlineKeyboardButton(text='Назад', callback_data='earning_write_review')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_yandex_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Я готов(а) отправить скриншот', callback_data='yandex_ready_to_screenshot')],
        [InlineKeyboardButton(text='Как повысить уровень знатока', callback_data='yandex_how_to_be_expert')],
        [InlineKeyboardButton(text='Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
    
def get_yandex_ask_profile_screenshot_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Отмена', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_yandex_continue_writing_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Продолжить', callback_data='yandex_continue_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_yandex_liking_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Выполнено', callback_data='yandex_confirm_liking_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Gmail ---
def get_gmail_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Создать аккаунт', callback_data='gmail_request_data')],
        [InlineKeyboardButton(text='Как создать аккаунт?', callback_data='gmail_how_to_create')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
    
def get_gmail_cooldown_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='У меня есть другой телефон', callback_data='gmail_another_phone')],
        [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_gmail_verification_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Как создать аккаунт?', callback_data='gmail_how_to_create')],
        [InlineKeyboardButton(text='Отправить на проверку', callback_data='gmail_send_for_verification')]
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
    builder.button(text="✅ Подтвердить", callback_data=f"admin_verify:confirm:{context}:{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin_verify:reject:{context}:{user_id}")
    builder.button(text="⚠️ Выдать предупреждение", callback_data=f"admin_verify:warn:{context}:{user_id}")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_admin_provide_text_keyboard(platform: str, user_id: int, link_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='✍️ Написать текст отзыва', callback_data=f'admin_provide_text:{platform}:{user_id}:{link_id}')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_refs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Google
    builder.button(text="📊 Google Статистика", callback_data="admin_refs:stats:google_maps")
    builder.button(text="📄 Google Список", callback_data="admin_refs:list:google_maps")
    builder.button(text="➕ Google Добавить", callback_data="admin_refs:add:google_maps")
    # Yandex With Text
    builder.button(text="📊 Янд. (с текстом) Стат.", callback_data="admin_refs:stats:yandex_with_text")
    builder.button(text="📄 Янд. (с текстом) Список", callback_data="admin_refs:list:yandex_with_text")
    builder.button(text="➕ Янд. (с текстом) Добавить", callback_data="admin_refs:add:yandex_with_text")
    # Yandex Without Text
    builder.button(text="📊 Янд. (без текста) Стат.", callback_data="admin_refs:stats:yandex_without_text")
    builder.button(text="📄 Янд. (без текста) Список", callback_data="admin_refs:list:yandex_without_text")
    builder.button(text="➕ Янд. (без текста) Добавить", callback_data="admin_refs:add:yandex_without_text")
    # Exit
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(2, 1, 2, 1, 2, 1, 1)
    return builder.as_markup()


def get_back_to_admin_refs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад', callback_data='back_to_refs_menu')
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

def get_delete_ref_keyboard(link_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='🗑️ Удалить эту ссылку', callback_data=f'admin_refs:delete:{link_id}')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_withdrawal_keyboard(request_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_withdraw_approve:{request_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_withdraw_reject:{request_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Клавиатуры для поддержки ---
def get_support_admin_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(text='✍️ Ответить на вопрос', callback_data=f'support_answer:{ticket_id}')
    ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Клавиатуры для промокодов ---

def get_promo_condition_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Без условия", callback_data="promo_cond:no_condition")
    builder.button(text="Отзыв Google", callback_data="promo_cond:google_review")
    builder.button(text="Отзыв Yandex", callback_data="promo_cond:yandex_review")
    builder.button(text="Создание Gmail", callback_data="promo_cond:gmail_account")
    builder.button(text="Отмена", callback_data="cancel_action")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_promo_conditional_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с выбором: начать или отказаться от задания для промокода."""
    buttons = [
        [InlineKeyboardButton(text="✅ Начать задание", callback_data="promo_start_task")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data="promo_decline_task")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- НОВАЯ ФУНКЦИЯ ДЛЯ КНОПКИ ОТМЕНЫ В GMAIL ---
def get_cancel_to_earning_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Отмена', callback_data='cancel_to_earning')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
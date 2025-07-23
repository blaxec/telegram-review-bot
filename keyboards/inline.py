from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- /start и навигация ---

def get_agreement_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Согласен с прочитанным', callback_data='agree_agreement')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Назад', callback_data='go_main_menu')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Раздел "Профиль" ---

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Вывод звезд', callback_data='profile_withdraw')],
        [InlineKeyboardButton(text='Передача звезд', callback_data='profile_transfer')],
        [InlineKeyboardButton(text='Реф. ссылка', callback_data='profile_referral')],
        [InlineKeyboardButton(text='Холд', callback_data='profile_hold')],
        [InlineKeyboardButton(text='Назад', callback_data='go_main_menu')]
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
        [InlineKeyboardButton(text='Указать юзера', callback_data='withdraw_recipient_other')],
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
    buttons = [
        [InlineKeyboardButton(text='Написание отзыва', callback_data='earning_write_review')],
        [InlineKeyboardButton(text='Сделать аккаунт Gmail', callback_data='earning_create_gmail')],
        [InlineKeyboardButton(text='Назад', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_write_review_platform_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Google карты', callback_data='review_google_maps')
    builder.button(text='Yandex карты', callback_data='review_yandex_maps')
    builder.button(text='Yandex услуги', callback_data='review_yandex_services')
    builder.button(text='Назад', callback_data='earning_menu_back')
    builder.adjust(2, 1, 1)
    return builder.as_markup()

# --- Google Отзывы ---

def get_google_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Выполнено', callback_data='google_review_done')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_google_ask_profile_screenshot_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Где взять профиль?', callback_data='google_get_profile_screenshot')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
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
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
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
def get_yandex_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Где найти ссылку?', callback_data='yandex_get_profile_link')],
        [InlineKeyboardButton(text='Как повысить уровень знатока', callback_data='yandex_how_to_be_expert')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_yandex_continue_writing_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='Продолжить', callback_data='yandex_continue_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Gmail ---
def get_gmail_init_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Создать аккаунт', callback_data='gmail_request_data')],
        [InlineKeyboardButton(text='Как создать аккаунт?', callback_data='gmail_how_to_create')],
        [InlineKeyboardButton(text='Отмена', callback_data='cancel_action')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_gmail_verification_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='Как создать аккаунт?', callback_data='gmail_how_to_create')],
        [InlineKeyboardButton(text='Отправить на проверку', callback_data='gmail_send_for_verification')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
    
# --- Админские клавиатуры ---

def get_admin_verification_keyboard(user_id: int, context: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"admin_verify:confirm:{context}:{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin_verify:reject:{context}:{user_id}")
    builder.button(text="⚠️ Дать пред.", callback_data=f"admin_verify:warn:{context}:{user_id}")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_admin_provide_text_keyboard(user_id: int, link_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='✍️ Написать текст отзыва', callback_data=f'admin_provide_text:{user_id}:{link_id}')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_refs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика Google", callback_data="admin_refs:stats:google_maps")
    builder.button(text="📊 Статистика Yandex", callback_data="admin_refs:stats:yandex_maps")
    builder.button(text="➕ Добавить Google", callback_data="admin_refs:add:google_maps")
    builder.button(text="➕ Добавить Yandex", callback_data="admin_refs:add:yandex_maps")
    builder.button(text="📄 Показать Google", callback_data="admin_refs:list:google_maps")
    builder.button(text="📄 Показать Yandex", callback_data="admin_refs:list:yandex_maps")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(2)
    return builder.as_markup()

def get_back_to_admin_refs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад', callback_data='back_to_refs_menu')
    builder.button(text='❌ Закрыть', callback_data='cancel_action')
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
    buttons = [
        [
            InlineKeyboardButton(text='✅ Отправить данные', callback_data=f'admin_gmail_send_data:{user_id}'),
            InlineKeyboardButton(text='❌ Отклонить', callback_data=f'admin_gmail_reject_request:{user_id}')
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
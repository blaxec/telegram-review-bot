# file: keyboards/inline.py

import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import Rewards, GOOGLE_API_KEYS
from aiogram import Bot
from logic import admin_roles
from database.models import UnbanRequest, InternshipApplication, User, PostTemplate, Administrator
from typing import Set, List, Optional

# --- /start и навигация ---

def get_agreement_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='✅ Я согласен и принимаю условия', callback_data='agree_agreement')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_inline_keyboard(callback_data: str = 'cancel_action') -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='❌ Отмена', callback_data=callback_data)]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Раздел "Профиль" ---

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='🎁 Вывод звезд', callback_data='profile_withdraw')],
        [InlineKeyboardButton(text='💸 Передача звезд', callback_data='profile_transfer')],
        [InlineKeyboardButton(text='📜 История операций', callback_data='profile_history')],
        [InlineKeyboardButton(text='🔗 Реферальная система', callback_data='profile_referral')],
        [InlineKeyboardButton(text='⏳ Холд', callback_data='profile_hold')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_operation_history_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для возврата из истории операций в профиль."""
    buttons = [[InlineKeyboardButton(text='⬅️ Назад в профиль', callback_data='go_profile')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_to_profile_keyboard() -> InlineKeyboardMarkup:
    """Создает кнопку "Отмена", возвращающую в профиль."""
    buttons = [[InlineKeyboardButton(text='❌ Отмена', callback_data='go_profile')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_transfer_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения перевода звезд."""
    buttons = [
        [InlineKeyboardButton(text='✅ Подтвердить', callback_data='transfer_confirm')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_to_profile')]
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

# --- Передача и вывод звезд ---
def get_skip_comment_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⏩ Пропустить', callback_data=f'{prefix}_skip_comment')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_attach_media_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='🖼️ Да, прикрепить', callback_data=f'{prefix}_attach_media_yes')],
        [InlineKeyboardButton(text='🙅‍♂️ Нет, пропустить', callback_data=f'{prefix}_attach_media_no')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_to_profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_withdraw_recipient_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='👤 Себе', callback_data='withdraw_recipient_self')],
        [InlineKeyboardButton(text='👥 Указать пользователя', callback_data='withdraw_recipient_other')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_to_profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_ask_comment_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='✍️ Да', callback_data=f'{prefix}_ask_comment_yes')],
        [InlineKeyboardButton(text='🙅‍♂️ Нет', callback_data=f'{prefix}_ask_comment_no')]
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


# --- Google и Yandex Отзывы ---

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

def get_intern_verification_keyboard(user_id: int, context: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру верификации для стажера (без кнопок ИИ)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"intern_verify:confirm:{context}:{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"intern_verify:reject:{context}:{user_id}")
    builder.button(text="⚠️ Выдать предупреждение", callback_data=f"intern_verify:warn:{context}:{user_id}")
    builder.adjust(2, 1)
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
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_platform_refs_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=f"admin_refs:stats:{platform}")
    builder.button(text="📄 Показать список", callback_data=f"admin_refs:list:{platform}")
    builder.button(text="➕ Добавить обычные", callback_data=f"admin_refs:add:regular:no_photo:{platform}")
    builder.button(text="➕ Добавить с фото 📸", callback_data=f"admin_refs:add:regular:photo:{platform}")
    builder.button(text="➕ Добавить быстрые 🚀", callback_data=f"admin_refs:add:fast:no_photo:{platform}")
    builder.button(text="➕ Добавить быстрые с фото 🚀📸", callback_data=f"admin_refs:add:fast:photo:{platform}")
    builder.button(text="⬅️ Назад к выбору платформ", callback_data="admin_refs:back_to_selection")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_back_to_platform_refs_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад', callback_data=f'admin_refs:select_platform:{platform}')
    return builder.as_markup()

def get_link_list_control_keyboard(platform: str, current_page: int, total_pages: int, filter_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    filters = [
        ("Все", "all"), ("🚀", "fast"), 
        ("📸", "photo"), ("📄", "regular")
    ]
    filter_buttons = []
    for text, f_type in filters:
        btn_text = f"✅ {text}" if filter_type == f_type else text
        filter_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=f"admin_refs:list:{platform}:{f_type}"))
    builder.row(*filter_buttons)
    
    pagination_buttons = []
    if current_page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"links_page:{platform}:{current_page-1}"))
    if total_pages > 1:
        pagination_buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"links_page:{platform}:{current_page+1}"))
    if pagination_buttons:
        builder.row(*pagination_buttons)
        
    builder.row(
        InlineKeyboardButton(text='🗑️ Удалить', callback_data=f'admin_refs:delete_start:{platform}'),
        InlineKeyboardButton(text='↪️ Вернуть', callback_data=f'admin_refs:return_start:{platform}')
    )
    builder.row(InlineKeyboardButton(text='⬅️ Назад к меню платформы', callback_data=f'admin_refs:select_platform:{platform}'))
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
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_pagination_keyboard(
    prefix: str,
    current_page: int,
    total_pages: int,
    show_close: bool = True,
    back_callback: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Создает клавиатуру для пагинации списков с опциональной кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    
    pagination_row = []
    if current_page > 1:
        pagination_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{current_page-1}"))
    if total_pages > 1:
        pagination_row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        pagination_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{current_page+1}"))
    
    if pagination_row:
        builder.row(*pagination_row)
    
    if back_callback:
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback))
    elif show_close:
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="go_main_menu"))
        
    return builder.as_markup()


def get_promo_list_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для списка промокодов с пагинацией и кнопкой удаления."""
    builder = InlineKeyboardBuilder()
    
    pagination_markup = get_pagination_keyboard("promolist:page", current_page, total_pages, show_close=False)
    for row in pagination_markup.inline_keyboard:
        builder.row(*row)

    builder.row(InlineKeyboardButton(text="🗑️ Удалить промокод", callback_data="promolist:delete_start"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="go_main_menu"))
    return builder.as_markup()

# --- Клавиатуры для поддержки и амнистии ---
def get_support_admin_keyboard(ticket_id: int, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✍️ Ответить на вопрос', callback_data=f'support_answer:{ticket_id}')
    builder.button(text='⚠️ Выдать предупреждение', callback_data=f'support_warn:{ticket_id}:{user_id}')
    builder.adjust(1)
    return builder.as_markup()

def get_amnesty_keyboard(requests: list[UnbanRequest], current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for req in requests:
        user = req.user
        username = f"@{user.username}" if user.username else f"ID {user.id}"
        ban_count_text = f"({user.unban_count + 1}-й раз)" if user.unban_count > 0 else "(1-й раз)"
        builder.row(
            InlineKeyboardButton(text=f"✅ Одобрить для {username} {ban_count_text}", callback_data=f"amnesty:action:approve:{req.id}"),
            InlineKeyboardButton(text=f"❌ Отклонить", callback_data=f"amnesty:action:reject:{req.id}")
        )
    
    pagination_markup = get_pagination_keyboard("amnesty:page", current_page, total_pages, show_close=True)
    for row in pagination_markup.inline_keyboard:
        builder.row(*row)
        
    return builder.as_markup()


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
    
    back_target = "main"
    if category == "yandex":
        back_target = "yandex" if subcategory else "main"

    builder.button(text="◀ Назад", callback_data=f"roles_back:{back_target}")
    builder.adjust(1)
    return builder.as_markup()

def get_current_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура под сообщением с текущими настройками."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить сообщение", callback_data="roles_delete_msg")
    return builder.as_markup()

# --- НОВЫЙ РАЗДЕЛ: Клавиатуры для системы стажировок ---

def get_internship_application_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для начала подачи анкеты."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Заполнить анкету", callback_data="internship_app:start")
    builder.button(text="⬅️ Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_internship_platform_selection_keyboard(selected: set = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора платформ в анкете."""
    if selected is None:
        selected = set()
        
    builder = InlineKeyboardBuilder()
    
    platforms = {
        "google": "Google Карты",
        "yandex_text": "Яндекс (с текстом)",
        "yandex_no_text": "Яндекс (без текста)",
    }
    
    for key, name in platforms.items():
        prefix = "✅ " if name in selected else ""
        builder.button(text=f"{prefix}{name}", callback_data=f"internship_toggle:{key}:{name}")
        
    builder.button(text="✅ Далее", callback_data="internship_app:platforms_done")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1)
    return builder.as_markup()

def get_internship_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Все верно, отправить", callback_data="internship_app:confirm")
    builder.button(text="Возраст", callback_data="internship_app:start:age")
    builder.button(text="Часы", callback_data="internship_app:start:hours")
    builder.button(text="Скорость ответа", callback_data="internship_app:start:response_time")
    builder.button(text="Платформы", callback_data="internship_app:start:platforms")
    builder.button(text="❌ Начать заново", callback_data="go_main_menu")
    builder.adjust(1, 4, 1)
    return builder.as_markup()

def get_intern_cabinet_keyboard(is_busy: bool) -> InlineKeyboardMarkup:
    """Клавиатура рабочего кабинета стажера."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 История ошибок", callback_data="intern_cabinet:mistakes")
    if not is_busy:
        builder.button(text="❌ Уволиться", callback_data="intern_cabinet:resign")
    builder.button(text="⬅️ Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_intern_resign_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения увольнения."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, я уверен", callback_data="intern_cabinet:resign_confirm")
    builder.button(text="⬅️ Нет, вернуться", callback_data="internship_main")
    builder.adjust(1)
    return builder.as_markup()

async def get_admin_internships_main_menu(stats: dict) -> InlineKeyboardMarkup:
    """Главное меню управления стажировками для админа."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📝 Анкеты ({stats.get('applications', 0)})", callback_data="admin_internships:view:applications:1")
    builder.button(text=f"🧑‍🎓 Кандидаты ({stats.get('candidates', 0)})", callback_data="admin_internships:view:candidates:1")
    builder.button(text=f"👨‍💻 Стажёры ({stats.get('interns', 0)})", callback_data="admin_internships:view:interns:1")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_application_review_keyboard(app: InternshipApplication) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра и решения по анкете."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"admin_internships:action:approve:{app.id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin_internships:action:reject:{app.id}")
    builder.button(text="⬅️ Назад к списку", callback_data="admin_internships:view:applications:1")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_admin_intern_view_keyboard(intern: User) -> InlineKeyboardMarkup:
    """Клавиатура для управления активным стажером."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Уволить", callback_data=f"admin_internships:fire_start:{intern.id}")
    builder.button(text="📜 История ошибок", callback_data=f"admin_internships:view_mistakes:{intern.id}:1")
    builder.button(text="⬅️ Назад к списку", callback_data="admin_internships:view:interns:1")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_admin_intern_task_setup_keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа задачи для кандидата."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Проверка профилей (Google/Yandex)", callback_data=f"admin_internships:set_task:{candidate_id}:profile_check")
    builder.button(text="⬅️ Назад к кандидатам", callback_data="admin_internships:view:candidates:1")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_intern_task_confirm_keyboard(candidate_id: int, platform: str, task_type: str, goal: int, salary: float) -> InlineKeyboardMarkup:
    """Клавиатура для финального подтверждения назначения задачи."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Назначить задачу", callback_data=f"admin_internships:confirm_task:{candidate_id}:{platform}:{task_type}:{goal}:{salary}")
    builder.button(text="❌ Отмена", callback_data=f"admin_internships:view:candidates:1")
    builder.adjust(1)
    return builder.as_markup()

# --- НОВЫЙ РАЗДЕЛ: Клавиатуры для /panel ---

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для панели управления SuperAdmin."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Забанить пользователя", callback_data="panel:ban_user")
    builder.button(text="✅ Разбанить пользователя", callback_data="panel:unban_user")
    builder.button(text="💸 Выписать штраф", callback_data="panel:issue_fine")
    builder.button(text="❄️ Сбросить кулдауны", callback_data="panel:reset_cooldown")
    builder.button(text="⏳ Просмотр холда", callback_data="panel:view_hold")
    builder.button(text="✨ Создать промокод", callback_data="panel:create_promo")
    builder.button(text="⬅️ Главное меню", callback_data="go_main_menu")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()
    
# --- НОВЫЙ РАЗДЕЛ: Клавиатуры для /roles_manage ---

def get_roles_manage_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить администратора", callback_data="roles_manage:add")
    builder.button(text="📋 Список администраторов", callback_data="roles_manage:list:1")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

async def get_roles_list_keyboard(admins: list[Administrator], page: int, total_pages: int, bot: Bot) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for admin in admins:
        role_icon = "👑" if admin.role == 'super_admin' else '🛡️'
        tester_icon = "🧪" if admin.is_tester else ''
        try:
            chat = await bot.get_chat(admin.user_id)
            username = f"@{chat.username}" if chat.username else f"ID {admin.user_id}"
        except Exception:
            username = f"ID {admin.user_id}"
        
        builder.button(text=f"{role_icon}{tester_icon} {username}", callback_data=f"roles_manage:view:{admin.user_id}")
    builder.adjust(1)

    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"roles_manage:list:{page-1}"))
    if total_pages > 1:
        pagination_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(text="➡️", callback_data=f"roles_manage:list:{page+1}"))
    if pagination_row:
        builder.row(*pagination_row)
        
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="roles_manage:back_to_menu"))
    return builder.as_markup()

def get_single_admin_manage_keyboard(admin: Administrator) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    tester_text = "✅ Убрать из тестеров" if admin.is_tester else "🔄 Сделать тестером"
    builder.button(text=tester_text, callback_data=f"roles_manage:toggle_tester:{admin.user_id}")
    if admin.is_removable:
        builder.button(text="🗑️ Удалить", callback_data=f"roles_manage:delete_confirm:{admin.user_id}")
    builder.button(text="⬅️ К списку", callback_data="roles_manage:list:1")
    builder.adjust(1)
    return builder.as_markup()

def get_role_selection_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛡️ Обычный админ", callback_data="roles_manage:set_role:admin")
    builder.button(text="👑 Главный админ", callback_data="roles_manage:set_role:super_admin")
    builder.button(text="❌ Отмена", callback_data="roles_manage:back_to_menu")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_delete_admin_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"roles_manage:delete_execute:{user_id}")
    builder.button(text="⬅️ Нет, назад", callback_data=f"roles_manage:view:{user_id}")
    builder.adjust(2)
    return builder.as_markup()

# --- НОВЫЙ РАЗДЕЛ: Клавиатуры для конструктора постов (/posts) ---

def get_post_constructor_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Текст", callback_data="post_constructor:edit_text")
    builder.button(text="🖼️ Медиа", callback_data="post_constructor:edit_media")
    builder.button(text="🎯 Аудитория", callback_data="post_constructor:edit_audience")
    builder.button(text="💾 Сохранить шаблон", callback_data="post_constructor:save_template")
    builder.button(text="📂 Загрузить шаблон", callback_data="post_constructor:load_template")
    builder.button(text="🚀 Отправить", callback_data="post_constructor:send")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_post_media_keyboard(has_media: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_media:
        builder.button(text="🗑️ Удалить последнее", callback_data="post_media:delete_last")
    builder.button(text="✅ Готово", callback_data="post_media:done")
    builder.button(text="❌ Отмена", callback_data="post_constructor:cancel_input")
    builder.adjust(1)
    return builder.as_markup()

def get_post_audience_keyboard(selected_audiences: List[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    audiences = {
        'all_users': 'Все пользователи',
        'admins': 'Админы',
        'super_admins': 'Главные админы',
        'testers': 'Тестеры'
    }
    for key, text in audiences.items():
        prefix = "✅ " if key in selected_audiences else ""
        builder.button(text=prefix + text, callback_data=f"post_audience:toggle:{key}")
    builder.button(text="⬅️ Назад к конструктору", callback_data="post_audience:back")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_post_template_list_keyboard(templates: list[PostTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not templates:
        builder.button(text="Шаблонов пока нет.", callback_data="noop")
    else:
        for t in templates:
            builder.button(text=t.template_name, callback_data=f"post_template:load:{t.id}")
    builder.button(text="🗑️ Удалить шаблон", callback_data="post_template:delete_start")
    builder.button(text="⬅️ Назад", callback_data="post_audience:back")
    builder.adjust(1)
    return builder.as_markup()
    
def get_post_confirm_send_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, отправить", callback_data="post_constructor:confirm_send")
    builder.button(text="⬅️ Нет, назад", callback_data="post_audience:back")
    builder.adjust(2)
    return builder.as_markup()

def get_close_post_keyboard() -> InlineKeyboardMarkup:
    """Кнопка для удаления полученного поста."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑️ Закрыть", callback_data="close_post")
    return builder.as_markup()
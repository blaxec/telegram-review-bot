# file: keyboards/inline.py

import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import Rewards, GOOGLE_API_KEYS
from aiogram import Bot
from logic import admin_roles
from database.models import UnbanRequest, InternshipApplication, User, PostTemplate, Administrator, Link, AIScenario
from typing import Set, List, Optional, Tuple, Dict

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

def get_profile_keyboard(first_task_completed: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🎁 Вывод звезд', callback_data='profile_withdraw')
    builder.button(text='💸 Передача звезд', callback_data='profile_transfer')
    builder.button(text='🏦 Депозиты', callback_data='show_deposits_menu')
    
    if first_task_completed:
        builder.button(text='💖 Помочь новичкам', callback_data='profile_donate')
    else:
        builder.button(text='🎁 Получить помощь', callback_data='get_daily_help')
        
    builder.button(text='📜 История операций', callback_data='profile_history')
    builder.button(text='🔗 Реферальная система', callback_data='profile_referral')
    builder.button(text='⏳ Холд', callback_data='profile_hold')
    builder.button(text='⬅️ Назад', callback_data='go_main_menu')
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()

def get_operation_history_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад в профиль', callback_data='go_profile')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_to_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='❌ Отмена', callback_data='go_profile')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_transfer_options_keyboard(data: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    comment_text = "✍️ Изменить комментарий" if data.get('transfer_comment') else "✍️ Добавить комментарий"
    media_text = f"🖼️ Управлять медиа ({len(data.get('transfer_media', []))}/3)"
    anon_text = "✅ Анонимно" if data.get('is_anonymous') else "🙈 Анонимно"
    
    builder.button(text=comment_text, callback_data="transfer_option:comment")
    builder.button(text=media_text, callback_data="transfer_option:media")
    builder.button(text=anon_text, callback_data="transfer_option:anonymous")
    builder.button(text="➡️ Продолжить", callback_data="transfer_option:confirm")
    builder.button(text="❌ Отмена", callback_data="go_profile")
    builder.adjust(2,1,1,1)
    return builder.as_markup()

def get_transfer_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='✅ Подтвердить', callback_data='transfer_confirm')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='go_profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_transfer_recipient_keyboard(transfer_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚨 Пожаловаться", callback_data=f"transfer_complain:{transfer_id}")
    builder.button(text="🗑️ Закрыть", callback_data="close_post")
    builder.adjust(1)
    return builder.as_markup()

# --- Раздел "Статистика" ---

def get_stats_keyboard(is_anonymous: bool) -> InlineKeyboardMarkup:
    anonymity_text = "🙈 Стать анонимным" if not is_anonymous else "🐵 Показать в топе"
    buttons = [
        [InlineKeyboardButton(text=anonymity_text, callback_data='profile_toggle_anonymity')],
        [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='go_main_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Передача и вывод звезд ---
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
        [InlineKeyboardButton(text='❌ Отмена', callback_data='go_profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_withdraw_recipient_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='👤 Себе', callback_data='withdraw_recipient_self')],
        [InlineKeyboardButton(text='👥 Указать пользователя', callback_data='withdraw_recipient_other')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='go_profile')]
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
    builder.button(text='💡 Как улучшить проходимость?', callback_data='info_how_to_improve_pass_rate')
    builder.button(text='⬅️ Назад', callback_data='earning_menu')
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()

def get_back_to_platform_choice_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='earning_write_review')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_subscribe_for_tasks_keyboard(platform: str, gender: str) -> InlineKeyboardMarkup:
    gender_map = {'male': 'мужских', 'female': 'женских', 'any': ''}
    platform_map = {'google_maps': 'Google', 'yandex_with_text': 'Yandex (с текстом)', 'yandex_without_text': 'Yandex (без текста)'}
    
    g_text = gender_map.get(gender, '')
    p_text = platform_map.get(platform, platform)
    
    btn_text = f"🔔 Уведомить о заданиях {p_text}"
    if g_text: btn_text += f" ({g_text})"
    
    buttons = [
        [InlineKeyboardButton(text=btn_text, callback_data=f'subscribe_for_tasks:{platform}:{gender}')],
        [InlineKeyboardButton(text='⬅️ Назад в меню', callback_data='earning_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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

def get_liking_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='👍 Выполнено', callback_data='google_confirm_liking_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_confirmation_keyboard(platform: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='👍 Выполнено', callback_data=f'{platform}_confirm_task')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_how_to_check_publication_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='❓ Как проверить публикацию?', callback_data='info_how_to_check_publication')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_awaiting_text_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='close_post')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_yandex_review_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text='С текстом', callback_data='yandex_review_type:with_text')],
        [InlineKeyboardButton(text='Без текста', callback_data='yandex_review_type:without_text')],
        [InlineKeyboardButton(text='✏ Этапы модерации Яндекс', callback_data='info_yandex_moderation_stages')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='earning_write_review')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_yandex_type_choice_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='⬅️ Назад', callback_data='review_yandex_maps')]]
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
    
def get_cancel_to_earning_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_to_earning')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Админские клавиатуры (верификация) ---

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
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"intern_verify:confirm:{context}:{user_id}")
    builder.button(text="❌ Отклонить", callback_data=f"intern_verify:reject:{context}:{user_id}")
    builder.button(text="⚠️ Выдать предупреждение", callback_data=f"intern_verify:warn:{context}:{user_id}")
    builder.adjust(2, 1)
    return builder.as_markup()

# --- Админские клавиатуры (выдача текста) ---

def get_admin_provide_text_keyboard(platform: str, user_id: int, link_id: int, requires_photo: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    photo_required_str = 'true' if requires_photo else 'false'
    builder.button(text='✍️ Ввести вручную (сценарий)', callback_data=f'admin_text_manual_start:{platform}:{user_id}:{link_id}:{photo_required_str}')
    builder.button(text='🤖 Сгенерировать с ИИ', callback_data=f'admin_ai_generate_start:{platform}:{user_id}:{link_id}:{photo_required_str}')
    builder.adjust(1)
    return builder.as_markup()

def get_manual_text_scenario_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✍ Ввести свой текст", callback_data="input_scenario_manually")
    builder.button(text="📂 Выбрать из банка сценариев", callback_data="use_scenario_template")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1)
    return builder.as_markup()

def get_ai_template_use_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сгенерировать", callback_data="ai_template:confirm_use")
    builder.button(text="✏ Редактировать текст", callback_data="ai_template:edit_text")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1, 1, 1)
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


# --- Админские клавиатуры (управление ссылками) ---

def get_admin_refs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Google Карты", callback_data="admin_refs:select_platform:google_maps")
    builder.button(text="Яндекс (с текстом)", callback_data="admin_refs:select_platform:yandex_with_text")
    builder.button(text="Яндекс (без текста)", callback_data="admin_refs:select_platform:yandex_without_text")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_back_to_platform_refs_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data=f"admin_refs:select_platform:{platform}")
    return builder.as_markup()

def get_admin_platform_refs_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=f"admin_refs:stats:{platform}")
    builder.button(text="📄 Показать список", callback_data=f"admin_refs:list:{platform}:all")
    
    types = [("regular_no_photo", "Обычные"), ("regular_photo", "С фото 📸"),
             ("fast_no_photo", "Быстрые 🚀"), ("fast_photo", "Быстрые с фото 🚀📸")]
    
    for link_type, label in types:
        builder.button(text=f"➕ {label}", callback_data=f"admin_refs:add:{platform}:{link_type}")
        
    builder.button(text="⬅️ Назад", callback_data="admin_refs:back_to_selection")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_gender_requirement_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Для всех 👤", callback_data="gender_any")
    builder.button(text="Только мужчины 👨", callback_data="gender_male")
    builder.button(text="Только женщины 👩", callback_data="gender_female")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1, 2, 1)
    return builder.as_markup()

def get_campaign_tag_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip_campaign_tag")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(1)
    return builder.as_markup()

def get_link_list_control_keyboard(platform: str, current_page: int, total_pages: int, filter_type: str, reward_filter: float = None, gender_filter: str = None, sort_by_tag: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    type_filters = [("Все", "all"), ("🚀", "fast"), ("📸", "photo"), ("📄", "regular")]
    type_btns = []
    for text, f_type in type_filters:
        btn_text = f"✅ {text}" if filter_type == f_type else text
        type_btns.append(InlineKeyboardButton(text=btn_text, callback_data=f"admin_refs:list:{platform}:{f_type}"))
    builder.row(*type_btns)
    
    reward_text = f"Награда: {reward_filter}⭐" if reward_filter is not None else "Награда"
    gender_icons = {'male': '👨', 'female': '👩', 'any': '👤'}
    gender_text = f"Пол: {gender_icons.get(gender_filter, 'Все')}" if gender_filter and gender_filter != 'all' else "Пол"
    sort_text = "✅ Теги" if sort_by_tag else "Теги"
    
    builder.row(
        InlineKeyboardButton(text=reward_text, callback_data=f"admin_refs:filter_reward:{platform}"),
        InlineKeyboardButton(text=gender_text, callback_data=f"admin_refs:filter_gender:{platform}"),
        InlineKeyboardButton(text=sort_text, callback_data=f"admin_refs:toggle_sort:{platform}")
    )
    
    if reward_filter is not None or (gender_filter and gender_filter != 'all'):
        builder.row(InlineKeyboardButton(text="🔄 Сбросить фильтры", callback_data=f"admin_refs:reset_filters:{platform}"))

    pagination_row = []
    if current_page > 1:
        pagination_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"links_page:{platform}:{current_page-1}"))
    if total_pages > 1:
        pagination_row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        pagination_row.append(InlineKeyboardButton(text="➡️", callback_data=f"links_page:{platform}:{current_page+1}"))
    if pagination_row:
        builder.row(*pagination_row)
        
    builder.row(
        InlineKeyboardButton(text='🗑️ Удалить ID', callback_data=f'admin_refs:delete_start:{platform}'),
        InlineKeyboardButton(text='↪️ Вернуть ID', callback_data=f'admin_refs:return_start:{platform}')
    )
    builder.row(InlineKeyboardButton(text='⬅️ Назад', callback_data=f'admin_refs:select_platform:{platform}'))
    return builder.as_markup()

def get_gender_filter_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Все", callback_data=f"admin_refs:set_gender:all:{platform}")
    builder.button(text="👨 Муж.", callback_data=f"admin_refs:set_gender:male:{platform}")
    builder.button(text="👩 Жен.", callback_data=f"admin_refs:set_gender:female:{platform}")
    builder.button(text="👤 Любой", callback_data=f"admin_refs:set_gender:any:{platform}")
    builder.button(text="⬅️ Назад", callback_data=f"admin_refs:list:{platform}:all")
    builder.adjust(4, 1)
    return builder.as_markup()

def get_reward_filter_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Сбросить фильтр награды", callback_data=f"admin_refs:reset_filters:{platform}")
    builder.button(text="⬅️ Назад", callback_data=f"admin_refs:list:{platform}:all")
    builder.adjust(1)
    return builder.as_markup()

# --- Кампании ---
def get_campaign_list_keyboard(tags: List[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tag in tags:
        builder.button(text=tag, callback_data=f"campaign_stats:{tag}")
    builder.button(text="🗑️ Закрыть", callback_data="close_post")
    builder.adjust(1)
    return builder.as_markup()

def get_back_to_campaigns_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К списку кампаний", callback_data="back_to_campaigns")
    builder.button(text="🗑️ Закрыть", callback_data="close_post")
    builder.adjust(1)
    return builder.as_markup()

# --- Админские клавиатуры (финальные решения) ---

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
    buttons = [
        [
            InlineKeyboardButton(text='✅ Одобрить и выплатить', callback_data=f'final_verify_approve:{review_id}'),
            InlineKeyboardButton(text='❌ Отклонить (списать)', callback_data=f'final_verify_reject:{review_id}')
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

# --- Пагинация (общая) ---

def get_pagination_keyboard(prefix: str, current_page: int, total_pages: int, show_close: bool = True, back_callback: Optional[str] = None) -> InlineKeyboardMarkup:
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
        builder.row(InlineKeyboardButton(text="🗑️ Закрыть", callback_data="close_post"))
        
    return builder.as_markup()

# --- Клавиатуры для поддержки, амнистии, жалоб ---
def get_support_admin_keyboard(ticket_id: int, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✍️ Ответить', callback_data=f'support_answer:{ticket_id}')
    builder.button(text='⚠️ Предупреждение', callback_data=f'support_warn:{ticket_id}:{user_id}')
    builder.adjust(1)
    return builder.as_markup()

def get_support_photo_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да", callback_data="support_add_photo:yes")
    builder.button(text="Нет", callback_data="support_add_photo:no")
    builder.button(text="Отмена", callback_data="cancel_action")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_amnesty_keyboard(requests: list[UnbanRequest], current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for req in requests:
        user = req.user
        username = f"@{user.username}" if user.username else f"ID {user.id}"
        builder.row(
            InlineKeyboardButton(text=f"✅ {username}", callback_data=f"amnesty:action:approve:{req.id}"),
            InlineKeyboardButton(text=f"❌ Отклонить", callback_data=f"amnesty:action:reject:{req.id}")
        )
    
    pagination_markup = get_pagination_keyboard("amnesty:page", current_page, total_pages, back_callback="panel:manage_bans")
    for row in pagination_markup.inline_keyboard:
        builder.row(*row)
    return builder.as_markup()

def get_complaints_keyboard(complaints: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pagination_markup = get_pagination_keyboard("complaints:page", page, total_pages, back_callback="panel:back_to_panel")
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
    builder.button(text="❌ Отмена", callback_data="panel:manage_promos")
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup()

def get_promo_conditional_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Начать задание", callback_data="promo_start_task")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data="promo_decline_task")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Клавиатуры для управления ролями, панели, стажировок, конструктора постов ---
async def get_roles_main_menu() -> InlineKeyboardMarkup:
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
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 С текстом", callback_data="roles_subcat:yandex_text")
    builder.button(text="🚫 Без текста", callback_data="roles_subcat:yandex_no_text")
    builder.button(text="◀ Назад", callback_data="roles_back:main")
    builder.adjust(2, 1)
    return builder.as_markup()

async def get_task_switching_keyboard(bot: Bot, category: str, subcategory: str = None) -> InlineKeyboardMarkup:
    tasks = admin_roles.get_tasks_for_category(category, subcategory)
    builder = InlineKeyboardBuilder()
    
    for task_key in tasks:
        description = admin_roles.ROLE_DESCRIPTIONS.get(task_key, task_key)
        admin_id = await admin_roles.get_responsible_admin(task_key)
        admin_name = await admin_roles.get_admin_username(bot, admin_id)
        builder.button(text=f"{description}: {admin_name}", callback_data=f"roles_switch:{task_key}")
    
    back_callback = "roles_back:main" if category != "yandex" else "roles_back:yandex"
    builder.button(text="◀ Назад", callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()

async def get_admin_selection_keyboard(admins: List[Administrator], role_key: str, current_admin_id: int, bot: Bot) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for admin in admins:
        prefix = "✅ " if admin.user_id == current_admin_id else ""
        try:
            chat = await bot.get_chat(admin.user_id)
            username = f"@{chat.username}" if chat.username else f"ID {admin.user_id}"
        except Exception:
            username = f"ID {admin.user_id}"
        builder.button(text=f"{prefix}{username}", callback_data=f"roles_set_admin:{role_key}:{admin.user_id}")
    
    category, subcategory = admin_roles.get_category_from_role_key(role_key)
    back_callback = f"roles_subcat:{category}_{subcategory}" if subcategory else f"roles_cat:{category}"
    builder.button(text="⬅️ Назад", callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()

def get_current_settings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить сообщение", callback_data="roles_delete_msg")
    return builder.as_markup()

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Блокировки", callback_data="panel:manage_bans")
    builder.button(text="✨ Промокоды", callback_data="panel:manage_promos")
    builder.button(text="💸 Штраф", callback_data="panel:issue_fine")
    builder.button(text="❄️ Сброс кулдаунов", callback_data="panel:reset_cooldown")
    builder.button(text="⏳ Холд юзера", callback_data="panel:view_hold")
    builder.button(text="🚨 Жалобы", callback_data="panel:view_complaints")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_ban_management_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Забанить", callback_data="panel:ban_user")
    builder.button(text="📜 Список забаненных", callback_data="panel:ban_list")
    builder.button(text="🙏 Амнистия", callback_data="panel:manage_amnesty")
    builder.button(text="⬅️ Назад", callback_data="panel:back_to_panel")
    builder.adjust(1)
    return builder.as_markup()

def get_promo_management_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ Создать", callback_data="panel:create_promo")
    builder.button(text="📝 Список", callback_data="panel:promo_list")
    builder.button(text="⬅️ Назад", callback_data="panel:back_to_panel")
    builder.adjust(1)
    return builder.as_markup()

def get_promo_list_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pagination_markup = get_pagination_keyboard("promolist:page", current_page, total_pages, show_close=False, back_callback="panel:manage_promos")
    for row in pagination_markup.inline_keyboard:
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="🗑️ Удалить по ID/коду", callback_data="promolist:delete_start"))
    return builder.as_markup()

async def get_roles_list_keyboard(admins: List[Administrator], page: int, total_pages: int, bot: Bot) -> Tuple[str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    text = "👥 **Список администраторов:**\n\n"
    
    if not admins:
        text += "Администраторы еще не добавлены."
    
    for admin in admins:
        try:
            chat = await bot.get_chat(admin.user_id)
            username = f"@{chat.username}" if chat.username else f"ID {admin.user_id}"
        except:
            username = f"ID {admin.user_id}"
        
        role_text = "👑" if admin.role == 'super_admin' else "🛡️"
        tester_text = " (🧪)" if admin.is_tester else ""
        
        builder.button(text=f"{role_text} {username}{tester_text}", callback_data=f"roles_manage:view:{admin.user_id}")

    pagination_markup = get_pagination_keyboard("roles_manage:list", page, total_pages, show_close=False, back_callback="roles_manage:back_to_menu")
    builder.adjust(1)
    for row in pagination_markup.inline_keyboard:
        builder.row(*row)
        
    return text, builder.as_markup()

def get_roles_manage_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить админа", callback_data="roles_manage:add")
    builder.button(text="📋 Список", callback_data="roles_manage:list:1")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
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
    builder.button(text="🛡️ Админ", callback_data="roles_manage:set_role:admin")
    builder.button(text="👑 Главный админ", callback_data="roles_manage:set_role:super_admin")
    builder.button(text="❌ Отмена", callback_data="roles_manage:back_to_menu")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_delete_admin_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data=f"roles_manage:delete_execute:{user_id}")],
        [InlineKeyboardButton(text="⬅️ Нет", callback_data=f"roles_manage:view:{user_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_internship_application_start_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text='📝 Заполнить анкету', callback_data='internship_app:start')]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_internship_platform_selection_keyboard(selected: set = None) -> InlineKeyboardMarkup:
    if selected is None: selected = set()
    builder = InlineKeyboardBuilder()
    platforms = [
        ("Google", "Google"), 
        ("Yandex (с текстом)", "YandexText"), 
        ("Yandex (без текста)", "YandexNoText"),
        ("Gmail", "Gmail")
    ]
    for name, callback_name in platforms:
        prefix = "✅ " if name in selected else ""
        builder.button(text=prefix + name, callback_data=f"internship_toggle:platform:{name}")
    
    builder.button(text="➡️ Далее", callback_data="internship_app:platforms_done")
    builder.button(text="❌ Отмена", callback_data="go_main_menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


async def get_admin_internships_main_menu(stats: Dict[str, int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📝 Анкеты ({stats['applications']})", callback_data="admin_internships:view:applications:1")
    builder.button(text=f"🧑‍🎓 Кандидаты ({stats['candidates']})", callback_data="admin_internships:view:candidates:1")
    builder.button(text=f"👨‍💻 Стажеры ({stats['interns']})", callback_data="admin_internships:view:interns:1")
    builder.button(text="🏠 Главное меню", callback_data="go_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_internship_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Возраст", callback_data="internship_app:start:age")
    builder.button(text="✏️ Часы", callback_data="internship_app:start:hours")
    builder.button(text="✏️ Ответ", callback_data="internship_app:start:response_time")
    builder.button(text="✏️ Платформы", callback_data="internship_app:start:platforms")
    builder.button(text="✅ Отправить", callback_data="internship_app:confirm")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_admin_application_review_keyboard(app: InternshipApplication) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"admin_internships:action:approve:{app.id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin_internships:action:reject:{app.id}")
    builder.button(text="⬅️ К списку", callback_data="admin_internships:view:applications:1")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_admin_intern_view_keyboard(intern: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Уволить", callback_data=f"admin_internships:fire_start:{intern.id}")
    builder.button(text="📜 Ошибки", callback_data=f"intern_cabinet:mistakes:{intern.id}:1")
    builder.button(text="⬅️ К списку", callback_data="admin_internships:view:interns:1")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_admin_intern_task_setup_keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Google (отзыв)", callback_data=f"admin_intern_task:type:google_review:{candidate_id}")
    builder.button(text="Yandex (текст)", callback_data=f"admin_intern_task:type:yandex_with_text:{candidate_id}")
    builder.button(text="Yandex (без)", callback_data=f"admin_intern_task:type:yandex_without_text:{candidate_id}")
    builder.button(text="Gmail", callback_data=f"admin_intern_task:type:gmail_account:{candidate_id}")
    builder.button(text="⬅️ Отмена", callback_data="admin_internships:view:candidates:1")
    builder.adjust(1)
    return builder.as_markup()

def get_post_constructor_keyboard(data: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    text_exists = bool(data.get("post_text"))
    media_exists = bool(data.get("post_media"))

    if not text_exists:
        builder.button(text="✍️ Добавить текст", callback_data="post_constructor:edit_text")
    else:
        builder.button(text="✍️ Изм. текст", callback_data="post_constructor:edit_text")
        builder.button(text="🗑️ Удал. текст", callback_data="post_constructor:delete_text")

    if not media_exists:
        builder.button(text="🖼️ Добавить медиа", callback_data="post_constructor:edit_media")
    else:
        builder.button(text="🖼️ Упр. медиа", callback_data="post_constructor:view_media")

    builder.button(text="🔘 Кнопки", callback_data="post_constructor:edit_buttons")
    builder.button(text="🎯 Аудитория", callback_data="post_constructor:edit_audience")
    builder.button(text="💾 Сохр. шаблон", callback_data="post_constructor:save_template")
    builder.button(text="📂 Загр. шаблон", callback_data="post_constructor:load_template")
    builder.button(text="🚀 Отправить", callback_data="post_constructor:send")
    builder.button(text="❓ Помощь", callback_data="post_constructor:show_format_help")
    builder.button(text="🏠 Меню", callback_data="go_main_menu")
    
    row1 = 1 if not text_exists else 2
    builder.adjust(row1, 1, 2, 2, 1, 1)
    return builder.as_markup()

def get_post_media_keyboard(has_media: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data="post:media_done")
    builder.button(text="❌ Отмена", callback_data="post:cancel_input")
    builder.adjust(1)
    return builder.as_markup()

def get_post_media_preview_keyboard(media_list: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, media in enumerate(media_list):
        builder.button(text=f"🗑️ {i+1}. {media['type']}", callback_data=f"post_media:delete:{i}")
    if len(media_list) < 10 and not any(m['type'] == 'gif' for m in media_list):
        builder.button(text="➕ Добавить", callback_data="post_constructor:edit_media")
    builder.button(text="⬅️ Назад", callback_data="post:back_to_constructor")
    builder.adjust(1)
    return builder.as_markup()

def get_post_buttons_manage_keyboard(buttons_list: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, btn in enumerate(buttons_list):
        builder.button(text=f"🗑️ {btn['text']}", callback_data=f"post_btn:delete:{i}")
    builder.button(text="➕ Добавить", callback_data="post_btn:add_start")
    builder.button(text="⬅️ Назад", callback_data="post:back_to_constructor")
    builder.adjust(1)
    return builder.as_markup()

def get_post_audience_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    audiences = {'all_users': 'Все', 'admins': 'Админы', 'super_admins': 'Главные', 'testers': 'Тестеры'}
    for key, text in audiences.items():
        prefix = "✅ " if key in selected else ""
        builder.button(text=prefix + text, callback_data=f"post_audience:toggle:{key}")
    builder.button(text="⬅️ Назад", callback_data="post:back_to_constructor")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_post_template_list_keyboard(templates: list[PostTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not templates:
        builder.button(text="Нет шаблонов", callback_data="noop")
    else:
        for t in templates:
            builder.button(text=t.template_name, callback_data=f"post_template:load:{t.id}")
    builder.button(text="⬅️ Назад", callback_data="post:back_to_constructor")
    builder.adjust(1)
    return builder.as_markup()

def get_post_confirm_send_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data="post_constructor:confirm_send")],
        [InlineKeyboardButton(text="⬅️ Нет", callback_data="post:back_to_constructor")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_close_post_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🗑️ Закрыть", callback_data="close_post")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_notification_close_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="Понятно", callback_data="close_post")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Клавиатуры для игр, депозитов, донатов, сценариев ---

def get_games_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪙 Орёл и Решка", callback_data="start_coinflip")
    builder.button(text="⬅️ В профиль", callback_data="go_profile")
    builder.adjust(1)
    return builder.as_markup()

def get_coinflip_bet_keyboard(play_again: bool = False, win_streak: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    bets = [1, 5, 10, 25]
    for bet in bets:
        builder.button(text=f"{bet} ⭐", callback_data=f"bet_{bet}")
    builder.button(text="Другая сумма", callback_data="custom_bet")
    
    back_text = "⬅️ Меню игр" if not play_again else "⏹️ Закончить"
    back_cb = "back_to_games_menu" if not play_again else "go_profile"

    builder.button(text=back_text, callback_data=back_cb)
    builder.adjust(4, 1, 1)
    return builder.as_markup()

def get_coinflip_choice_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🦅 Орёл", callback_data="choice_eagle"),
         InlineKeyboardButton(text="🪙 Решка", callback_data="choice_tails")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposits_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Открыть новый депозит", callback_data="open_new_deposit")],
        [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="go_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposit_plan_selection_keyboard(plans: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan_id, plan in plans.items():
        builder.button(text=plan['name'], callback_data=f"select_deposit_plan:{plan_id}")
    builder.button(text="❌ Отмена", callback_data="show_deposits_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_donation_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💰 Сделать пожертвование", callback_data="make_donation")],
        [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="go_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_scenarios_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить сценарий", callback_data="scenarios:add")],
        [InlineKeyboardButton(text="📂 Просмотреть/Управлять", callback_data="scenarios:view")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="go_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_scenario_category_keyboard(categories: list, action_prefix: str, show_add_new: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"{action_prefix}:{cat}")
    
    if show_add_new:
        builder.button(text="✨ (Создать новую категорию)", callback_data="scenarios:add_new_category")
        
    builder.button(text="⬅️ Назад", callback_data="scenarios:back_to_main")
    builder.adjust(2)
    return builder.as_markup()

def get_back_to_scenario_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К категориям", callback_data="scenarios:view")
    return builder.as_markup()

def get_scenario_management_keyboard(category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑️ Удалить по ID", callback_data=f"scenarios:manage:delete:{category}")
    builder.button(text="✏️ Редактировать по ID", callback_data=f"scenarios:manage:edit:{category}")
    builder.button(text="⬅️ К категориям", callback_data="scenarios:view")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_scenario_category_selection_keyboard(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"use_scenario_cat:{cat}")
    builder.button(text="✍ Ввести вручную", callback_data="input_scenario_manually")
    builder.adjust(2)
    return builder.as_markup()
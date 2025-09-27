# file: states/user_states.py

from aiogram.fsm.state import State, StatesGroup

class UserState(StatesGroup):
    MAIN_MENU = State()

    # Состояния для передачи звезд
    TRANSFER_AMOUNT_OTHER = State()
    TRANSFER_RECIPIENT = State()
    TRANSFER_AWAITING_MEDIA_CHOICE = State()
    TRANSFER_AWAITING_MEDIA = State()
    TRANSFER_COMMENT_INPUT = State()
    
    # Состояния для вывода звезд
    WITHDRAW_AMOUNT = State()
    WITHDRAW_AMOUNT_OTHER = State()
    WITHDRAW_RECIPIENT = State()
    WITHDRAW_USER_ID = State()
    WITHDRAW_ASK_COMMENT = State()
    WITHDRAW_COMMENT_INPUT = State()

    # Состояния для отзыва в Google
    GOOGLE_REVIEW_INIT = State()
    GOOGLE_REVIEW_ASK_PROFILE_SCREENSHOT = State()
    GOOGLE_REVIEW_PROFILE_CHECK_PENDING = State()
    GOOGLE_REVIEW_LAST_REVIEWS_CHECK = State()
    GOOGLE_REVIEW_LAST_REVIEWS_CHECK_PENDING = State()
    GOOGLE_REVIEW_READY_TO_CONTINUE = State()
    GOOGLE_REVIEW_LIKING_TASK_ACTIVE = State()
    GOOGLE_REVIEW_AWAITING_ADMIN_TEXT = State()
    GOOGLE_REVIEW_TASK_ACTIVE = State()
    GOOGLE_REVIEW_AWAITING_SCREENSHOT = State()
    
    AWAITING_CONFIRMATION_SCREENSHOT = State()

    # Состояния для отзыва в Yandex
    YANDEX_REVIEW_INIT = State()
    YANDEX_REVIEW_PROFILE_CHECK_PENDING = State()
    YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT = State()
    YANDEX_REVIEW_PROFILE_SCREENSHOT_PENDING = State()
    YANDEX_REVIEW_READY_TO_TASK = State()
    YANDEX_REVIEW_LIKING_TASK_ACTIVE = State()
    YANDEX_REVIEW_AWAITING_ADMIN_TEXT = State()
    YANDEX_REVIEW_TASK_ACTIVE = State()
    YANDEX_REVIEW_AWAITING_SCREENSHOT = State()
    
    # Состояния для создания Gmail
    GMAIL_ACCOUNT_INIT = State()
    GMAIL_AWAITING_DATA = State()
    GMAIL_AWAITING_VERIFICATION = State()
    GMAIL_INSTRUCTIONS = State()
    GMAIL_ENTER_DEVICE_MODEL = State()
    GMAIL_ENTER_ANOTHER_DEVICE_MODEL = State()

    # Состояния для промокодов
    PROMO_ENTER_CODE = State()
    PROMO_AWAITING_CHOICE = State()

    # Состояния для поддержки
    SUPPORT_AWAITING_QUESTION = State()
    SUPPORT_AWAITING_PHOTO_CHOICE = State()
    SUPPORT_AWAITING_PHOTO = State()

    # Состояния для реферальной системы
    REFERRAL_PATH_SELECTION = State()
    REFERRAL_YANDEX_SUBPATH_SELECTION = State()
    
    UNBAN_AWAITING_REASON = State()

    # Состояния для системы стажировок (пользователь)
    INTERNSHIP_APP_START = State()
    INTERNSHIP_APP_AGE = State()
    INTERNSHIP_APP_HOURS = State()
    INTERNSHIP_APP_PLATFORMS = State()
    INTERNSHIP_APP_CONFIRM = State()


class AdminState(StatesGroup):
    # Состояния для указания причин
    PROVIDE_REJECTION_REASON = State()
    PROVIDE_WARN_REASON = State()
    PROVIDE_FINAL_REJECTION_REASON = State()
    
    # Состояния для предоставления текста отзыва
    PROVIDE_GOOGLE_REVIEW_TEXT = State()
    PROVIDE_YANDEX_REVIEW_TEXT = State()
    
    # Состояния для генерации с ИИ
    AI_AWAITING_SCENARIO = State()
    AI_AWAITING_MODERATION = State()
    
    # Состояния для предоставления данных Gmail
    ENTER_GMAIL_DATA = State()

    # Состояния для штрафа (теперь запускаются из /panel)
    FINE_USER_ID = State()
    FINE_AMOUNT = State()
    FINE_REASON = State()
    
    # Состояния для создания промокода (теперь запускаются из /panel)
    PROMO_CODE_NAME = State()
    PROMO_CONDITION = State()
    PROMO_REWARD = State()
    PROMO_USES = State()
    
    # Состояния для поддержки
    SUPPORT_AWAITING_ANSWER = State()
    SUPPORT_AWAITING_WARN_REASON = State()
    SUPPORT_AWAITING_COOLDOWN_HOURS = State()

    # Состояния для управления ссылками
    ADD_LINKS = State() 
    DELETE_LINK_ID = State()
    RETURN_LINK_ID = State()
    LINK_LIST_VIEW = State()

    # Состояния для процесса бана (теперь запускаются из /panel)
    BAN_USER_IDENTIFIER = State()
    BAN_REASON = State()

    # Состояния для списков
    BAN_LIST_VIEW = State()
    PROMO_LIST_VIEW = State()
    PROMO_DELETE_CONFIRM = State()
    AMNESTY_LIST_VIEW = State()
    
    # Состояния для управления наградами
    REWARD_SETTINGS_MENU = State()
    REWARD_SET_PLACES_COUNT = State()
    REWARD_SET_AMOUNT_FOR_PLACE = State()
    REWARD_SET_TIMER = State()

    # Состояния для системы стажировок (админ)
    INTERNSHIP_CANDIDATE_TASK_GOAL = State()
    INTERNSHIP_FIRE_REASON = State()
    MENTOR_REJECT_REASON = State()

    # --- НОВЫЕ СОСТОЯНИЯ ДЛЯ ДИНАМИЧЕСКИХ РОЛЕЙ ---
    ROLES_ADD_ADMIN_ID = State()
    ROLES_ADD_ADMIN_ROLE = State()
    ROLES_DELETE_CONFIRM = State()
    
    # --- НОВЫЕ СОСТОЯНИЯ ДЛЯ КОНСТРУКТОРА ПОСТОВ ---
    POST_CONSTRUCTOR_AWAIT_TEXT = State()
    POST_CONSTRUCTOR_AWAIT_MEDIA = State()
    POST_CONSTRUCTOR_SAVE_TEMPLATE_NAME = State()
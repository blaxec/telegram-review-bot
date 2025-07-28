from aiogram.fsm.state import State, StatesGroup

class UserState(StatesGroup):
    MAIN_MENU = State()

    # Состояния для передачи звезд
    TRANSFER_AMOUNT_OTHER = State()
    TRANSFER_RECIPIENT = State()
    TRANSFER_SHOW_MY_NICK = State()
    TRANSFER_ASK_COMMENT = State()
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

    # Состояния для отзыва в Yandex
    YANDEX_REVIEW_INIT = State()
    YANDEX_REVIEW_PROFILE_CHECK_PENDING = State()
    YANDEX_REVIEW_ASK_PROFILE_SCREENSHOT = State()
    YANDEX_REVIEW_PROFILE_SCREENSHOT_PENDING = State()
    YANDEX_REVIEW_READY_TO_TASK = State()
    YANDEX_REVIEW_TASK_ACTIVE = State()
    YANDEX_REVIEW_AWAITING_TEXT_PHOTO = State()
    
    # Состояния для создания Gmail
    GMAIL_ACCOUNT_INIT = State()
    GMAIL_AWAITING_DATA = State()
    GMAIL_AWAITING_VERIFICATION = State()
    GMAIL_ENTER_DEVICE_MODEL = State()
    GMAIL_ENTER_ANOTHER_DEVICE_MODEL = State()


class AdminState(StatesGroup):
    # Состояния для добавления ссылок
    ADD_GOOGLE_REFERENCE = State()
    ADD_YANDEX_REFERENCE = State()

    # Состояния для указания причин отклонения
    REJECT_REASON_GOOGLE_PROFILE = State()
    REJECT_REASON_GOOGLE_LAST_REVIEWS = State()
    REJECT_REASON_YANDEX_PROFILE = State()
    REJECT_REASON_GOOGLE_REVIEW = State()
    REJECT_REASON_YANDEX_REVIEW = State()
    REJECT_REASON_GMAIL_ACCOUNT = State()
    REJECT_REASON_GMAIL_DATA_REQUEST = State()

    # Состояния для предоставления текста отзыва
    PROVIDE_GOOGLE_REVIEW_TEXT = State()
    
    # Состояния для предоставления данных Gmail
    ENTER_GMAIL_DATA = State()
# file: logic/ai_helper.py

import os
import asyncio
import logging
from groq import Groq, APIError

# Инициализируем логгер
logger = logging.getLogger(__name__)

# Загружаем ключ API из переменных окружения
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def generate_review_sync(client: Groq, system_prompt: str, user_prompt: str) -> str:
    """
    Синхронная обертка для вызова API Groq.
    Эта функция будет выполняться в отдельном потоке, чтобы не блокировать бота.
    """
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        model="llama3-8b-8192",
        temperature=0.7,
        max_tokens=200,
    )

    if (
        chat_completion
        and chat_completion.choices
        and isinstance(chat_completion.choices, list)
        and len(chat_completion.choices) > 0
        and chat_completion.choices[0].message
        and chat_completion.choices[0].message.content
    ):
        return chat_completion.choices[0].message.content.strip()
    else:
        logger.warning(f"Groq API returned a successful response but without content. Full response: {chat_completion}")
        raise ValueError("AI-модель вернула пустой ответ. Вероятно, сработал фильтр безопасности.")


async def generate_review_text(
    company_info: str,
    scenario: str,
    tone: str = "спокойный и довольный",
    details: list[str] = None
) -> str:
    """
    Генерирует текст отзыва с помощью API от Groq, выполняя вызов в отдельном потоке.
    """
    if not GROQ_API_KEY:
        logger.critical("Groq API key not found in .env file! AI generation is disabled.")
        return "Ошибка: AI-сервис не настроен. Отсутствует GROQ_API_KEY."

    # Создаем СИНХРОННЫЙ клиент
    client = Groq(api_key=GROQ_API_KEY)

    details_text = ""
    if details:
        details_list = "\n".join([f"- {detail}" for detail in details])
        details_text = f"\nЧто нужно упомянуть в тексте:\n{details_list}"

    # Усиленный системный промпт
    system_prompt = "Ты — талантливый копирайтер, который пишет короткие, живые и абсолютно естественные отзывы для Google и Яндекс Карт от лица разных людей. Твоя главная задача — избегать любых клише, роботизированных фраз и чрезмерного восторга. Текст должен звучать так, как будто его написал реальный человек. Твой ответ всегда должен быть только на русском языке, без единого английского слова."
    
    # Усиленный пользовательский промпт
    user_prompt = f"""
    Вот сценарий: "{scenario}".

    Напиши короткий положительный отзыв на 5 звезд от лица этого человека о заведении: "{company_info}".

    Требования:
    - Язык: Строго русский. Никаких английских слов или фраз.
    - Тон отзыва: {tone}.
    - Длина: 2-4 предложения.
    - НЕ используй шаблонные фразы вроде "рекомендую это место", "обязательно вернусь", "лучший в городе", "высокий уровень сервиса".
    - Пиши просто и по-человечески.
    {details_text}
    """

    try:
        # Выполняем синхронную функцию в отдельном потоке
        loop = asyncio.get_running_loop()
        generated_text = await loop.run_in_executor(
            None,  # Используем стандартный ThreadPoolExecutor
            generate_review_sync,
            client,
            system_prompt,
            user_prompt
        )
        return generated_text

    except APIError as e:
        logger.error(f"Groq API Error: {e}")
        return f"Ошибка AI-сервиса: {e.message}"
    except ValueError as e:
        # Наша кастомная ошибка для пустого ответа
        logger.warning(str(e))
        return f"Ошибка: {e}"
    except Exception as e:
        # Логируем полную трассировку ошибки для дебага
        logger.exception("An unknown error occurred during AI text generation!")
        return "Произошла неизвестная ошибка при генерации текста. Администратор уже уведомлен через логи."
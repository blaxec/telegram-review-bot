# file: logic/ai_helper.py

import os
from groq import Groq, APIError

# Загружаем ключ API из переменных окружения
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

async def generate_review_text(
    company_info: str,
    scenario: str,
    tone: str = "спокойный и довольный",
    details: list[str] = None
) -> str:
    """
    Генерирует текст отзыва с помощью надежного и быстрого API от Groq.
    """
    if not GROQ_API_KEY:
        print("ОШИБКА: Ключ Groq API не найден в .env файле!")
        return "Ошибка: AI-сервис не настроен. Отсутствует GROQ_API_KEY."

    client = Groq(api_key=GROQ_API_KEY)

    details_text = ""
    if details:
        details_list = "\n".join([f"- {detail}" for detail in details])
        details_text = f"\nЧто нужно упомянуть в тексте:\n{details_list}"

    system_prompt = "Ты — талантливый копирайтер, который пишет короткие, живые и абсолютно естественные отзывы для Google и Яндекс Карт от лица разных людей. Твоя главная задача — избегать любых клише, роботизированных фраз и чрезмерного восторга. Текст должен звучать так, как будто его написал реальный человек."
    user_prompt = f"""
    Вот сценарий: "{scenario}".

    Напиши короткий положительный отзыв на 5 звезд от лица этого человека о заведении: "{company_info}".

    Требования:
    - Тон отзыва: {tone}.
    - Длина: 2-4 предложения.
    - НЕ используй шаблонные фразы вроде "рекомендую это место", "обязательно вернусь", "лучший в городе", "высокий уровень сервиса".
    - Пиши просто и по-человечески.
    {details_text}
    """

    try:
        chat_completion = await client.chat.completions.create(
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
            model="llama3-8b-8192", # Используем быструю и качественную модель Llama 3
            temperature=0.7,
            max_tokens=200,
        )

        # --- НОВАЯ УЛУЧШЕННАЯ ПРОВЕРКА ОТВЕТА ---
        if (
            chat_completion.choices
            and chat_completion.choices[0].message
            and chat_completion.choices[0].message.content
        ):
            generated_text = chat_completion.choices[0].message.content
            return generated_text.strip()
        else:
            # Это происходит, если сработал фильтр безопасности Groq
            print(f"Groq API вернул успешный ответ, но без контента. Вероятная причина - фильтр безопасности. Ответ: {chat_completion}")
            return "Ошибка: AI-модель вернула пустой ответ. Вероятно, сработал фильтр безопасности. Пожалуйста, попробуйте перефразировать ваш сценарий."
        # --- КОНЕЦ ПРОВЕРКИ ---

    except APIError as e:
        print(f"Ошибка API Groq: {e}")
        return f"Ошибка AI-сервиса: {e.message}"
    except Exception as e:
        print(f"Неизвестная ошибка при обращении к Groq API: {e}")
        return "Произошла неизвестная ошибка при генерации текста."
# file: logic/ai_helper.py

import os
import httpx
import logging

HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
API_URL = "https://api-inference.huggingface.co/models/deepseek-ai/deepseek-llm-7b-chat"

logger = logging.getLogger(__name__)


async def generate_review_text(
    company_info: str,
    scenario: str,
    tone: str = "спокойный и довольный",
    details: list[str] = None
) -> str | None:
    """
    Генерирует текст отзыва с помощью бесплатного API Hugging Face (модель Deepseek).
    """
    if not HUGGINGFACE_TOKEN:
        logger.error("ОШИБКА: Токен Hugging Face не найден в .env файле!")
        return "Ошибка: AI не настроен."

    details_text = ""
    if details:
        details_list = "\n".join([f"- {detail}" for detail in details])
        details_text = f"\nЧто нужно упомянуть в тексте:\n{details_list}"

    # --- ИЗМЕНЕНИЕ: Формируем единую инструкцию для пользователя, т.к. системный промпт не поддерживается ---
    user_instruction = f"""
Ты — талантливый копирайтер. Твоя задача — написать короткий, живой и естественный отзыв для Google/Яндекс Карт.

Вот сценарий: "{scenario}".

Напиши короткий положительный отзыв на 5 звезд от лица этого человека о заведении: "{company_info}".

Требования к отзыву:
- Тон: {tone}.
- Длина: 2-4 предложения.
- Стиль: Простой и человечный.
- ЗАПРЕЩЕНО использовать шаблонные фразы вроде "рекомендую это место", "обязательно вернусь", "лучший в городе", "высокий уровень сервиса".
{details_text}

Ответь ТОЛЬКО текстом отзыва и ничем больше.
"""
    # --- ИЗМЕНЕНИЕ: Собираем промпт в формате, который указан в документации ---
    # Формат: "User: {инструкция}\n\nAssistant:"
    full_prompt = f"User: {user_instruction}\n\nAssistant:"


    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    
    payload = {
        "inputs": full_prompt,
        "parameters": {
            "max_new_tokens": 200,
            "temperature": 0.7,
            "return_full_text": False,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result[0]['generated_text']
            
            # Убираем возможный лишний токен в конце ответа
            if generated_text.endswith("<｜end of sentence｜>"):
                generated_text = generated_text[:-len("<｜end of sentence｜>")]

            return generated_text.strip()
            
    except httpx.ReadTimeout:
        logger.error("Ошибка: Hugging Face API не ответил вовремя.")
        return "AI-сервер перегружен, попробуйте через минуту."
    except Exception as e:
        logger.exception(f"Ошибка при обращении к Hugging Face API: {e}")
        error_text = str(e)
        if "is currently loading" in error_text:
             return "AI-модель сейчас загружается. Пожалуйста, подождите 1-2 минуты и попробуйте снова."
        if "Input validation error" in error_text:
            return "Ошибка в формате запроса к AI. Обратитесь к разработчику."
        return "Произошла ошибка при генерации текста."
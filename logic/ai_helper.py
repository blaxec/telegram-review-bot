# file: logic/ai_helper.py

import os
import json
import httpx

HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
# --- ИЗМЕНЕНИЕ: Используем новую, более мощную и доступную модель ---
API_URL = "https://api-inference.huggingface.co/models/deepseek-ai/DeepSeek-V2-Lite-Chat"

async def generate_review_text(
    company_info: str,
    scenario: str,
    tone: str = "спокойный и довольный",
    details: list[str] = None
) -> str | None:
    """
    Генерирует текст отзыва с помощью бесплатного API Hugging Face (модель Deepseek-V2).
    """
    if not HUGGINGFACE_TOKEN:
        print("ОШИБКА: Токен Hugging Face не найден в .env файле!")
        return "Ошибка: AI не настроен."

    details_text = ""
    if details:
        details_list = "\n".join([f"- {detail}" for detail in details])
        details_text = f"\nЧто нужно упомянуть в тексте:\n{details_list}"

    # --- ИЗМЕНЕНИЕ: Промпт в формате чата, который лучше подходит для Deepseek-v2 ---
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
    # Собираем промпт в формате "разговора"
    # Это официальный формат для моделей Deepseek
    full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant"


    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    
    payload = {
        "inputs": full_prompt,
        "parameters": {
            "max_new_tokens": 200,
            "temperature": 0.7,
            "return_full_text": False, # Мы не хотим получать наш промпт в ответе
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            generated_text = result[0]['generated_text']
            
            # Иногда модель может закончить ответ специальным токеном <|im_end|>, его нужно убрать
            if generated_text.endswith("<|im_end|>"):
                generated_text = generated_text[:-len("<|im_end|>")]

            return generated_text.strip()
            
    except httpx.ReadTimeout:
        print("Ошибка: Hugging Face API не ответил вовремя.")
        return "AI-сервер перегружен, попробуйте через минуту."
    except Exception as e:
        print(f"Ошибка при обращении к Hugging Face API: {e}")
        error_text = str(e)
        if "is currently loading" in error_text:
             return "AI-модель сейчас загружается. Пожалуйста, подождите 1-2 минуты и попробуйте снова."
        if "Input validation error" in error_text:
            return "Ошибка в формате запроса к AI. Обратитесь к разработчику."
        return "Произошла ошибка при генерации текста."

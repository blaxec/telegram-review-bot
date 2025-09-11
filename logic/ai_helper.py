# file: logic/ai_helper.py

import os
import asyncio
import logging
import json
from groq import Groq, APIError

from duckduckgo_search import DDGS
from config import GROQ_MODEL_NAME

# Инициализируем логгер
logger = logging.getLogger(__name__)

# Загружаем ключ API Groq из переменных окружения
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def perform_web_search(query: str):
    """
    Выполняет поиск в интернете по заданному запросу, чтобы найти актуальную информацию.

    Args:
        query: Поисковый запрос (например, 'особенности кафе Ромашка' или 'чем известно ООО Вектор').
    """
    try:
        with DDGS() as ddgs:
            results = [r['body'] for r in ddgs.text(query, max_results=3)]
            if not results:
                return "Поиск не дал результатов."
            return "\n".join(results)
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return f"Ошибка при поиске: {e}"

def generate_review_sync(client: Groq, model: str, system_prompt: str, user_prompt: str, tools: list = None) -> str:
    """
    Синхронная обертка для вызова API Groq, которая умеет работать с инструментами.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=tools,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=400,
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if not tool_calls:
        return response_message.content.strip()

    logger.info(f"AI requested tool call: {tool_calls[0].function.name}")
    
    available_tools = {
        "perform_web_search": perform_web_search,
    }
    
    function_name = tool_calls[0].function.name
    function_to_call = available_tools.get(function_name)
    
    if not function_to_call:
        return f"Ошибка: модель запросила несуществующий инструмент '{function_name}'."

    try:
        function_args = json.loads(tool_calls[0].function.arguments)
    except json.JSONDecodeError:
        return "Ошибка: модель вернула некорректные аргументы для инструмента."
        
    function_response = function_to_call(**function_args)

    second_response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            response_message,
            {
                "tool_call_id": tool_calls[0].id,
                "role": "tool",
                "name": function_name,
                "content": function_response,
            },
        ],
    )
    
    return second_response.choices[0].message.content.strip()


async def generate_review_text(
    company_info: str,
    scenario: str,
    tone: str = "спокойный и довольный"
) -> str:
    """
    Генерирует текст отзыва, используя Groq и, при необходимости, поиск в интернете.
    """
    if not GROQ_API_KEY:
        logger.critical("Groq API key not found in .env file! AI generation is disabled.")
        return "Ошибка: AI-сервис не настроен. Отсутствует GROQ_API_KEY."

    client = Groq(api_key=GROQ_API_KEY)

    search_tool = {
        "type": "function",
        "function": {
            "name": "perform_web_search",
            "description": "Искать в интернете актуальную информацию о компании, ее услугах или особенностях.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос, например 'особенности кафе Ромашка'",
                    }
                },
                "required": ["query"],
            },
        },
    }

    # ИЗМЕНЕНИЕ: Указываем ИИ использовать HTML-теги для выделения жирным.
    system_prompt = "Ты — талантливый копирайтер, который пишет короткие, живые и абсолютно естественные отзывы для Google и Яндекс Карт. Твоя главная задача — избегать любых клише и роботизированных фраз. Текст должен звучать так, как будто его написал реальный человек. Если для написания качественного отзыва не хватает информации, используй инструмент поиска. Твой ответ всегда должен быть только на русском языке."
    
    user_prompt = f"""
    Мне нужно написать отзыв о компании/месте: "{company_info}".
    Сценарий отзыва: "{scenario}".
    Тон отзыва должен быть: {tone}.

    Пожалуйста, сгенерируй короткий (2-4 предложения) и естественный отзыв на 5 звезд. Если в сценарии не хватает деталей, используй поиск, чтобы найти что-то уникальное об этом месте (например, их фирменное блюдо, особенность интерьера или популярную услугу) и ненавязчиво впиши это в отзыв.
    
    НЕ используй шаблонные фразы вроде "рекомендую это место", "обязательно вернусь", "лучший в городе".
    """

    try:
        loop = asyncio.get_running_loop()
        
        # --- ИЗМЕНЕНИЕ: Используем модель из конфига ---
        model_to_use = GROQ_MODEL_NAME
        
        generated_text = await loop.run_in_executor(
            None,
            generate_review_sync,
            client,
            model_to_use, 
            system_prompt,
            user_prompt,
            [search_tool]
        )
        return generated_text

    except APIError as e:
        logger.error(f"Groq API Error: {e}")
        return f"Ошибка AI-сервиса: {e.message}"
    except Exception as e:
        logger.exception("An unknown error occurred during AI text generation!")
        return "Произошла неизвестная ошибка при генерации текста. Администратор уже уведомлен через логи."
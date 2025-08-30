# file: logic/ocr_helper.py

import logging
import datetime
import re
from io import BytesIO
from itertools import cycle
from typing import Literal, Dict, Any, List

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from aiogram import Bot

from config import GOOGLE_API_KEYS, ADMIN_ID_1

logger = logging.getLogger(__name__)

AnalysisTask = Literal['yandex_level', 'review_date']

class GeminiKeyManager:
    """Управляет ротацией и состоянием API-ключей Google Gemini."""
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.key_iterator = cycle(self.keys)
        self.exhausted_keys = set()

    def get_next_key(self) -> str | None:
        """Возвращает следующий рабочий ключ или None, если все исчерпаны."""
        if not self.keys:
            return None
        if len(self.exhausted_keys) == len(self.keys):
            logger.error("All Google API keys are exhausted.")
            return None
        
        # Прокручиваем итератор, пока не найдем рабочий ключ
        for _ in range(len(self.keys)):
            key = next(self.key_iterator)
            if key not in self.exhausted_keys:
                return key
        return None

    def mark_key_as_exhausted(self, key: str):
        """Помечает ключ как исчерпавший лимит."""
        logger.warning(f"Google API key ending with '...{key[-4:]}' has been marked as exhausted.")
        self.exhausted_keys.add(key)

# Создаем один экземпляр менеджера для всего бота
key_manager = GeminiKeyManager(GOOGLE_API_KEYS)


async def _get_image_from_telegram(bot: Bot, file_id: str) -> BytesIO | None:
    """Скачивает файл по file_id и возвращает его в виде BytesIO."""
    try:
        file_info = await bot.get_file(file_id)
        if not file_info.file_path:
            return None
        
        image_bytes = await bot.download_file(file_info.file_path)
        return image_bytes
    except Exception as e:
        logger.error(f"Failed to download image with file_id {file_id}: {e}")
        return None

def _parse_yandex_level(text: str) -> int | None:
    """Извлекает числовой уровень из текста, возвращенного AI."""
    # Ищем числа (целые или с плавающей точкой)
    numbers = re.findall(r'\d+', text)
    if numbers:
        try:
            # Берем первое найденное число
            return int(numbers[0])
        except (ValueError, IndexError):
            return None
    return None

def _parse_review_date(text: str) -> datetime.date | None:
    """Извлекает и парсит дату из текста, возвращенного AI."""
    # Ищем дату в формате ДД.ММ.ГГГГ
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', text)
    if match:
        try:
            day, month, year = map(int, match.groups())
            return datetime.date(year, month, day)
        except ValueError:
            return None
    return None


async def analyze_screenshot(bot: Bot, file_id: str, task: AnalysisTask) -> Dict[str, Any]:
    """
    Анализирует скриншот с помощью Google Gemini Vision, управляя API-ключами.
    """
    if not GOOGLE_API_KEYS:
        return {"status": "error", "message": "OCR service is not configured."}

    image_bytes = await _get_image_from_telegram(bot, file_id)
    if not image_bytes:
        return {"status": "error", "message": "Failed to download image from Telegram."}

    image_for_api = {'mime_type': 'image/png', 'data': image_bytes.getvalue()}
    
    # Определяем промпт в зависимости от задачи
    if task == 'yandex_level':
        prompt = "На этом изображении профиля Яндекс Карт найди уровень 'Знатока города'. В ответе напиши только одно число, обозначающее этот уровень. Например: 5"
    elif task == 'review_date':
        prompt = "На этом скриншоте из профиля отзывов найди дату самого последнего (верхнего) отзыва. В ответе напиши только эту дату в формате ДД.ММ.ГГГГ. Например: 21.08.2025"
    else:
        return {"status": "error", "message": f"Unknown OCR task: {task}"}

    # Цикл для перебора ключей в случае ошибки квоты
    for _ in range(len(GOOGLE_API_KEYS)):
        api_key = key_manager.get_next_key()
        if not api_key:
            try:
                # Уведомляем админа, что все ключи закончились
                await bot.send_message(ADMIN_ID_1, "🚨 ВНИМАНИЕ! Все API ключи для распознавания изображений (Google Gemini) исчерпали свой дневной лимит. Автопроверка скриншотов отключена до следующего дня.")
            except Exception as e:
                logger.error(f"Failed to notify admin about exhausted keys: {e}")
            return {"status": "error", "message": "All API keys are exhausted."}
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        try:
            logger.info(f"Attempting OCR with key ...{api_key[-4:]} for task '{task}'.")
            response = await model.generate_content_async([prompt, image_for_api])
            
            # --- Обработка результата ---
            raw_text = response.text.strip()
            logger.info(f"Gemini response for task '{task}': '{raw_text}'")

            if task == 'yandex_level':
                level = _parse_yandex_level(raw_text)
                if level is not None:
                    return {"status": "success", "level": level}
            
            elif task == 'review_date':
                date = _parse_review_date(raw_text)
                if date:
                    return {"status": "success", "date": date}

            # Если парсинг не удался, считаем результат неопределенным
            return {"status": "uncertain", "reason": "Could not parse AI response.", "raw_text": raw_text}

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Quota exhausted for Google API key ...{api_key[-4:]}. Trying next key.")
            key_manager.mark_key_as_exhausted(api_key)
            try:
                # Уведомляем админа, что один из ключей закончился
                await bot.send_message(ADMIN_ID_1, f"🔔 API ключ Google Gemini (заканчивается на ...{api_key[-4:]}) исчерпал свой дневной лимит. Бот автоматически переключился на следующий.")
            except Exception as admin_notify_error:
                logger.error(f"Failed to notify admin about exhausted key: {admin_notify_error}")
            continue # Переходим к следующему ключу

        except Exception as e:
            logger.exception(f"An unexpected error occurred with Google Gemini API using key ...{api_key[-4:]}")
            return {"status": "error", "message": str(e)}

    # Если мы вышли из цикла, значит все ключи были перебраны и не сработали
    return {"status": "error", "message": "All available API keys failed or are exhausted."}
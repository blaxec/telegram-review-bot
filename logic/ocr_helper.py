# file: logic/ocr_helper.py

import logging
import datetime
import re
import json
from io import BytesIO
from itertools import cycle
from typing import Literal, Dict, Any, List, Optional

import pytz
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from aiogram import Bot

from config import GOOGLE_API_KEYS, ADMIN_ID_1

logger = logging.getLogger(__name__)

AnalysisTask = Literal['yandex_level', 'review_date', 'google_profile']
# Устанавливаем часовой пояс Алматы
almaty_tz = pytz.timezone('Asia/Almaty')

class GeminiKeyManager:
    """Управляет ротацией и состоянием API-ключей Google Gemini."""
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.key_iterator = cycle(self.keys)
        self.exhausted_keys = set()
        if not self.keys:
            logger.warning("OCR Key Manager initialized with no keys.")

    def get_next_key(self) -> str | None:
        """Возвращает следующий рабочий ключ или None, если все исчерпаны."""
        if not self.keys:
            return None
        if len(self.exhausted_keys) == len(self.keys):
            logger.error("All Google API keys are exhausted.")
            return None
        
        for _ in range(len(self.keys)):
            key = next(self.key_iterator)
            if key not in self.exhausted_keys:
                return key
        return None

    def mark_key_as_exhausted(self, key: str):
        """Помечает ключ как исчерпавший лимит."""
        logger.warning(f"Google API key ending with '...{key[-4:]}' has been marked as exhausted.")
        self.exhausted_keys.add(key)

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

def _parse_relative_date(text: str, today: datetime.date) -> Optional[datetime.date]:
    """Пытается распарсить относительные даты типа 'неделю назад', используя 'сегодня' в правильном часовом поясе."""
    text = text.lower()
    match = re.search(r'(\d+)\s+(день|дня|дней|недел|месяц)', text)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if 'ден' in unit:
            return today - datetime.timedelta(days=value)
        if 'недел' in unit:
            return today - datetime.timedelta(weeks=value)
        if 'месяц' in unit:
            return today - datetime.timedelta(days=value * 30) # Приблизительно
    if 'вчера' in text:
        return today - datetime.timedelta(days=1)
    if 'сегодня' in text:
        return today
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

    image_for_api = {'mime_type': 'image/jpeg', 'data': image_bytes.getvalue()}
    
    # Используем 'сегодня' по часовому поясу Алматы
    today_in_almaty = datetime.datetime.now(almaty_tz).date()
    today_str = today_in_almaty.strftime('%d.%m.%Y')
    
    prompt = ""
    # Улучшенные промпты с требованием JSON-ответа
    if task == 'yandex_level':
        prompt = f"""
        Проанализируй это изображение профиля Яндекс Карт. Найди числовой уровень "Знатока города".
        Твоя задача вернуть ответ ТОЛЬКО в формате JSON.
        - Если ты уверенно видишь числовой уровень, верни: {{"status": "success", "level": ЧИСЛО}}
        - Если ты не можешь найти уровень, верни: {{"status": "uncertain", "reason": "Уровень не найден на изображении"}}
        Пример успешного ответа: {{"status": "success", "level": 5}}
        """
    elif task == 'review_date' or task == 'google_profile': # Объединяем, так как задача одна
        prompt = f"""
        Проанализируй это изображение из профиля Google Карт. Сегодняшняя дата: {today_str} (по времени Алматы).
        Найди дату самого последнего (верхнего) отзыва.
        Твоя задача вернуть ответ ТОЛЬКО в формате JSON.
        - Если ты видишь точную дату (например, 21.08.2025), верни ее в поле "date": {{"status": "success", "date": "ДД.ММ.ГГГГ"}}
        - Если ты видишь относительную дату (например, "неделю назад", "вчера"), верни ее в поле "text": {{"status": "relative", "text": "ОРИГИНАЛЬНЫЙ_ТЕКСТ_ДАТЫ"}}
        - Если ты не можешь найти дату, верни: {{"status": "uncertain", "reason": "Дата не найдена на изображении"}}
        Пример ответа 1: {{"status": "success", "date": "21.08.2025"}}
        Пример ответа 2: {{"status": "relative", "text": "неделю назад"}}
        """
    else:
        return {"status": "error", "message": f"Unknown OCR task: {task}"}

    for _ in range(len(GOOGLE_API_KEYS)):
        api_key = key_manager.get_next_key()
        if not api_key:
            try:
                await bot.send_message(ADMIN_ID_1, "🚨 ВНИМАНИЕ! Все API ключи для распознавания изображений (Google Gemini) исчерпали свой дневной лимит. Автопроверка скриншотов отключена до следующего дня.")
            except Exception as e:
                logger.error(f"Failed to notify admin about exhausted keys: {e}")
            return {"status": "error", "message": "All API keys are exhausted."}
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        try:
            logger.info(f"Attempting OCR with key ...{api_key[-4:]} for task '{task}'.")
            response = await model.generate_content_async([prompt, image_for_api])
            
            # Очищаем ответ от markdown обертки для JSON
            clean_response_text = response.text.strip()
            if clean_response_text.startswith("```json"):
                clean_response_text = clean_response_text[7:]
            if clean_response_text.endswith("```"):
                clean_response_text = clean_response_text[:-3]
            
            logger.info(f"Gemini response for task '{task}': '{clean_response_text}'")
            
            try:
                data = json.loads(clean_response_text)
                
                if data.get("status") == "success":
                    return data
                
                if data.get("status") == "relative":
                    parsed_date = _parse_relative_date(data.get("text", ""), today_in_almaty)
                    if parsed_date:
                        return {"status": "success", "date": parsed_date.strftime('%d.%m.%Y')}
                    else:
                        return {"status": "uncertain", "reason": f"Could not parse relative date: {data.get('text')}"}

                return data # Возвращаем uncertain

            except json.JSONDecodeError:
                return {"status": "uncertain", "reason": "AI returned non-JSON response.", "raw_text": clean_response_text}

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Quota exhausted for Google API key ...{api_key[-4:]}. Trying next key.")
            key_manager.mark_key_as_exhausted(api_key)
            try:
                await bot.send_message(ADMIN_ID_1, f"🔔 API ключ Google Gemini (заканчивается на ...{api_key[-4:]}) исчерпал свой дневной лимит. Бот автоматически переключился на следующий.")
            except Exception as admin_notify_error:
                logger.error(f"Failed to notify admin about exhausted key: {admin_notify_error}")
            continue

        except Exception as e:
            logger.exception(f"An unexpected error occurred with Google Gemini API using key ...{api_key[-4:]}")
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": "All available API keys failed or are exhausted."}
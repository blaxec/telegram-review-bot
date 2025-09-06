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

# ИЗМЕНЕНИЕ: Упрощаем типы задач и устанавливаем часовой пояс
AnalysisTask = Literal['yandex_level', 'review_date_check']
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
    if task == 'yandex_level':
        prompt = f"""
        Проанализируй это изображение профиля Яндекс Карт. Найди числовой уровень "Знатока города".
        Твоя задача вернуть ответ ТОЛЬКО в формате JSON.
        - Если ты уверенно видишь числовой уровень, верни: {{"status": "success", "level": ЧИСЛО}}
        - Если ты не можешь найти уровень, верни: {{"status": "uncertain", "reason": "Уровень не найден на изображении"}}
        Пример успешного ответа: {{"status": "success", "level": 5}}
        """
    # --- ИЗМЕНЕНИЕ: Полностью новый, умный промпт для анализа даты ---
    elif task == 'review_date_check':
        prompt = f"""
        Ты — внимательный ассистент-аналитик. Твоя задача — проанализировать скриншот из профиля Google или Яндекс Карт и определить, может ли пользователь написать новый отзыв.

        КОНТЕКСТ:
        - Сегодняшняя дата (по времени Алматы, Казахстан): **{today_str}**.
        - ГЛАВНОЕ ПРАВИЛО: Пользователь может написать новый отзыв, только если его последний отзыв был опубликован **3 (три) или более дней назад**.

        ТВОЯ ЗАДАЧА:
        1. Найди на скриншоте самый верхний, самый свежий отзыв.
        2. Определи его дату публикации. Дата может быть абсолютной ("15.08.2025") или относительной ("вчера", "2 дня назад", "неделю назад", "месяц назад").
        3. Вычисли, сколько дней прошло между датой публикации отзыва и СЕГОДНЯШНЕЙ датой ({today_str}).
        4. Примени ГЛАВНОЕ ПРАВИЛО.
        5. Верни свой ответ СТРОГО в формате JSON.

        ФОРМАТ ОТВЕТА JSON:
        - Если ты уверен в дате и можешь принять решение:
          {{"status": "success", "is_valid": true/false, "days_passed": ЧИСЛО_ДНЕЙ, "detected_date_text": "ТЕКСТ_ДАТЫ_С_КАРТИНКИ", "reason": "Краткое пояснение"}}
        - Если ты не можешь найти дату или не уверен:
          {{"status": "uncertain", "reason": "Причина неуверенности"}}

        ПРИМЕРЫ:
        - Сегодня {today_str}. На картинке "неделю назад". Ответ: {{"status": "success", "is_valid": true, "days_passed": 7, "detected_date_text": "неделю назад", "reason": "Прошло 7 дней, что больше 3."}}
        - Сегодня {today_str}. На картинке "вчера". Ответ: {{"status": "success", "is_valid": false, "days_passed": 1, "detected_date_text": "вчера", "reason": "Прошел 1 день, что меньше 3."}}
        - Сегодня {today_str}. На картинке "2 дня назад". Ответ: {{"status": "success", "is_valid": false, "days_passed": 2, "detected_date_text": "2 дня назад", "reason": "Прошло 2 дня, что меньше 3."}}
        - Сегодня {today_str}. На картинке "месяц назад". Ответ: {{"status": "success", "is_valid": true, "days_passed": 30, "detected_date_text": "месяц назад", "reason": "Прошло около 30 дней, что больше 3."}}
        - На картинке нет видимой даты. Ответ: {{"status": "uncertain", "reason": "Не удалось найти дату последнего отзыва на изображении."}}
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
            
            clean_response_text = response.text.strip()
            if clean_response_text.startswith("```json"):
                clean_response_text = clean_response_text[7:]
            if clean_response_text.endswith("```"):
                clean_response_text = clean_response_text[:-3]
            
            logger.info(f"Gemini response for task '{task}': '{clean_response_text}'")
            
            try:
                data = json.loads(clean_response_text)
                return data

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
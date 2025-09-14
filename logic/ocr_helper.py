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

# ИЗМЕНЕНИЕ: Новые, более конкретные типы задач
AnalysisTask = Literal['yandex_profile_check', 'google_profile_check', 'google_reviews_check']
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
    
    # ИСПОЛЬЗУЕМ ЧАСОВОЙ ПОЯС АЛМАТЫ (UTC+5)
    today_in_almaty = datetime.datetime.now(pytz.timezone('Asia/Almaty')).date()
    today_str = today_in_almaty.strftime('%d.%m.%Y')
    
    prompt = ""
    # --- НОВЫЕ СПЕЦИАЛИЗИРОВАННЫЕ ПРОМПТЫ ---
    if task == 'google_profile_check':
        prompt = f"""
        Ты — ассистент-аналитик, проверяющий скриншоты профилей Google. Твоя задача — проверить имя и фамилию пользователя на соответствие правилам.

        ПРАВИЛА ПРОВЕРКИ ИМЕНИ:
        1.  Имя не должно быть случайным набором букв (например, "fjdovvd", "ывапрол").
        2.  Имя не должно содержать матерные или оскорбительные слова.
        3.  Имя не должно содержать цифры.
        4.  Имя или фамилия не должны состоять из одной буквы.
        5.  Имя не должно быть написано с использованием арабского, китайского, японского или корейского алфавитов. Имена на кириллице и латинице приемлемы.

        ТВОЯ ЗАДАЧА:
        1.  Найди на скриншоте имя и фамилию пользователя.
        2.  Проверь их на соответствие всем правилам выше.
        3.  Верни свой вердикт СТРОГО в формате JSON.

        ФОРМАТ ОТВЕТА JSON:
        {{
          "status": "success",
          "analysis_summary": "Краткий вывод (например, 'Проверка имени пройдена' или 'Проверка имени провалена')",
          "name_check_passed": true/false,
          "reasoning": "Подробное объяснение твоего решения. Если проверка провалена, укажи, какое правило было нарушено."
        }}
        
        Пример 1 (успех): {{"status": "success", "analysis_summary": "Проверка имени пройдена", "name_check_passed": true, "reasoning": "Имя 'Иван Петров' соответствует всем правилам."}}
        Пример 2 (провал): {{"status": "success", "analysis_summary": "Проверка имени провалена", "name_check_passed": false, "reasoning": "Имя 'фывфыв' выглядит как случайный набор символов."}}
        """
    elif task == 'google_reviews_check':
        prompt = f"""
        Ты — ассистент-аналитик, проверяющий скриншоты с отзывами Google.

        КОНТЕКСТ:
        - Сегодняшняя дата (по времени Алматы, Казахстан, UTC+5): **{today_str}**.
        - ГЛАВНОЕ ПРАВИЛО: Пользователь может написать новый отзыв, только если его последний (самый верхний) отзыв был опубликован **3 (три) или более дней назад**.

        ТВОЯ ЗАДАЧА:
        1.  Найди на скриншоте самый верхний, самый свежий отзыв.
        2.  Определи его дату публикации (она может быть абсолютной: "15.08.2025" или относительной: "вчера", "2 дня назад", "неделю назад", "месяц назад").
        3.  Вычисли, сколько дней прошло между датой отзыва и СЕГОДНЯШНЕЙ датой ({today_str}).
        4.  Примени ГЛАВНОЕ ПРАВИЛО.
        5.  Верни свой вердикт СТРОГО в формате JSON.

        ФОРМАТ ОТВЕТА JSON:
        {{
          "status": "success",
          "analysis_summary": "Краткий вывод (например, 'Проверка даты пройдена' или 'Проверка даты провалена')",
          "date_check_passed": true/false,
          "days_passed": ЧИСЛО_ДНЕЙ_ИЛИ_NULL,
          "detected_date_text": "ТЕКСТ_ДАТЫ_С_КАРТИНКИ",
          "reasoning": "Подробное объяснение твоего решения."
        }}

        Пример 1: Сегодня {today_str}. На скриншоте "неделю назад". Ответ: {{"status": "success", "analysis_summary": "Проверка даты пройдена", "date_check_passed": true, "days_passed": 7, "detected_date_text": "неделю назад", "reasoning": "Прошло 7 дней, что соответствует правилу (>= 3 дня)."}}
        Пример 2: Сегодня {today_str}. На скриншоте "вчера". Ответ: {{"status": "success", "analysis_summary": "Проверка даты провалена", "date_check_passed": false, "days_passed": 1, "detected_date_text": "вчера", "reasoning": "Прошел всего 1 день, что не соответствует правилу (>= 3 дня)."}}
        Пример 3: Сегодня {today_str}. На скриншоте "год назад". Ответ: {{"status": "success", "analysis_summary": "Проверка даты провалена", "date_check_passed": false, "days_passed": 365, "detected_date_text": "год назад", "reasoning": "Отзыв слишком старый (более года)."}}
        """
    elif task == 'yandex_profile_check':
        prompt = f"""
        Ты — ассистент-аналитик, проверяющий скриншоты профилей Яндекс. Твоя задача — провести комплексную проверку по двум критериям: имя пользователя и уровень "Знатока города".

        ПРАВИЛА ПРОВЕРКИ:
        1.  **Имя пользователя:**
            - Не должно быть случайным набором букв (например, "fjdovvd", "ывапрол").
            - Не должно содержать матерные или оскорбительные слова.
            - Не должно содержать цифры.
            - Имя или фамилия не должны состоять из одной буквы.
            - Не должно быть написано с использованием арабского, китайского, японского или корейского алфавитов.
        2.  **Уровень "Знаток города":**
            - Уровень должен быть **3 (третий) или выше**.

        ТВОЯ ЗАДАЧА:
        1.  Найди на скриншоте имя пользователя и его уровень "Знатока города".
        2.  Проверь оба параметра на соответствие правилам.
        3.  Сформируй общий вердикт.
        4.  Верни свой ответ СТРОГО в формате JSON.

        ФОРМАТ ОТВЕТА JSON:
        {{
          "status": "success",
          "analysis_summary": "Общий вывод (например, 'Проверка пройдена' или 'Проверка провалена по уровню')",
          "name_check_passed": true/false,
          "level_check_passed": true/false,
          "detected_level": ЧИСЛО_УРОВНЯ_ИЛИ_NULL,
          "reasoning": "Подробное объяснение твоего решения по каждому пункту."
        }}

        Пример 1 (успех): {{"status": "success", "analysis_summary": "Проверка пройдена", "name_check_passed": true, "level_check_passed": true, "detected_level": 5, "reasoning": "Имя 'Елена' корректно. Уровень 5 >= 3."}}
        Пример 2 (провал по уровню): {{"status": "success", "analysis_summary": "Проверка провалена (низкий уровень)", "name_check_passed": true, "level_check_passed": false, "detected_level": 2, "reasoning": "Имя 'Сергей' корректно. Уровень 2 < 3."}}
        Пример 3 (провал по имени): {{"status": "success", "analysis_summary": "Проверка провалена (некорректное имя)", "name_check_passed": false, "level_check_passed": true, "detected_level": 8, "reasoning": "Имя 'qwer123' содержит цифры и похоже на случайный набор. Уровень 8 >= 3."}}
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
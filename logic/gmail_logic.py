# file: logic/gmail_logic.py

import re
import logging
from typing import Tuple, Dict, Optional, Union

logger = logging.getLogger(__name__)

# --- Модуль 5.1: Функция-парсер для данных Gmail ---

def parse_gmail_data(pasted_text: str) -> Tuple[bool, Union[Dict[str, Optional[str]], str]]:
    """
    Принимает текстовый блок, извлекает структурированные данные для Gmail-аккаунта.
    Гибко ищет ключевые слова и извлекает значения, не зависит от порядка строк.

    Args:
        pasted_text: Сырой текстовый блок, вставленный пользователем или администратором.

    Returns:
        Кортеж (is_success, result), где result - словарь с данными или строка с ошибкой.
    """
    patterns = {
        'name': r"Имя:\s*(.+)",
        'surname': r"Фамилия:\s*(.+)",
        'email': r"Email:\s*(.+)",
        'password': r"Пароль:\s*(.+)"
    }
    
    data = {}
    
    # Ищем совпадения для каждого ключа в тексте
    for key, pattern in patterns.items():
        match = re.search(pattern, pasted_text, re.IGNORECASE | re.MULTILINE)
        if match:
            # .strip() убирает лишние пробелы по краям
            data[key] = match.group(1).strip()

    # Проверяем, что все обязательные поля были найдены
    required_fields = ['name', 'email', 'password']
    if not all(field in data for field in required_fields):
        error_message = "Ошибка: Не удалось распознать все обязательные поля (Имя, Email, Пароль) в тексте. Пожалуйста, проверьте скопированный текст и попробуйте снова."
        return False, error_message

    # Обработка и очистка полученных данных
    
    # Фамилия: может отсутствовать
    if 'surname' in data:
        surname_val = data['surname'].lower()
        # Если значение - крестик или слово "нет", считаем фамилию отсутствующей
        if surname_val in ['✖', 'x', 'нет']:
            data['surname'] = None
    else:
        # Если ключ "Фамилия" вообще не был найден в тексте
        data['surname'] = None

    # Email: убираем домен, если он есть
    if '@gmail.com' in data['email']:
        data['email'] = data['email'].replace('@gmail.com', '').strip()

    logger.info(f"Successfully parsed Gmail data: {data}")
    return True, data
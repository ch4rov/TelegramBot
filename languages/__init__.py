import os
import importlib
from services.database_service import get_user_language

# Кэш языков
LANGUAGES = {}
DEFAULT_LANG = 'en'

def load_languages():
    """Загружает все .py файлы из папки languages"""
    global LANGUAGES
    current_dir = os.path.dirname(__file__)
    
    for filename in os.listdir(current_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            lang_code = filename[:-3] # en, ru, pl
            try:
                module = importlib.import_module(f"languages.{lang_code}")
                if hasattr(module, "STRINGS"):
                    LANGUAGES[lang_code] = module.STRINGS
                    print(f"🌐 [LANG] Загружен язык: {lang_code}")
            except Exception as e:
                print(f"❌ [LANG] Ошибка загрузки {filename}: {e}")

async def t(user_id, key, **kwargs):
    """
    Главная функция перевода.
    Возвращает строку на языке пользователя.
    """
    lang_code = await get_user_language(user_id)
    
    # Если язык не загружен или такого ключа нет в языке - берем дефолтный (en)
    if lang_code not in LANGUAGES:
        lang_code = DEFAULT_LANG
    
    strings = LANGUAGES.get(lang_code, {})
    text = strings.get(key)

    # Если ключа нет даже в выбранном языке - пробуем дефолтный
    if not text and lang_code != DEFAULT_LANG:
        text = LANGUAGES.get(DEFAULT_LANG, {}).get(key)
        
    if not text:
        return f"[{key}]" # Заглушка, если перевод потерялся
    
    # Форматирование (вставка переменных)
    if kwargs:
        try:
            return text.format(**kwargs)
        except:
            return text
            
    return text

# Загружаем при импорте
load_languages()
import os
import importlib
from services.database.core import get_user_language

LANGUAGES = {}
DEFAULT_LANG = 'en'

def load_languages():
    global LANGUAGES
    current_dir = os.path.dirname(__file__)
    loaded_codes = []
    
    for filename in os.listdir(current_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            lang_code = filename[:-3]
            try:
                module = importlib.import_module(f"languages.{lang_code}")
                if hasattr(module, "STRINGS"):
                    LANGUAGES[lang_code] = module.STRINGS
                    loaded_codes.append(lang_code)
            except Exception as e:
                print(f"❌ [LANG] Ошибка {filename}: {e}")
    print(f"🌐 [LANG] Загружены языки: {', '.join(loaded_codes)}")

async def t(user_id, key, **kwargs):
    lang_code = await get_user_language(user_id)
    if lang_code not in LANGUAGES: lang_code = DEFAULT_LANG
    strings = LANGUAGES.get(lang_code, {})
    text = strings.get(key)
    if not text and lang_code != DEFAULT_LANG:
        text = LANGUAGES.get(DEFAULT_LANG, {}).get(key)
    if not text: return f"[{key}]"
    if kwargs:
        try: return text.format(**kwargs)
        except: return text
    return text

load_languages()
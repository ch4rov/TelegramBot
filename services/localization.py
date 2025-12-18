# -*- coding: utf-8 -*-
import json
import os
import logging

logger = logging.getLogger(__name__)

class LocalizationService:
    def __init__(self):
        self.locales = {}
        self.load_locales()

    def load_locales(self):
        """Loads all locale files from locales directory"""
        locale_dir = "locales"
        
        if not os.path.exists(locale_dir):
            logger.warning(f"Locales directory not found: {locale_dir}")
            return
        
        for filename in os.listdir(locale_dir):
            if filename.endswith(".json"):
                lang_code = filename.split(".")[0]
                try:
                    with open(os.path.join(locale_dir, filename), "r", encoding="utf-8") as f:
                        self.locales[lang_code] = json.load(f)
                        logger.info(f"Loaded locale: {lang_code}")
                except Exception as e:
                    logger.error(f"Error loading locale {lang_code}: {e}")

    def get(self, key: str, lang: str = "en", **kwargs) -> str:
        """Gets translated string for key"""
        # Try to get from requested language, fallback to en
        lang_data = self.locales.get(lang, self.locales.get("en", {}))
        text = lang_data.get(key, key)
        
        # Format with kwargs if provided
        if kwargs:
            try:
                return text.format(**kwargs)
            except:
                return text
        
        return text

# Create global instance
i18n = LocalizationService()
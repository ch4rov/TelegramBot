# -*- coding: utf-8 -*-
"""
Legacy loader - kept for compatibility but most logic moved to core/loader.py
"""
import logging
from core.loader import bot, dp, on_startup, on_shutdown

logger = logging.getLogger(__name__)
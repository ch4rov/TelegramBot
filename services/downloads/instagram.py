from .base import base_download

async def download(url: str, custom_opts: dict = None):
    opts = {
        # 1. Запрещаем конвертацию в MP4 (Инста и так отдает MP4)
        'skip_conversion': True,
        
        # 2. ВАЖНО: Запрещаем лезть в метаданные файла
        # Это предотвращает поломку соотношения сторон (Squashed video fix)
        'skip_metadata': True,
        
        # 3. Скачиваем "best" (цельный файл), а не "video+audio"
        # Это гарантирует, что мы получим тот файл, который видит телефон
        'format': 'best',
    }
    
    # Если передали кастомные настройки (например, для инлайн-аудио), добавляем их
    if custom_opts:
        opts.update(custom_opts)
        
    return await base_download(url, opts)
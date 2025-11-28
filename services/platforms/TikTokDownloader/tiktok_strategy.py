from services.platforms.common_downloader import CommonDownloader

class TikTokStrategy(CommonDownloader):
    
    def get_platform_settings(self) -> dict:
        return {
            'format': 'best',
            
            # УБРАЛИ HTTP HEADERS (User-Agent)
            # Чтобы yt-dlp использовал куки "как есть", без конфликтов заголовков
            
            'socket_timeout': 20,
            'extractor_timeout': 30,
            'no_warnings': True,
            
            # Обязательно для обхода некоторых проверок
            'nocheckcertificate': True,
            
            'postprocessors': [
                {'key': 'FFmpegMetadata', 'add_metadata': True}
            ]
        }
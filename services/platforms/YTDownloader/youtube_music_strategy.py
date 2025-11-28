from services.platforms.common_downloader import CommonDownloader

class YouTubeMusicStrategy(CommonDownloader):
    """
    Стратегия ТОЛЬКО для YouTube Music (Audio).
    """
    def get_platform_settings(self) -> dict:
        return {
            'format': 'bestaudio/best',
            
            'postprocessors': [
                # 1. Конвертация в MP3
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                # 2. Вшиваем обложку
                {'key': 'EmbedThumbnail'},
                # 3. Метаданные
                {'key': 'FFmpegMetadata', 'add_metadata': True}
            ],
            
            # Обход блокировок (SABR)
            'extractor_args': {
                'youtube': {
                    'player_client': 'default',
                }
            }
        }
from services.platforms.common_downloader import CommonDownloader

class YouTubeVideoStrategy(CommonDownloader):
    """
    Стратегия ТОЛЬКО для YouTube Video (Main/Shorts).
    """
    def get_platform_settings(self) -> dict:
        return {
            # Ограничиваем 1080p, берем MP4
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
            
            # Склейка
            'merge_output_format': 'mp4',
            
            'postprocessors': [
                # Гарантируем MP4 контейнер
                {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'},
                {'key': 'FFmpegMetadata', 'add_metadata': True},
                {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}
            ],
            
            # Обход блокировок
            'extractor_args': {
                'youtube': {
                    'player_client': 'default',
                }
            }
        }
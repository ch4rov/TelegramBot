from services.platforms.common_downloader import CommonDownloader

class YouTubeVideoStrategy(CommonDownloader):
    def get_platform_settings(self) -> dict:
        return {
            # 1. Пытаемся скачать сразу готовый H.264 (avc1)
            'format': 'bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            
            # 2. ЖЕСТКОЕ ПЕРЕКОДИРОВАНИЕ (Если скачалось не то)
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                    # -vcodec libx264: Стандарт для iPhone
                    # -pix_fmt yuv420p: Обязательно для совместимости
                    # -acodec aac: Звук
                    'options': [
                        '-vcodec', 'libx264', 
                        '-pix_fmt', 'yuv420p', 
                        '-acodec', 'aac', 
                        '-movflags', '+faststart'
                    ]
                },
                {'key': 'FFmpegMetadata', 'add_metadata': True},
                {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}
            ],
            'extractor_args': {'youtube': {'player_client': 'default'}}
        }
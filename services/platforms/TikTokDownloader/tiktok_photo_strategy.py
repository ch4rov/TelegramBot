from services.platforms.common_downloader import CommonDownloader

class TikTokPhotoStrategy(CommonDownloader):
    """
    Стратегия для ТикТок Слайдшоу.
    """
    
    # --- РУБИЛЬНИК ---
    IS_ENABLED = False
    # -----------------
    
    def get_platform_settings(self) -> dict:
        # 1. Проверка рубильника
        if not self.IS_ENABLED:
            # Выбрасываем исключение. 
            # CommonDownloader поймает его и вернет как текст ошибки (error).
            raise Exception("ТикТок фото-карусели временно отключены на тех. обслуживание.")

        print(f"📸 [TikTok Photo] Запуск стратегии Android API для: {self.url}")
        
        return {
            'format': 'best',
            
            # Эмуляция Android
            'http_headers': {
                'User-Agent': 'com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_ES; SM-G988N; Build/NRD90M; Cronet/41.0.2272.118)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                    'app_version': '20.2.2',
                    'manifest_app_version': '2022600030',
                }
            },

            'socket_timeout': 30,
            'extractor_timeout': 30,
            'no_warnings': True,
            'nocheckcertificate': True,
            
            'postprocessors': [
                {'key': 'FFmpegMetadata', 'add_metadata': True}
            ]
        }
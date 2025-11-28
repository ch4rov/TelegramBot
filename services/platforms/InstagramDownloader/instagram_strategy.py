from services.platforms.common_downloader import CommonDownloader

class InstagramStrategy(CommonDownloader):
    def get_platform_settings(self) -> dict:
        # Сообщаем CommonDownloader, что конвертировать не надо
        self.configure(skip_conversion=True, skip_metadata=True)

        return {
            'format': 'best',
            # Инстаграм отдает хорошие MP4, не трогаем их
        }
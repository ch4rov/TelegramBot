from services.platforms.common_downloader import CommonDownloader

class SoundCloudStrategy(CommonDownloader):
    def get_platform_settings(self) -> dict:
        return {
            'format': 'bestaudio/best',
            'postprocessors': [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegMetadata', 'add_metadata': True}
            ]
        }
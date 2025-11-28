from services.platforms.common_downloader import CommonDownloader

class YouTubeStrategy(CommonDownloader):
    def get_platform_settings(self) -> dict:
        # Добавляем аргумент для обхода SABR-стриминга
        opts = {
            'extractor_args': {
                'youtube': {
                    'player_client': 'default', # Используем универсальный клиент
                }
            }
        }
        
        is_music = "music.youtube.com" in self.url
        
        if self.options and 'postprocessors' in self.options:
            for pp in self.options['postprocessors']:
                if pp['key'] == 'FFmpegExtractAudio':
                    is_music = True
                    break

        if is_music:
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                    {'key': 'EmbedThumbnail'},
                    {'key': 'FFmpegMetadata', 'add_metadata': True}
                ]
            })
        else:
            opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4'
            })

        return opts

class VKStrategy(CommonDownloader):
    def get_platform_settings(self) -> dict:
        return {
            'format': 'best', 
            'merge_output_format': 'mp4', 
            
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True
                },
                {
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg'
                }
            ]
        }
import aiohttp
import logging

# API Odesli (Song.link)
API_URL = "https://api.song.link/v1-alpha.1/links"

async def get_links_by_url(url: str):
    """
    Отправляет ссылку (Spotify/YouTube/etc) в Odesli
    и возвращает словарь с ссылками на другие платформы.
    """
    params = {
        'url': url,
        'userCountry': 'US' # Можно менять на RU, но US дает больше глобальных ссылок
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=params) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                
                # Разбираем ответ
                links = {}
                links_data = data.get('linksByPlatform', {})
                
                # Какие сервисы нас интересуют
                targets = {
                    'spotify': 'Spotify',
                    'appleMusic': 'Apple Music',
                    'youtube': 'YouTube',
                    'yandex': 'Yandex Music',
                    'soundcloud': 'SoundCloud',
                    'deezer': 'Deezer'
                }

                for key, name in targets.items():
                    if key in links_data:
                        links[name] = links_data[key]['url']
                
                # Основная ссылка на song.link (сводная)
                page_url = data.get('pageUrl')
                
                return {'page': page_url, 'links': links}

    except Exception as e:
        logging.error(f"Odesli API Error: {e}")
        return None
import asyncio
import traceback # Чтобы видеть полный текст ошибки
from youtubesearchpython import VideosSearch

async def search_music(query: str, limit: int = 5):
    """
    Поиск с ГЛУБОКИМ ЛОГИРОВАНИЕМ.
    """
    print(f"\n🔍 [DEBUG] Запрос на поиск: '{query}' | Лимит: {limit}")

    def _sync_search():
        try:
            print(f"   --> [DEBUG] Запускаем VideosSearch('{query}')...")
            search = VideosSearch(query, limit=limit)
            
            print(f"   --> [DEBUG] Выполняем .result()...")
            res = search.result()
            
            # Логируем тип и размер
            if res:
                count = len(res.get('result', []))
                print(f"   --> [DEBUG] Получен ответ. Найдено элементов: {count}")
            else:
                print(f"   --> [DEBUG] Ответ пустой (None или пустой словарь).")
            
            return res
            
        except Exception as e:
            print(f"❌ [DEBUG] ОШИБКА ВНУТРИ _sync_search:")
            print(traceback.format_exc()) # Полный лог ошибки
            return None

    loop = asyncio.get_event_loop()
    
    print(f"🔄 [DEBUG] Передача в executor...")
    raw_data = await loop.run_in_executor(None, _sync_search)
    
    clean_results = []
    
    if raw_data and 'result' in raw_data:
        print(f"⚙️ [DEBUG] Начинаю обработку {len(raw_data['result'])} элементов...")
        
        for i, item in enumerate(raw_data['result']):
            try:
                title = item.get('title', 'Unknown')
                link = item.get('link', None)
                vid_id = item.get('id', None)
                
                print(f"   [{i}] Found: {title} | ID: {vid_id}")
                
                if not link or not vid_id:
                    print(f"   ⚠️ [DEBUG] Пропуск элемента (нет ссылки или ID)")
                    continue

                clean_results.append({
                    'source': 'YT',
                    'id': vid_id,
                    'url': link,
                    'title': title,
                    'duration': item.get('duration') or "Live",
                    'uploader': item['channel']['name']
                })
            except Exception as parse_err:
                print(f"   ⚠️ [DEBUG] Ошибка парсинга элемента {i}: {parse_err}")
    else:
        print(f"⚠️ [DEBUG] 'result' ключ отсутствует в ответе API.")

    print(f"✅ [DEBUG] Итог: возвращаем {len(clean_results)} результатов.\n")
    return clean_results

# Алиас
search_youtube = search_music
# Файл: test_search.py
from youtubesearchpython import VideosSearch
import json

def test():
    query = "Linkin Park Numb"
    print(f"🛠 [TEST] Пробую найти: '{query}'...")

    try:
        # Ищем 1 видео
        search = VideosSearch(query, limit=1)
        result = search.result()
        
        print(f"✅ [TEST] Библиотека отработала без ошибок.")
        print(f"📦 [TEST] Тип данных: {type(result)}")
        
        # Выводим сырой JSON (обрезаем, если огромный)
        result_str = json.dumps(result, indent=2, ensure_ascii=False)
        print(f"📄 [TEST] Ответ:\n{result_str}")

        if result and 'result' in result and len(result['result']) > 0:
            print("🎉 [TEST] УСПЕХ! Видео найдено.")
            print(f"Title: {result['result'][0]['title']}")
            print(f"Link: {result['result'][0]['link']}")
        else:
            print("⚠️ [TEST] Ответ пустой (список 'result' пуст).")

    except Exception as e:
        print(f"❌ [TEST] КРИТИЧЕСКАЯ ОШИБКА БИБЛИОТЕКИ:")
        print(e)

if __name__ == "__main__":
    test()
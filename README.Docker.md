# Как запустить бота в Docker (Windows)

## Что потребуется
- Docker Desktop (с WSL2 backend)
- Ваш готовый файл `.env` (его мы смонтируем внутрь контейнера)

## Шаги "для чайника"
1) Открой PowerShell и перейди в папку проекта (где лежит `main.py` и твой `.env`). Если проекта нет — клонируй:
   ```powershell
   git clone https://github.com/ch4rov/TelegramBot.git
   cd TelegramBot
   ```

2) Проверь, что рядом с `main.py` лежит твой рабочий `.env` (без него контейнер не запустится, core/config.py выйдет с ошибкой).

3) Запусти контейнер:
   ```powershell
   docker compose up -d --build
   ```

4) Посмотреть логи:
   ```powershell
   docker compose logs -f telegrambot
   ```

5) Остановить и удалить контейнер:
   ```powershell
   docker compose down
   ```

## Что делает `docker-compose.yml`
- Собирает образ из `Dockerfile` (Python 3.11, ставит ffmpeg через apt)
- Монтирует твой `.env` в `/app/.env`
- Монтирует папку `./data` на хосте в `/data` внутри контейнера и задаёт `DB_PATH=/data/bot.db` (SQLite сохраняется снаружи)
- Пробрасывает порты 8088/8089 под OAuth callback сервер (Spotify и др.)

## Если нужно перенести существующую базу SQLite
- Положи свой `bot.db` в папку `data` рядом с `docker-compose.yml` до старта
- Убедись, что в `.env` либо пусто про DB, либо стоит `DB_TYPE=sqlite`, `DB_PATH=/data/bot.db`

## Частые вопросы
- **Нужно ли заранее создавать контейнер?** Нет. Команда `docker compose up -d --build` сама собирает образ и запускает контейнер.
- **Где лежит база?** На хосте в `./data/bot.db` (том, примонтированный в контейнер в `/data`).
- **Можно ли запускать без клонирования?** Можно, если у тебя уже есть папка проекта с `.env`. Просто зайди в неё и выполняй шаги 3–5.

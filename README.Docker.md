# Как запустить ch4roBO в Docker (Windows)

## Что это такое
**ch4roBO** — это единая Docker Compose группа из трёх связанных сервисов:
1. **ch4robo-bot** — основной Telegram бот
2. **ch4robo-api** — Telegram Bot API Local Server (для файлов >50MB)
3. **ch4robo-auth** — Cloudflared tunnel (для OAuth callback через публичный URL)

Все три контейнера запускаются вместе одной командой и работают в общей сети `ch4robo-network`.

## Что потребуется
- Docker Desktop (с WSL2 backend)
- Готовый файл `.env` (см. `.env.example`)
- Telegram API credentials: https://my.telegram.org/apps
- Cloudflare Tunnel token: https://one.dash.cloudflare.com/ → Zero Trust → Networks → Tunnels

## Быстрый старт
1) Клонируй проект (если ещё не):
   ```powershell
   git clone https://github.com/ch4rov/TelegramBot.git
   cd TelegramBot
   ```

2) Создай `.env` из примера и заполни обязательные поля:
   ```powershell
   copy .env.example .env
   notepad .env
   ```
   
   Минимум нужно заполнить:
   - `TEST_BOT_TOKEN` или `BOT_TOKEN`
   - `ADMIN_IDS`
   - `TECH_CHAT_ID`
   - `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` (для Local API)
   - `CLOUDFLARED_TUNNEL_TOKEN` (для PROD домена)
   - `PUBLIC_BASE_URL` (например `https://botmenu.ch4rov.pl`)
   - `MINIAPP_PUBLIC_URL` (например `https://botmenu.ch4rov.pl`)
   - Для TEST можно оставить `TEST_PUBLIC_BASE_URL` пустым: в тесте cloudflared поднимет quick tunnel и бот попробует сам взять URL из `/data/cloudflared.log`
   - `TEST_MINIAPP_PUBLIC_URL` (например `https://botmenutesting.ch4rov.pl`) если используешь тестовый поддомен
   - `TEST_SPOTIFY_CLIENT_ID` и `TEST_SPOTIFY_CLIENT_SECRET` (опционально для Spotify)

3) Запусти все три контейнера:
   ```powershell
   docker compose up -d --build
   ```

4) Проверь логи:
   ```powershell
   # Все контейнеры
   docker compose logs -f
   
   # Только бот
   docker compose logs -f telegrambot
   
   # Только Local API
   docker compose logs -f telegram-bot-api
   
   # Только туннель
   docker compose logs -f cloudflared
   ```

5) Остановить группу:
   ```powershell
   docker compose down
   ```

## Обновление на новую версию
```powershell
cd M:\TelegramBot
git pull
docker compose up -d --build --force-recreate
docker compose logs -f --tail=200
```

## Структура
```
ch4robo-network (Docker network)
├── ch4robo-bot        (основной бот, порты 8088/8089)
├── ch4robo-api        (Local API, порт 8081)
└── ch4robo-auth       (Cloudflared tunnel)
```

- Бот обращается к Local API по имени `telegram-bot-api:8081` внутри сети
- Cloudflared пробрасывает порт 8089 (или 8088) наружу через tunnel
- База SQLite хранится в `./data/bot.db` на хосте
- Данные Local API в Docker volume `ch4robo-api-data`

## Частые вопросы
**Q: Нужно ли запускать контейнеры по отдельности?**  
A: Нет. `docker compose up -d` запускает все три сразу. Без Local API бот не сможет отправлять файлы >50MB, без туннеля не будет работать OAuth.

**Q: Как проверить, что Local API работает?**  
A: `docker compose logs telegram-bot-api` — там должна быть строка `Server started`. В боте выстави `USE_LOCAL_SERVER=True` в compose (уже выставлено).

**Q: Cloudflare tunnel не подключается?**  
A: 
- PROD: проверь `CLOUDFLARED_TUNNEL_TOKEN` в `.env` и в Cloudflare Dashboard настрой Public Hostname `botmenu.ch4rov.pl` → Service `http://telegrambot:8088`
- TEST: при `IS_TEST_ENV=True` по умолчанию используется quick tunnel на `ORIGIN_URL` (по умолчанию `http://telegrambot:8089`). Если хочешь тестовый домен `botmenutesting.ch4rov.pl`, создай отдельный Tunnel в Cloudflare и выставь `TEST_PUBLIC_BASE_URL=https://botmenutesting.ch4rov.pl`

Примечание: `telegrambot` — это имя сервиса в `docker-compose.yml` внутри сети Docker. `ch4robo-bot` — `container_name` (алиас), но в документации используем `telegrambot`.

**Q: Где лежат данные?**  
- База бота: `./data/bot.db` (на хосте)
- Данные Local API: Docker volume `ch4robo-api-data`

**Q: Можно ли запустить только бота без Local API?**  
A: Технически да, закомментируй сервисы `telegram-bot-api` и убери `depends_on`, но тогда потеряешь возможность отправки файлов >50MB.

## Отладка
```powershell
# Статус контейнеров
docker compose ps

# Перезапустить один сервис
docker compose restart telegrambot

# Пересобрать только бота
docker compose up -d --build telegrambot

# Удалить всё (включая volumes)
docker compose down -v
```

## Тест без Docker (локально)
Если на тестовой машине нет Docker, quick tunnel контейнером не поднимется. Тогда:

```powershell
# 1) Запусти бота локально (как обычно)
python run.py

# 2) В отдельном окне запусти cloudflared (предварительно скачай cloudflared.exe)
cloudflared tunnel --url http://127.0.0.1:8089
```

Cloudflared напечатает временный URL вида `https://xxxxx.trycloudflare.com` — вставь его в `.env` как `TEST_PUBLIC_BASE_URL`.

# Авторизация Spotify / Yandex

Цель: добавить **персональную авторизацию** для источников, где без входа часть контента недоступна (private/age/captcha/region), и сделать это похоже на текущую идею с Last.fm (персональные привязки на пользователя), но с OAuth-токенами.

## Общие требования

- Привязка **строго per-user**: токены хранятся на `user_id` Telegram.
- Возможность **отвязать** аккаунт (revoke) и удалить токены.
- Авто-обновление access token через refresh token.
- Минимальные права (scopes) и понятный UX.

## Как это выглядит в боте (UX)

Команды/кнопки (предложение):

- `/auth` → список сервисов + статус привязки.
- `Spotify: Подключить` / `Отключить`
- `Yandex: Подключить` / `Отключить`

Флоу подключения:

1) Бот отправляет ссылку на авторизацию (OAuth).
2) Пользователь открывает её в браузере.
3) После авторизации сервис редиректит на ваш `redirect_uri`.
4) Ваш backend принимает `code`, меняет на токены, сохраняет `refresh_token`.
5) Бот пишет пользователю “✅ Подключено”.

Важно: OAuth требует публичный HTTPS callback. В проекте реализован встроенный HTTP callback server (aiohttp) внутри бота + туннель (Cloudflare/ngrok).

## Что уже реализовано в проекте

- Таблицы: `user_oauth_tokens`, `oauth_states`
- `/login` → кнопки Spotify/Yandex: бот генерирует `state` и выдаёт ссылку на авторизацию
- HTTP callback endpoints внутри бота:
  - `/oauth/spotify/callback`
  - `/oauth/yandex/callback`
- После успешного callback бот пишет пользователю “✅ Connected”

Настройки и готовые docker-compose под cloudflared: `docs/api_tokens.md`, `infra/cloudflared/README.md`.

## Хранилище (БД)

Таблица (вариант): `user_oauth_tokens`

- `id`
- `user_id` (Telegram)
- `service` ("spotify" | "yandex")
- `access_token` (текст)
- `refresh_token` (текст)
- `expires_at` (datetime)
- `scope` (текст)
- `created_at`, `updated_at`

Плюс таблица/кэш для одноразовых `state`: `oauth_states`.

## Spotify

### Текущий flow

- OAuth 2.0 Authorization Code.
- `redirect_uri` = `${PUBLIC_BASE_URL}/oauth/spotify/callback` (или `TEST_PUBLIC_BASE_URL` в тесте).

### Scopes (минимально)

Зависит от того, что вы хотите делать:

- Если нужно **только читать публичные данные** и использовать как “доступ к CDN” — чаще всего это не работает напрямую.
- Если нужно читать библиотеку/плейлисты пользователя:
  - `playlist-read-private`
  - `user-library-read`

### Refresh

- Access token живёт недолго → при каждом запросе проверять `expires_at`.
- Если истёк — обновить по refresh token.

## Yandex

### Flow

- OAuth Authorization Code (стандартный Яндекс OAuth).
- Также требует `redirect_uri`.

### Ограничения

- Для **music.yandex.ru** даже с токеном могут быть ограничения (регион/подписка/капча).
- Практически полезно использовать токен для снижения “капча/блок” в запросах к метаданным.

## Где использовать токены в текущем коде

Идея интеграции (без кода):

- В `services/platforms/platform_manager.py` перед скачиванием:
  - если источник “Spotify/Yandex Music” и есть токен пользователя →
    - использовать токен для получения прямых ссылок/метаданных (если есть API) или для более надёжного резолва.
  - если токена нет → текущий fallback (Odesli → YouTube).

## Безопасность

- Не логировать токены.
- Желательно шифровать токены на диске (хотя бы через env secret).
- `state` обязательно, чтобы связать callback браузера с Telegram user.

## Примечание

Бот может работать в polling как сейчас; отдельный backend не требуется.

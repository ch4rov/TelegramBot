# Где создать API токены (Spotify)

Ниже — минимальный список “что где нажать”, чтобы получить `client_id` (и `client_secret` где нужно).

## Spotify

1) Открой Spotify Developer Dashboard:
- https://developer.spotify.com/dashboard

2) Создай приложение (Create app)
- Name: любое
- Description: любое

3) В настройках приложения (Settings) найди:
- **Client ID** (нужен)
- **Client Secret** (для классического Authorization Code flow; для PKCE может не понадобиться, но лучше иметь)

4) Добавь Redirect URI
- В Settings → Redirect URIs добавь URL, на который будет возвращаться браузер после логина.
- Важно: redirect URI должен **в точности** совпадать с тем, что использует бот.

Пример (если используешь туннель):
- `https://YOUR_PUBLIC_HOST/oauth/spotify/callback`

Если бот запущен в тестовом режиме (`IS_TEST_ENV=True`), бот берёт base URL из `TEST_PUBLIC_BASE_URL`.
Если в проде (`IS_TEST_ENV=False`) — из `PUBLIC_BASE_URL`.

## Yandex Music (только ссылки)

OAuth Яндекса в проекте не используется.
Ссылки Яндекс.Музыки обрабатываются как обычные ссылки: best-effort метаданные + скачивание через Odesli → YouTube/SoundCloud.

## Важно про публичный callback URL (без отдельного сервера)

OAuth почти всегда требует публичный HTTPS callback.
Чтобы не поднимать отдельный backend-проект, можно:

- Запустить мини-веб-сервер **внутри бота** на `127.0.0.1:PORT`
- Пробросить наружу через **Cloudflare Tunnel** или **ngrok**

Тогда redirect URI будет указывать на домен туннеля.

### Про порты (test vs stable)

- Внутренний HTTP сервер OAuth слушает `OAUTH_HTTP_HOST` и порт:
	- `TEST_OAUTH_HTTP_PORT` в тестовом режиме
	- `OAUTH_HTTP_PORT` в прод режиме
- Туннель должен проксировать именно на этот `host:port`.

Готовые docker-compose под cloudflared лежат в `infra/cloudflared/README.md`.

(Я могу доделать встроенный OAuth callback сервер в проекте, но нужны значения client_id/secret и понятный PUBLIC_BASE_URL.)

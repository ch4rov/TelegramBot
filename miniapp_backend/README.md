# Mini App backend

## Локальный запуск
```powershell
cd M:\TelegramBot
python -m pip install -r requirements.txt

# Backend
python -m miniapp_backend.run_miniapp
```

По умолчанию слушает `0.0.0.0:8090`.

## Тест в локальной сети (LAN)
Telegram Mini App требует HTTPS. Самый простой способ без Docker — quick tunnel.

1) Запусти backend, чтобы он слушал на LAN IP:
```powershell
$env:MINIAPP_BACKEND_HOST="0.0.0.0"
$env:MINIAPP_BACKEND_PORT="8090"
python -m miniapp_backend.run_miniapp
```

2) Запусти cloudflared на этой же машине:
```powershell
cloudflared tunnel --url http://127.0.0.1:8090
```

3) Скопируй выданный URL `https://xxxxx.trycloudflare.com` и поставь его в `.env`:
- `TEST_PUBLIC_BASE_URL=https://xxxxx.trycloudflare.com`
- `TEST_MINIAPP_PUBLIC_URL=https://xxxxx.trycloudflare.com`

## Проверка initData
В браузере без Telegram initData не будет валидным.

В Telegram открой WebApp и убедись, что запрос к:
- `/api/admin/me`

возвращает `{"is_admin": true}`.

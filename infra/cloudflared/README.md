# Cloudflare Tunnel (Docker) for OAuth callbacks

## Quick tunnel (trycloudflare.com) — good for testing

On Windows (PowerShell), from repo root:

```powershell
$env:ORIGIN_URL = "http://host.docker.internal:8089"
docker compose -f .\infra\cloudflared\docker-compose.quick.yml up
```

- In the logs you will see a URL like `https://xxxx.trycloudflare.com`.
- Put it into `.env`:
  - `TEST_PUBLIC_BASE_URL=https://xxxx.trycloudflare.com`
- Your provider redirect URIs must be:
  - `https://xxxx.trycloudflare.com/oauth/spotify/callback`

## Named tunnel (stable / production)


This requires a Cloudflare account and a Tunnel token.

### Step-by-step: Production Tunnel via Cloudflare Zero Trust

1. **Create a Cloudflare account** (if you don't have one):
  - https://dash.cloudflare.com/

2. **Add your domain** (if not already added) and complete DNS setup.

3. **Go to Zero Trust dashboard:**
  - https://one.dash.cloudflare.com/
  - Left menu: Access → Tunnels

4. **Create a new Tunnel:**
  - Click "Create a tunnel"
  - Name it (e.g. `telegrambot-prod`)
  - Click "Save tunnel"

5. **Install cloudflared (skip, you use Docker)**

6. **Copy the Tunnel Token:**
  - After creating, click the tunnel → "Connect" tab → "Docker" → copy the long `--token ...` string

7. **Set up docker-compose:**
  - In PowerShell:
    ```powershell
    $env:CLOUDFLARED_TUNNEL_TOKEN = "PASTE_TOKEN_HERE"
    docker compose -f .\infra\cloudflared\docker-compose.named.yml up -d
    ```

8. **Configure public hostname:**
  - In the tunnel page, go to "Public Hostname" tab
  - Add a hostname (e.g. `bot.yourdomain.com`)
  - Service type: `http`
  - URL: `http://host.docker.internal:8088` (or your chosen port)
  - Save

  If you want **stable PROD + stable TEST** on the same domain (example: `ch4rov.pl`):
  - `bot.ch4rov.pl` → `http://host.docker.internal:8088` (prod, matches `OAUTH_HTTP_PORT`)
  - `test-bot.ch4rov.pl` → `http://host.docker.internal:8089` (test, matches `TEST_OAUTH_HTTP_PORT`)

9. **Update your `.env`:**
  - `PUBLIC_BASE_URL=https://bot.yourdomain.com`
  - (optional) `TEST_PUBLIC_BASE_URL=https://test-bot.yourdomain.com`

10. **Set redirect URIs in Spotify app:**
  - `https://bot.yourdomain.com/oauth/spotify/callback`
  - (optional test) `https://test-bot.yourdomain.com/oauth/spotify/callback`

11. **Restart bot and tunnel if needed.**

---

**Notes:**
- For test mode, use quick tunnel as above.
- For production, always use your own domain and named tunnel for reliability.

# Deploy videoGirl to Coolify

This guide covers deploying the videoGirl Telegram bot on a [Coolify](https://coolify.io) instance.

## What Coolify will run

- The Python bot worker (`Dockerfile`)
- PostgreSQL with `pgvector` extension
- Redis

The bot uses Telegram long-polling, so **no public HTTP port or domain is required**. Coolify's health check uses the `HEALTHCHECK` command defined in the `Dockerfile`.

## Prerequisites

1. A Coolify instance (self-hosted or managed) with Docker available.
2. A Git repository containing this project.
3. A Telegram bot token from [@BotFather](https://t.me/BotFather).
4. A reachable LLM/Ollama endpoint (e.g. a GPU box at home or a cloud host).
5. Environment values filled in; **do not wrap values in quotes**.

## 1. Prepare environment variables

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

Critical variables:

| Variable | Example | Notes |
|---|---|---|
| `telegram_token` | `123456:ABC-DEF...` | Required |
| `postgres_url` | `postgresql://videogirl:videogirl@postgres:5432/videogirl` | Use Coolify-managed DB hostname if you create one |
| `redis_url` | `redis://redis:6379/0` | Use Coolify-managed Redis hostname if you create one |
| `ollama_base_url` | `http://192.168.1.100:11434` | Must be reachable from the Coolify server |
| `comfyui_base_url` | `http://ai.bygpu.com:8188` | Optional image/video pipeline |
| `breezyvoice_base_url` / `BREEZYVOICE_URL` | `https://breezyvoice.momooai.com` | Optional GPU TTS; both names are accepted |
| `model_name` | `hf.co/...:Q6_K` | Ollama model tag |
| `llm_profile` | `mac-qwen9b` | Choose a profile from `shared/llm.py` |

> **Important:** Do **not** add quotes around values. Docker `--env-file` and Coolify treat quotes as part of the value, which breaks URLs like `postgresql://...`.

## 2. Add the project to Coolify

1. Log in to your Coolify dashboard.
2. Click **Create New Resource**.
3. Choose **Application** (or **Docker Compose** if you prefer `docker-compose.prod.yml`).
4. Select your Git source and repository.
5. Choose the branch to deploy.

### Option A: Deploy from Dockerfile (recommended for Coolify)

- Build Pack: **Dockerfile**
- Dockerfile path: `Dockerfile`
- Base Directory: `/`
- No port or domain needed. Set the service type to **worker / non-web** if Coolify asks.

### Option B: Deploy from Docker Compose

- Build Pack: **Docker Compose**
- Docker Compose file: `docker-compose.prod.yml`
- Coolify will create `postgres` and `redis` services alongside the bot.

## 3. Configure environment in Coolify

1. Open the resource **Environment** tab.
2. Paste the contents of your `.env` file.
3. Adjust database/cache URLs if you are using Coolify-managed resources instead of the compose-managed ones.
4. Save.

If you use the compose-managed Postgres/Redis, keep:

```text
postgres_url=postgresql://videogirl:videogirl@postgres:5432/videogirl
redis_url=redis://redis:6379/0
```

If you create Coolify-managed databases, Coolify will expose hostnames such as `postgres-xxx` or `redis-xxx` — update the URLs accordingly.

## 4. Set health check

The `Dockerfile` already includes:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run --python python3.11 python -m shared.health || exit 1
```

You can override it in Coolify if desired. The command checks PostgreSQL and Redis connectivity.

## 5. Deploy

1. Click **Deploy**.
2. Watch the build logs. The first build downloads dependencies and installs `ffmpeg`, so it can take a few minutes.
3. After the container starts, check the **Logs** tab for bot startup messages.
4. Send `/start` to your bot on Telegram to verify it responds.

## 6. Updates

Push code changes to the same branch; Coolify can auto-deploy if webhooks are configured, or you can click **Redeploy** manually.

## Local verification before pushing

You can verify the production image locally (assuming Colima/Docker is running):

```bash
# 1. Build
docker build -t videogirl:test .

# 2. Start Postgres + Redis (dev compose is fine for this test)
docker compose -f docker-compose.dev.yml up -d

# 3. Run health check inside the image
docker run --rm --env-file .env --network host videogirl:test \
  uv run --python python3.11 python -m shared.health

# 4. Run the bot briefly to confirm it connects to Telegram
#    (Stop with Ctrl-C once you see "Bot started")
docker run --rm --env-file .env --network host videogirl:test
```

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `postgresql://...` DSN parse error | Values in Coolify env have quotes. Remove them. |
| `Connection refused` to Ollama/ComfyUI | The Coolify server cannot reach your GPU box. Use a public or VPN-routable address. |
| `telegram_token` missing | The env variable was not saved in Coolify before deploy. |
| Container exits immediately | Check logs; likely database not ready or token invalid. |
| `.venv` rebuild warning inside container | Make sure `.dockerignore` excludes `.venv/`; it does in this repo. |

## Files involved

- `Dockerfile` — production image
- `.dockerignore` — excludes local venv and env files
- `docker-compose.prod.yml` — full production stack
- `.env.example` — environment template
- `shared/health.py` — health check logic

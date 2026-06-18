# Coolify 部署說明

本專案設計為部署在自架的 **Coolify**（家用 Linux）上，LLM 與媒體生成分別跑在 Mac mini 與 4090 機器上。此處只說明 Coolify 端需要的基礎設施與環境變數。

## 1. 建立資料庫服務

在 Coolify 中新增 **PostgreSQL** 服務：

- 使用 image：`pgvector/pgvector:pg16`
- 建議開一個資料庫，例如 `videogirl`
- 記錄下連線字串，例如：
  `postgresql://user:password@postgres:5432/videogirl`

> 本專案的 migrations 會在啟動時啟用 `vector` 擴充功能，請務必使用 pgvector image。

## 2. 建立 Redis 服務

在 Coolify 中新增 **Redis** 服務：

- 使用官方 image：`redis:7-alpine`
- 記錄下連線字串，例如：
  `redis://redis:6379/0`

## 3. 新增應用程式服務

1. 在 Coolify 新增一個 **Application**。
2. 來源選擇此 Git repo。
3. Build type 選 **Dockerfile**（使用本目錄的 `Dockerfile`）。
4. 在 Environment Variables 中設定以下變數（值請替換為實際內容）：

| 變數名 | 說明 | 範例 |
|---|---|---|
| `telegram_token` | Telegram Bot Token | `123456:ABC-DEF...` |
| `postgres_url` | PostgreSQL 連線字串 | `postgresql://user:pass@postgres:5432/videogirl` |
| `redis_url` | Redis 連線字串 | `redis://redis:6379/0` |
| `ollama_base_url` | Mac mini 上的 Ollama LAN IP | `http://192.168.1.100:11434` |
| `comfyui_base_url` | 4090 上的 ComfyUI（透過 Tailscale） | `http://ai.bygpu.com:8188` |
| `breezyvoice_base_url` | 4090 上的 BreezyVoice TTS | `http://ai.bygpu.com:8080` |
| `embedding_model` | CPU 使用的 embedding 模型 | `BAAI/bge-m3` |
| `model_name` | 預設 LLM 名稱 | `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` |
| `log_level` | 日誌等級 | `INFO` |

5. Healthcheck 可保留 Dockerfile 內建的 `python -m shared.health`，Coolify 會使用 exit code 判斷健康狀態。

## 4. 啟動

應用程式啟動後會執行 `python -m bot`，目前只會印出 `bot scaffold ready`。後續任務會逐步實作真正的 bot 邏輯。

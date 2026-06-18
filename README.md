> ⚠️ 本專案仍處於早期開發階段，目前僅完成任務 #1 的專案骨架與基礎設施。

# videoGirl

Telegram 繁體中文 NSFW AI 女友服務。本任務建立可部署至 Coolify 的 Python 骨架，為後續 bot、記憶、人設、媒體生成等功能打好地基。

## 技術棧

- Python 3.11 + asyncio
- aiogram 3.x（Telegram long polling）
- pydantic-settings（環境變數管理）
- structlog（結構化 JSON 日誌）
- asyncpg + PostgreSQL + pgvector
- redis（async）
- alembic（資料庫遷移）
- pytest + pytest-asyncio

## 開發環境準備

### 1. 安裝 uv

參考官方文件：<https://docs.astral.sh/uv/getting-started/installation/>

macOS（Homebrew）：

```bash
brew install uv
```

### 2. 安裝依賴

```bash
uv sync --python python3.11
```

### 3. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入實際值（開發時可保留 docker-compose.dev.yml 的預設 DB/Redis）
```

## 啟動開發服務

使用 docker-compose.dev.yml 在本機啟動 PostgreSQL（含 pgvector）與 Redis：

```bash
docker-compose -f docker-compose.dev.yml up -d
```

套用資料庫 migration：

```bash
uv run --python python3.11 alembic upgrade head
```

## 執行健康檢查

```bash
uv run --python python3.11 python -m shared.health
```

成功時會印出 JSON `{status: ok}` 並以 exit code 0 結束；失敗則 exit 1。

## 跑測試

```bash
uv run --python python3.11 pytest
```

測試內容包含：

- 能否連線 Postgres 並確認 pgvector 已啟用
- 能否 ping Redis
- pydantic-settings 在缺少必填欄位時會拋出 ValidationError

## 執行 bot 佔位程式

目前 bot 僅會印出 `bot scaffold ready`：

```bash
uv run --python python3.11 python -m bot
```

## 部署到 Coolify

請參考 [`infra/README.md`](infra/README.md)，其中說明：

- 如何在 Coolify 新增 PostgreSQL（pgvector）與 Redis 服務
- 需要設定哪些環境變數
- Dockerfile 與 healthcheck 設定

## 專案結構

```
.
├── bot/              # Telegram bot（目前為佔位）
├── orchestrator/     # 對話編排邏輯（後續任務）
├── workers/          # 背景工作與 GPU 佇列（後續任務）
├── shared/           # config、logging、db、redis、health
├── infra/            # 部署文件
├── migrations/       # Alembic 遷移
├── tests/            # pytest 測試
├── Dockerfile
├── docker-compose.dev.yml
└── pyproject.toml
```

## 注意事項

- `.env` 已列入 `.gitignore`，請勿將機密提交至 git。
- 本任務不實作 bot 對話、人設、記憶等業務邏輯，那些屬於後續任務。

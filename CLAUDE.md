# videoGirl — project guide for the coding agent

Telegram **NSFW Traditional-Chinese (zh-TW)** AI girlfriend service. Differentiator: companionship **+ proactive push + reminders/notes** (assistant-hybrid). Full spec: `.taskmaster/docs/prd.txt`.

## How to work
- Tasks are managed by **Task Master**. Before coding, run `task-master next`, then `task-master show <id>` for details. Mark progress: `task-master set-status --id=<id> --status=in-progress|done`.
- Implement **one task at a time**, in dependency order. Commit after each task with a clear message.
- Keep ALL source code in this repo (git). Do not depend on files living only on the GPU box.

## Architecture (distributed, home-hosted)
- **App tier on Coolify** (home Linux box): bot, orchestrator, scheduler, queue worker, **PostgreSQL+pgvector**, **Redis**, and CPU embeddings. Coolify runs Docker for you (Nixpacks/Dockerfile) — do NOT hand-maintain docker-compose for prod (a dev compose is optional).
- **Bot**: Python 3.11+ asyncio, **aiogram 3.x**, **long polling** (no webhook — host is behind home NAT). Telegram, adult opt-in + 18+ age gate.
- **LLM on the Mac mini M4 (16GB, headless, same LAN)** via **Ollama**: uncensored zh-TW model, start Qwen2.5-8B abliterated (or 14B Q4 with ctx ~4k). Reached by LAN IP. Embeddings run on Coolify CPU, NOT the Mac.
- **Media on the rented 4090 (via Tailscale)**: ComfyUI (NSFW images + per-persona LoRA); image-to-video (Wan2.2/Hunyuan). **GPU media queue** (Redis + Celery/RQ) serializes 4090 work, priority **photo > video**, VRAM-aware load/unload. The LLM is NOT in this queue.
- **Voice**: **BreezyVoice** TTS (zh-TW) on the 4090 (or Mac if light).
- **Proactive engine**: APScheduler (good-morning/night, reminders, notes).
- **Companion soul (first priority, tasks #5/#12/#13/#32/#33/#26)**: user dossier memory (remembers your personality + life facts), life-assistant reminders (tax/electricity, recurring, in-voice), special-dates + proactive gift image (#33), routine-aware care check-ins ("你在做什麼?"), an internal **mood model** (#32) that shifts with interaction and colors tone, and multiple/custom personas (#26).
- **Monetization = Telegram Stars only** (XTR): payments core/wallet/VIP subscription/unlocks/gifts/referral funnel/gacha (#19–#26). **Mini App** (#27–#30) needs public HTTPS via **Cloudflare Tunnel** from the Coolify box (bot stays long-polling); validate Mini App `initData` via HMAC. Keep ALL public surfaces SFW; Stars payouts via Fragment (min 1,000, 21-day hold) and can be frozen — see #31.

## Hardware
- **Coolify Linux box (home)** = persistent app + DB tier. **Mac mini (home LAN)** = persistent LLM. **RTX 4090 (ssh ai.bygpu.com, Tailscale)** = **disposable** GPU, wiped on rental expiry — run ONLY ComfyUI/video/voice there; never store the only copy of code there.
- Tasks needing the 4090: #9 (maybe), #10, #11, #14, #15. LLM (#3) runs on the Mac mini. Everything else runs on Coolify/CPU.

## Conventions
- Output to users is **zh-TW (Traditional Chinese)**, never Simplified.
- Adult content is **opt-in only**; default SFW; always refuse illegal content (see task #17).
- Secrets live in `.env` (gitignored). Never commit keys.
- Match existing code style; write tests per each task's `testStrategy`.

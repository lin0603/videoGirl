# 4090 ComfyUI 媒體生成（NSFW 文生圖 / 圖生圖 / 圖生影片 / 影片換人）

把分散在 mentorAI 的 ComfyUI 工作流集中、版本控管在這裡,目的:**換 4090 機器很方便、能力一目了然**。

## 內容
- `workflows/` — 各能力的 ComfyUI **API-format** 工作流(t2i / i2i / i2v / talking / avatar)。
- `CATALOG.md` — 能力 → 工作流 → 模型 → VRAM → 穩定度(先看這個)。
- `models.manifest.json` — 需要的模型檔(依 ComfyUI 子目錄分類)+ 自訂節點清單。
- `provision-4090.sh` — 換機器時一鍵設置(裝 ComfyUI + 自訂節點 + 拉模型 + 起服務)。

## 換機器流程(摘要)
1. 租新 4090,拿到 SSH port。
2. `NEW_PORT=<port> MODELS_SRC=<舊機或備份的 ComfyUI/models> ./provision-4090.sh`
   - 模型很大(Wan 14B / LTX 22B 共數十 GB)→ **優先 rsync 舊機或 `/home/bygpu/public_disk`,別重下載**。
   - 本地 `TaiwanDollLikeness.safetensors` 用 scp 上傳到 `models/loras/`。
3. 在 Coolify 主機把隧道指到新 SSH port(同 BreezyVoice 的 autossh systemd 模式),
   設 `comfyui_base_url=http://192.168.0.140:8188` → 重新部署。

## app 怎麼用(videoGirl 後續任務)
videoGirl 的媒體任務(#8 佇列 / #10 照片 / #14 影片 / #11 LoRA)會:
- 載入 `workflows/<能力>/<檔>.json`,
- 用程式填入 prompt / 來源圖 / 種子等參數,
- POST 到 ComfyUI `comfyui_base_url`(經隧道到 4090:8188)`/prompt`,輪詢 `/history` 取結果。

> 連線一律走 Tailscale / autossh 隧道,4090 服務只綁 `127.0.0.1`(不對外)。
> 公開面維持 SFW;NSFW 僅在 18+ opt-in 後。

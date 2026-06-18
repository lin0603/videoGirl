#!/usr/bin/env bash
# Provision a fresh rented 4090 (bygpu) for videoGirl media generation.
# Goal: switching machines = run this once. ComfyUI + custom nodes + models +
# the workflow JSONs (from this repo), then expose ComfyUI to the app.
#
# Usage (on your Mac, with SSH access to the new box):
#   NEW_HOST=ai.bygpu.com NEW_PORT=<ssh-port> ./provision-4090.sh
# or run the steps manually on the box. Review before running — it installs software.
set -euo pipefail

# ---- config ----
NEW_HOST="${NEW_HOST:-ai.bygpu.com}"
NEW_PORT="${NEW_PORT:?set NEW_PORT to the new rental's SSH port}"
NEW_USER="${NEW_USER:-bygpu}"
COMFY_DIR="${COMFY_DIR:-/home/bygpu/mentorai-comfyui-official/ComfyUI}"
# Where to pull big models FROM. Best options, in order:
#   1) the OLD 4090 (still alive) — set MODELS_SRC=user@oldhost:port:/path/to/ComfyUI/models
#   2) the persistent shared disk /home/bygpu/public_disk/software/...
#   3) re-download per models.manifest.json
MODELS_SRC="${MODELS_SRC:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"

ssh_box() { ssh -o StrictHostKeyChecking=no -p "$NEW_PORT" "$NEW_USER@$NEW_HOST" "$@"; }

echo "==> 1. Install ComfyUI + venv (bygpu has a prebuilt pytorch env; reuse it)"
ssh_box bash -s <<'REMOTE'
set -e
test -d ~/mentorai-comfyui-official/ComfyUI || {
  mkdir -p ~/mentorai-comfyui-official && cd ~/mentorai-comfyui-official
  git clone https://github.com/comfyanonymous/ComfyUI
}
# reuse bygpu's shared pytorch env if present, else create one
source /home/bygpu/anaconda3/etc/profile.d/conda.sh 2>/dev/null || true
conda activate py310-torch250-cuda124 2>/dev/null || true
cd ~/mentorai-comfyui-official/ComfyUI && pip install -r requirements.txt
REMOTE

echo "==> 2. Install custom nodes"
ssh_box bash -s <<'REMOTE'
set -e
cd ~/mentorai-comfyui-official/ComfyUI/custom_nodes
for repo in \
  https://github.com/city96/ComfyUI-GGUF \
  https://github.com/rgthree/rgthree-comfy \
  https://github.com/Lightricks/ComfyUI-LTXVideo \
  https://github.com/Fannovel16/comfyui_controlnet_aux ; do
  d=$(basename "$repo"); [ -d "$d" ] || git clone "$repo"
  [ -f "$d/requirements.txt" ] && pip install -r "$d/requirements.txt" || true
done
REMOTE

echo "==> 3. Create model dirs"
ssh_box "mkdir -p $COMFY_DIR/models/{diffusion_models,vae,text_encoders,controlnet,loras,upscale_models,audio}"

echo "==> 4. Acquire models"
if [ -n "$MODELS_SRC" ]; then
  echo "    rsync from $MODELS_SRC (fast: avoids re-download)"
  ssh_box "rsync -av --progress -e 'ssh -p ${MODELS_SRC%%:*:*}' '${MODELS_SRC#*:}/' $COMFY_DIR/models/ || true"
  echo "    (verify the rsync line for your host:port:path format; adjust as needed)"
else
  echo "    !! MODELS_SRC not set. Either:"
  echo "       - set MODELS_SRC to the old box's ComfyUI/models and re-run, or"
  echo "       - symlink from /home/bygpu/public_disk/software/* if models persist there, or"
  echo "       - download each file in models.manifest.json into the matching subdir."
fi
echo "    Upload the local LoRA:"
echo "      scp -P $NEW_PORT '/Volumes/External Disk/TaiwanDollLikeness.safetensors' $NEW_USER@$NEW_HOST:$COMFY_DIR/models/loras/taiwanDollLikeness_v20.safetensors"

echo "==> 5. Workflows live in this repo (infra/comfyui/workflows). The app loads them"
echo "    via the ComfyUI HTTP API; no need to copy onto the box."

echo "==> 6. Start ComfyUI on 127.0.0.1:8188"
ssh_box "cd ~/mentorai-comfyui-official/ComfyUI && nohup python main.py --listen 127.0.0.1 --port 8188 >/tmp/comfyui.log 2>&1 & sleep 3; curl -s -m5 http://127.0.0.1:8188/system_stats | head -c 80 || echo 'check /tmp/comfyui.log'"

echo "==> 7. Deploy media worker (task #8)"
# Rsync the workers/ package and workflow JSONs onto the box
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
ssh_box "mkdir -p ~/videogirl-worker/infra/comfyui/workflows"
rsync -av --progress -e "ssh -o StrictHostKeyChecking=no -p $NEW_PORT" \
  "$REPO_ROOT/workers/" "$NEW_USER@$NEW_HOST:~/videogirl-worker/workers/"
rsync -av --progress -e "ssh -o StrictHostKeyChecking=no -p $NEW_PORT" \
  "$REPO_ROOT/infra/comfyui/workflows/" "$NEW_USER@$NEW_HOST:~/videogirl-worker/infra/comfyui/workflows/"

# Install httpx + redis on the box
ssh_box "pip install 'httpx>=0.27' 'redis>=5.0' || pip install --user 'httpx>=0.27' 'redis>=5.0'"

# Write systemd unit (requires REDIS_URL, CALLBACK_SECRET to be set in the env file)
ssh_box bash -s <<'REMOTE'
set -e
cat > /tmp/videogirl-worker.service <<'UNIT'
[Unit]
Description=videoGirl GPU media worker
After=network.target

[Service]
Type=simple
User=bygpu
WorkingDirectory=/home/bygpu/videogirl-worker
EnvironmentFile=/home/bygpu/videogirl-worker/.env
ExecStart=/home/bygpu/anaconda3/bin/python -m workers.worker
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
sudo mv /tmp/videogirl-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
echo "[provision] worker service installed. Set env vars in ~/videogirl-worker/.env, then:"
echo "  sudo systemctl enable --now videogirl-worker"
REMOTE

cat <<'ENVTEMPLATE'
  ── Create ~/videogirl-worker/.env on the box:
     REDIS_URL=redis://<coolify-tailscale-ip>:6379
     COMFYUI_BASE_URL=http://127.0.0.1:8188
     CALLBACK_SECRET=<same as MEDIA_CALLBACK_SECRET on Coolify>
ENVTEMPLATE

cat <<EOF

==> 8. Connect the app to this box (same pattern as BreezyVoice):
   On the Coolify host, point the autossh tunnel at the NEW SSH port:
     sudo systemctl edit/replace breezyvoice-tunnel  (or add a comfyui-tunnel)
     forward 0.0.0.0:8188 -> 127.0.0.1:8188 via -p $NEW_PORT $NEW_USER@$NEW_HOST
   Then set Coolify env comfyui_base_url=http://192.168.0.140:8188 and redeploy.
   Also set: MEDIA_CALLBACK_URL=http://<coolify-tailscale-ip>:3000/internal/media_done
             MEDIA_CALLBACK_SECRET=<strong-random-secret>

Done. Verify capabilities with the JSONs in infra/comfyui/workflows/ (see CATALOG.md).
EOF

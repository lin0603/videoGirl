"""
GPU media worker entrypoint — runs on the 4090.

Consumes jobs from Redis priority queues (photo > video),
executes ComfyUI, and POSTs results to the callback URL on Coolify.

Usage on the 4090:
    REDIS_URL=redis://<coolify-tailscale-ip>:6379 \\
    COMFYUI_BASE_URL=http://127.0.0.1:8188 \\
    CALLBACK_SECRET=<shared-secret> \\
    python -m workers.worker

Environment variables:
    REDIS_URL             Redis on Coolify, reachable via Tailscale (required)
    COMFYUI_BASE_URL      ComfyUI on this machine (default: http://127.0.0.1:8188)
    CALLBACK_SECRET       Shared secret for /internal/media_done auth (required)
    MAX_RETRIES           Max retries before dead-letter (default: 3)
    BLPOP_TIMEOUT         Seconds to block on empty queues (default: 30)
"""
from __future__ import annotations

import json
import os
import signal
import sys

import redis as sync_redis

from workers.media_tasks import execute_job

QUEUES = ["media:photo", "media:video"]


def main() -> None:
    redis_url = os.environ["REDIS_URL"]
    comfyui_url = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    callback_secret = os.environ.get("CALLBACK_SECRET", "")
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))
    blpop_timeout = int(os.environ.get("BLPOP_TIMEOUT", "30"))

    r = sync_redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=blpop_timeout + 15,
        socket_keepalive=True,
        health_check_interval=30,
    )
    r.ping()
    print(f"[worker] connected redis={redis_url} comfyui={comfyui_url}", flush=True)

    shutdown = False

    def _on_signal(sig, _frame):
        nonlocal shutdown
        print(f"[worker] received signal {sig}, stopping after current job", flush=True)
        shutdown = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    while not shutdown:
        try:
            result = r.blpop(QUEUES, timeout=blpop_timeout)
        except sync_redis.exceptions.TimeoutError:
            continue  # 空佇列的 socket read timeout，視同無工作續迴圈
        except sync_redis.exceptions.ConnectionError as exc:
            print(f"[worker] redis connection error: {exc}, retrying", flush=True)
            import time
            time.sleep(2)
            continue
        if result is None:
            continue

        _, job_id = result
        raw = r.get(f"mediajob:{job_id}")
        if raw is None:
            print(f"[worker] job {job_id} not found in Redis, skipping", flush=True)
            continue

        job_data = json.loads(raw)
        print(
            f"[worker] start job_id={job_id} type={job_data.get('job_type')} "
            f"workflow={job_data.get('workflow')} retry={job_data.get('retry_count', 0)}",
            flush=True,
        )
        try:
            execute_job(
                job_data,
                comfyui_base_url=comfyui_url,
                redis_client=r,
                callback_secret=callback_secret,
                max_retries=max_retries,
            )
            print(f"[worker] done job_id={job_id}", flush=True)
        except Exception as exc:
            print(f"[worker] error job_id={job_id}: {exc}", flush=True)

    print("[worker] stopped", flush=True)


if __name__ == "__main__":
    main()

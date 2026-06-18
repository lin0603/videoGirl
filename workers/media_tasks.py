"""
Media job execution logic — runs inside the 4090 worker process.
Called by worker.py for each dequeued job.
"""
from __future__ import annotations

import json
import uuid

import httpx
import redis as sync_redis

from workers.comfyui_runner import (
    ComfyUIError,
    apply_params,
    download_output,
    load_workflow,
    submit_prompt,
    upload_image,
    wait_for_completion,
)


def _update_redis(r: sync_redis.Redis, job_id: str, **fields) -> None:
    key = f"mediajob:{job_id}"
    raw = r.get(key)
    if raw is None:
        return
    data = json.loads(raw)
    data.update(fields)
    r.set(key, json.dumps(data), ex=86400)


def execute_job(
    job_data: dict,
    *,
    comfyui_base_url: str,
    redis_client: sync_redis.Redis,
    callback_secret: str,
    max_retries: int = 3,
) -> None:
    """
    Execute one media job end-to-end:
      load workflow → apply params → submit to ComfyUI →
      poll → download → POST to callback_url
    On failure, re-queues up to max_retries times, then dead-letters.
    """
    job_id = job_data["job_id"]
    _update_redis(redis_client, job_id, status="started")

    try:
        workflow_path = f"infra/comfyui/workflows/{job_data['workflow']}"
        workflow = load_workflow(workflow_path)
        params = dict(job_data.get("params") or {})

        # I2V jobs may include a source image URL that must be uploaded first.
        source_image_url = params.pop("_source_image_url", None)
        source_image_node = params.pop("_source_image_node", "97")
        if source_image_url:
            img_resp = httpx.get(source_image_url, timeout=30)
            img_resp.raise_for_status()
            uploaded_name = upload_image(
                comfyui_base_url,
                img_resp.content,
                filename=f"src_{job_id}.jpg",
            )
            params[f"{source_image_node}.image"] = uploaded_name

        workflow = apply_params(workflow, params)

        client_id = str(uuid.uuid4())
        prompt_id = submit_prompt(comfyui_base_url, workflow, client_id)
        outputs = wait_for_completion(comfyui_base_url, prompt_id)
        file_bytes, filename = download_output(comfyui_base_url, outputs)

        resp = httpx.post(
            job_data["callback_url"],
            headers={"Authorization": f"Bearer {callback_secret}"},
            data={"job_id": job_id},
            files={"file": (filename, file_bytes)},
            timeout=60,
        )
        resp.raise_for_status()
        _update_redis(redis_client, job_id, status="done")

    except Exception as exc:
        retry_count = job_data.get("retry_count", 0)
        if retry_count < max_retries:
            job_data["retry_count"] = retry_count + 1
            job_data["status"] = "queued"
            job_data["error"] = str(exc)
            redis_client.set(f"mediajob:{job_id}", json.dumps(job_data), ex=86400)
            queue = "media:photo" if job_data["job_type"] == "image" else "media:video"
            redis_client.rpush(queue, job_id)
        else:
            _update_redis(redis_client, job_id, status="dead", error=str(exc))
            redis_client.rpush("media:dead", job_id)
        raise

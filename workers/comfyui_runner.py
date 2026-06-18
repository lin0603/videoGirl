"""
Synchronous ComfyUI HTTP client — runs inside the 4090 worker process.

ComfyUI API flow:
  POST /prompt  →  get prompt_id
  GET  /history/<prompt_id>  →  poll until completed
  GET  /view?filename=...    →  download output file
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import httpx


class ComfyUIError(RuntimeError):
    pass


def load_workflow(workflow_path: str) -> dict:
    path = Path(workflow_path)
    if not path.exists():
        raise ComfyUIError(f"Workflow not found: {workflow_path}")
    return json.loads(path.read_text())


def apply_params(workflow: dict, params: dict[str, object]) -> dict:
    """
    Apply flat param overrides to a ComfyUI API-format workflow.
    Key format: "<node_id>.<input_name>", e.g. {"6.text": "sexy girl"}.
    """
    wf = copy.deepcopy(workflow)
    for key, value in params.items():
        node_id, _, input_name = key.partition(".")
        node = wf.get(node_id)
        if node and "inputs" in node:
            node["inputs"][input_name] = value
    return wf


def upload_image(base_url: str, image_bytes: bytes, filename: str = "source.jpg") -> str:
    """
    Upload an image to ComfyUI's input directory via POST /upload/image.
    Returns the filename ComfyUI assigned (use as the LoadImage node's 'image' param).
    """
    resp = httpx.post(
        f"{base_url}/upload/image",
        files={"image": (filename, image_bytes, "image/jpeg")},
        data={"type": "input", "overwrite": "true"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    name = data.get("name") or data.get("filename") or filename
    return name


def submit_prompt(base_url: str, workflow: dict, client_id: str) -> str:
    resp = httpx.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise ComfyUIError(f"No prompt_id in response: {data}")
    return prompt_id


def wait_for_completion(
    base_url: str,
    prompt_id: str,
    *,
    poll_interval: float = 3.0,
    timeout: float = 600.0,
) -> dict:
    """Poll /history/<prompt_id> until completed. Returns outputs dict."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = httpx.get(f"{base_url}/history/{prompt_id}", timeout=15)
        resp.raise_for_status()
        history = resp.json()
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("completed"):
                return entry.get("outputs", {})
            if status.get("status_str") == "error":
                messages = status.get("messages", [])
                raise ComfyUIError(f"ComfyUI job error: {messages}")
        time.sleep(poll_interval)
    raise ComfyUIError(f"Timed out after {timeout}s waiting for {prompt_id}")


def download_output(base_url: str, outputs: dict) -> tuple[bytes, str]:
    """
    Find the first image/video/gif in ComfyUI outputs and download it.
    Returns (file_bytes, filename).
    """
    for node_outputs in outputs.values():
        for output_type in ("images", "videos", "gifs"):
            items = node_outputs.get(output_type)
            if not items:
                continue
            item = items[0]
            params = {
                "filename": item["filename"],
                "subfolder": item.get("subfolder", ""),
                "type": item.get("type", "output"),
            }
            resp = httpx.get(
                f"{base_url}/view",
                params=params,
                timeout=120,
            )
            resp.raise_for_status()
            return resp.content, item["filename"]
    raise ComfyUIError("No image/video output in ComfyUI response")

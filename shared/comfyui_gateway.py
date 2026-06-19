"""
ComfyUI Station Gateway 非同步客戶端（task #10）。

videoGirl 的 worker 透過此客戶端呼叫 4090 上的 gateway /v1/generate，
不再直接操作原生 ComfyUI API。
"""
from __future__ import annotations

from typing import Any

import httpx

from shared.config import get_settings


class GatewayError(RuntimeError):
    """Gateway 回傳非 2xx 或連線異常時拋出。"""

    def __init__(self, message: str, *, detail: Any = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.detail = detail
        self.status_code = status_code


def _auth_headers() -> dict[str, str]:
    """根據設定產生 Authorization Bearer header。"""
    token = get_settings().comfyui_gateway_token
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def generate(
    capability: str,
    params: dict[str, Any],
    images: dict[str, str] | None = None,
    *,
    wait: bool = True,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """
    POST {gateway_url}/v1/generate，回傳 gateway 的 job dict。

    wait=True 時會阻塞到任務完成，回傳包含 outputs[{url,type,filename}] 的結果。
    非 2xx 時 raise GatewayError（含 detail 與 status_code）。
    """
    settings = get_settings()
    url = settings.comfyui_gateway_url.rstrip("/") + "/v1/generate"
    body = {
        "capability": capability,
        "params": params,
        "images": images or {},
        "wait": wait,
    }
    headers = {"Content-Type": "application/json"}
    headers.update(_auth_headers())

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            pass
        raise GatewayError(
            f"Gateway error {resp.status_code}: {detail}",
            detail=detail,
            status_code=resp.status_code,
        )
    return resp.json()


async def download_output(url: str, *, timeout: float = 120.0) -> bytes:
    """從 gateway 輸出直鏈下載圖片/影片位元組。"""
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# 同步包裝（供 workers/media_tasks.py 的 sync worker 使用）
# ---------------------------------------------------------------------------


def _raise_for_status(resp: httpx.Response) -> None:
    """把非 2xx 回應轉成 GatewayError。"""
    if resp.status_code < 400:
        return
    detail = resp.text
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        pass
    raise GatewayError(
        f"Gateway error {resp.status_code}: {detail}",
        detail=detail,
        status_code=resp.status_code,
    )


def generate_sync(
    capability: str,
    params: dict[str, Any],
    images: dict[str, str] | None = None,
    *,
    wait: bool = True,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """generate() 的同步版本。"""
    settings = get_settings()
    url = settings.comfyui_gateway_url.rstrip("/") + "/v1/generate"
    body = {
        "capability": capability,
        "params": params,
        "images": images or {},
        "wait": wait,
    }
    headers = {"Content-Type": "application/json"}
    headers.update(_auth_headers())

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=body, headers=headers)
    _raise_for_status(resp)
    return resp.json()


def download_output_sync(url: str, *, timeout: float = 120.0) -> bytes:
    """download_output() 的同步版本。"""
    headers = _auth_headers()
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content

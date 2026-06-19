"""FastAPI admin backend for voices, categories and personas."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import SESSION_COOKIE, check_credentials, sign_session, verify_session
from miniapp.app import register_mini_app
from repositories import admin_repo as repo
from shared.config import get_settings
from shared.db import AsyncSessionLocal
from shared.logging import get_logger
from shared.models import Persona, Voice, VoiceCategory

logger = get_logger("admin.app")

app = FastAPI(title="videoGirl Admin")
templates = Jinja2Templates(directory="admin/templates")
register_mini_app(app)


def _admin_redirect(path: str) -> RedirectResponse:
    resp = RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)
    return resp


async def require_admin(request: Request) -> str:
    username = verify_session(request)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/admin/login"},
            detail="Not authenticated",
        )
    return username


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/admin/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    if not check_credentials(username, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "帳號或密碼錯誤"},
        )
    resp = _admin_redirect("/admin/")
    resp.set_cookie(SESSION_COOKIE, sign_session(username), httponly=True, samesite="lax")
    return resp


@app.get("/admin/logout")
async def logout():
    resp = _admin_redirect("/admin/login")
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/admin/", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(require_admin)):
    return templates.TemplateResponse(request, "dashboard.html", {})


# Helpers


def _bool_value(form: dict, key: str) -> bool:
    return form.get(key) in ("1", "on", "true")


def _float_or(form: dict, key: str, default: float) -> float:
    try:
        return float(form[key])
    except (KeyError, ValueError):
        return default


def _int_or(form: dict, key: str, default: int) -> int:
    try:
        return int(form[key])
    except (KeyError, ValueError):
        return default


def _category_rows(categories: list[VoiceCategory]) -> list[dict]:
    return [
        {
            "slug": c.slug,
            "name": c.name,
            "sort_order": c.sort_order,
            "active": c.active,
        }
        for c in categories
    ]


def _voice_rows(voices: list[Voice]) -> list[dict]:
    return [
        {
            "slug": v.slug,
            "name": v.name,
            "provider": v.provider,
            "category": v.category.name if v.category else "",
            "sort_order": v.sort_order,
            "active": v.active,
        }
        for v in voices
    ]


def _persona_rows(personas: list[Persona]) -> list[dict]:
    return [
        {
            "slug": p.slug,
            "name": p.name,
            "nsfw_level": p.nsfw_level,
            "sort_order": p.sort_order,
            "active": p.active,
        }
        for p in personas
    ]


# Voice categories


@app.get("/admin/categories", response_class=HTMLResponse)
async def list_categories(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    categories = await repo.list_categories(session)
    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "title": "語音分類",
            "entity": "categories",
            "columns": [
                {"key": "slug", "label": "代碼"},
                {"key": "name", "label": "名稱"},
                {"key": "sort_order", "label": "排序"},
                {"key": "active", "label": "啟用", "type": "bool"},
            ],
            "rows": _category_rows(categories),
        },
    )


@app.get("/admin/categories/new", response_class=HTMLResponse)
async def new_category(
    request: Request,
    username: str = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "title": "新增語音分類",
            "entity": "categories",
            "fields": [
                {"name": "slug", "label": "代碼", "value": "", "type": "text"},
                {"name": "name", "label": "名稱", "value": "", "type": "text"},
                {"name": "sort_order", "label": "排序", "value": 0, "type": "int"},
                {"name": "active", "label": "啟用", "value": True, "type": "checkbox"},
            ],
        },
    )


@app.post("/admin/categories/new")
async def create_category(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    form = await request.form()
    await repo.create_category(
        session,
        {
            "slug": form["slug"],
            "name": form["name"],
            "sort_order": _int_or(form, "sort_order", 0),
            "active": _bool_value(form, "active"),
        },
    )
    return _admin_redirect("/admin/categories")


@app.get("/admin/categories/{slug}/edit", response_class=HTMLResponse)
async def edit_category(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    cat = await repo.get_category(session, slug)
    if cat is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "title": f"編輯語音分類: {cat.name}",
            "entity": "categories",
            "fields": [
                {"name": "name", "label": "名稱", "value": cat.name, "type": "text"},
                {"name": "sort_order", "label": "排序", "value": cat.sort_order, "type": "int"},
                {"name": "active", "label": "啟用", "value": cat.active, "type": "checkbox"},
            ],
        },
    )


@app.post("/admin/categories/{slug}/edit")
async def update_category(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    cat = await repo.get_category(session, slug)
    if cat is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    await repo.update_category(
        session,
        cat,
        {
            "name": form["name"],
            "sort_order": _int_or(form, "sort_order", 0),
            "active": _bool_value(form, "active"),
        },
    )
    return _admin_redirect("/admin/categories")


@app.post("/admin/categories/{slug}/delete")
async def delete_category(
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    cat = await repo.get_category(session, slug)
    if cat is None:
        raise HTTPException(status_code=404)
    await repo.delete_category(session, cat)
    return _admin_redirect("/admin/categories")


# Voices


@app.get("/admin/voices", response_class=HTMLResponse)
async def list_voices(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    voices = await repo.list_voices(session)
    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "title": "語音",
            "entity": "voices",
            "columns": [
                {"key": "slug", "label": "代碼"},
                {"key": "name", "label": "名稱"},
                {"key": "provider", "label": "提供者"},
                {"key": "category", "label": "分類"},
                {"key": "sort_order", "label": "排序"},
                {"key": "active", "label": "啟用", "type": "bool"},
            ],
            "rows": _voice_rows(voices),
        },
    )


async def _voice_form_context(
    request: Request,
    session: AsyncSession,
    voice: Voice | None,
    title: str,
) -> dict:
    categories = await repo.list_categories(session)
    cat_options = [{"value": "", "label": "（無）"}] + [
        {"value": c.slug, "label": c.name} for c in categories
    ]
    provider_options = [
        {"value": "breezevoice", "label": "BreezyVoice"},
        {"value": "edge-tts", "label": "Edge TTS"},
        {"value": "existing", "label": "Existing audio"},
    ]
    v = voice or Voice(
        slug="",
        name="",
        provider="breezevoice",
        reference_audio_path="",
        reference_transcript="",
        tempo=1.0,
        active=True,
        sort_order=0,
        category_slug=None,
    )
    return {
        "request": request,
        "title": title,
        "entity": "voices",
        "fields": [
            *(
                [{"name": "slug", "label": "代碼", "value": v.slug, "type": "text"}]
                if voice is None
                else []
            ),
            {"name": "name", "label": "名稱", "value": v.name, "type": "text"},
            {
                "name": "provider",
                "label": "提供者",
                "value": v.provider,
                "type": "select",
                "options": provider_options,
            },
            {
                "name": "category_slug",
                "label": "分類",
                "value": v.category_slug or "",
                "type": "select",
                "options": cat_options,
            },
            {"name": "reference_audio_path", "label": "參考音檔路徑", "value": v.reference_audio_path or "", "type": "text"},
            {
                "name": "reference_transcript",
                "label": "參考音檔台詞",
                "value": v.reference_transcript or "",
                "type": "textarea",
            },
            {"name": "tempo", "label": "語速", "value": v.tempo, "type": "number"},
            {"name": "sort_order", "label": "排序", "value": v.sort_order, "type": "int"},
            {"name": "active", "label": "啟用", "value": v.active, "type": "checkbox"},
        ],
    }


@app.get("/admin/voices/new", response_class=HTMLResponse)
async def new_voice(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    ctx = await _voice_form_context(request, session, None, "新增語音")
    return templates.TemplateResponse(request, "form.html", ctx)


@app.post("/admin/voices/new")
async def create_voice(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    form = await request.form()
    category_slug = form.get("category_slug") or None
    await repo.create_voice(
        session,
        {
            "slug": form["slug"],
            "name": form["name"],
            "provider": form.get("provider", "breezevoice"),
            "category_slug": category_slug,
            "reference_audio_path": form.get("reference_audio_path") or None,
            "reference_transcript": form.get("reference_transcript") or None,
            "tempo": _float_or(form, "tempo", 1.0),
            "sort_order": _int_or(form, "sort_order", 0),
            "active": _bool_value(form, "active"),
        },
    )
    return _admin_redirect("/admin/voices")


@app.get("/admin/voices/{slug}/edit", response_class=HTMLResponse)
async def edit_voice(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    voice = await repo.get_voice(session, slug)
    if voice is None:
        raise HTTPException(status_code=404)
    ctx = await _voice_form_context(request, session, voice, f"編輯語音: {voice.name}")
    return templates.TemplateResponse(request, "form.html", ctx)


@app.post("/admin/voices/{slug}/edit")
async def update_voice(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    voice = await repo.get_voice(session, slug)
    if voice is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    category_slug = form.get("category_slug") or None
    await repo.update_voice(
        session,
        voice,
        {
            "name": form["name"],
            "provider": form.get("provider", "breezevoice"),
            "category_slug": category_slug,
            "reference_audio_path": form.get("reference_audio_path") or None,
            "reference_transcript": form.get("reference_transcript") or None,
            "tempo": _float_or(form, "tempo", 1.0),
            "sort_order": _int_or(form, "sort_order", 0),
            "active": _bool_value(form, "active"),
        },
    )
    return _admin_redirect("/admin/voices")


@app.post("/admin/voices/{slug}/delete")
async def delete_voice(
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    voice = await repo.get_voice(session, slug)
    if voice is None:
        raise HTTPException(status_code=404)
    await repo.delete_voice(session, voice)
    return _admin_redirect("/admin/voices")


# Personas


@app.get("/admin/personas", response_class=HTMLResponse)
async def list_personas(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    personas = await repo.list_personas(session)
    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "title": "人設",
            "entity": "personas",
            "columns": [
                {"key": "slug", "label": "代碼"},
                {"key": "name", "label": "名稱"},
                {"key": "nsfw_level", "label": "NSFW 等級"},
                {"key": "sort_order", "label": "排序"},
                {"key": "active", "label": "啟用", "type": "bool"},
            ],
            "rows": _persona_rows(personas),
        },
    )


def _persona_fields(persona: Persona | None) -> list[dict]:
    p = persona or Persona(
        slug="",
        name="",
        avatar_url="",
        system_prompt="",
        greeting="",
        nsfw_level=0,
        active=True,
        sort_order=0,
    )
    fields = []
    if persona is None:
        fields.append({"name": "slug", "label": "代碼", "value": p.slug, "type": "text"})
    fields.extend(
        [
            {"name": "name", "label": "名稱", "value": p.name, "type": "text"},
            {"name": "avatar_url", "label": "頭像 URL", "value": p.avatar_url or "", "type": "text"},
            {
                "name": "system_prompt",
                "label": "系統提示詞 (System Prompt)",
                "value": p.system_prompt,
                "type": "textarea",
            },
            {"name": "greeting", "label": "開場問候", "value": p.greeting, "type": "textarea"},
            {"name": "nsfw_level", "label": "NSFW 等級", "value": p.nsfw_level, "type": "int"},
            {"name": "sort_order", "label": "排序", "value": p.sort_order, "type": "int"},
            {"name": "active", "label": "啟用", "value": p.active, "type": "checkbox"},
        ]
    )
    return fields


@app.get("/admin/personas/new", response_class=HTMLResponse)
async def new_persona(
    request: Request,
    username: str = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "title": "新增人設",
            "entity": "personas",
            "fields": _persona_fields(None),
        },
    )


@app.post("/admin/personas/new")
async def create_persona(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    form = await request.form()
    await repo.create_persona(
        session,
        {
            "slug": form["slug"],
            "name": form["name"],
            "avatar_url": form.get("avatar_url") or None,
            "system_prompt": form.get("system_prompt", ""),
            "greeting": form.get("greeting", ""),
            "nsfw_level": _int_or(form, "nsfw_level", 0),
            "sort_order": _int_or(form, "sort_order", 0),
            "active": _bool_value(form, "active"),
        },
    )
    return _admin_redirect("/admin/personas")


@app.get("/admin/personas/{slug}/edit", response_class=HTMLResponse)
async def edit_persona(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    persona = await repo.get_persona(session, slug)
    if persona is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "title": f"編輯人設: {persona.name}",
            "entity": "personas",
            "fields": _persona_fields(persona),
        },
    )


@app.post("/admin/personas/{slug}/edit")
async def update_persona(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    persona = await repo.get_persona(session, slug)
    if persona is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    await repo.update_persona(
        session,
        persona,
        {
            "name": form["name"],
            "avatar_url": form.get("avatar_url") or None,
            "system_prompt": form.get("system_prompt", ""),
            "greeting": form.get("greeting", ""),
            "nsfw_level": _int_or(form, "nsfw_level", 0),
            "sort_order": _int_or(form, "sort_order", 0),
            "active": _bool_value(form, "active"),
        },
    )
    return _admin_redirect("/admin/personas")


@app.post("/admin/personas/{slug}/delete")
async def delete_persona(
    slug: str,
    session: AsyncSession = Depends(get_db),
    username: str = Depends(require_admin),
):
    persona = await repo.get_persona(session, slug)
    if persona is None:
        raise HTTPException(status_code=404)
    await repo.delete_persona(session, persona)
    return _admin_redirect("/admin/personas")


# ---------------------------------------------------------------------------
# Internal media callback — called by the 4090 worker over Tailscale.
# NOT protected by admin session (no browser cookie); uses Bearer token.
# ---------------------------------------------------------------------------

def _verify_callback_secret(request: Request) -> None:
    expected = get_settings().media_callback_secret
    if not expected:
        raise HTTPException(status_code=503, detail="media callback not configured")
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid callback secret")


@app.post("/internal/media_done")
async def media_done_callback(
    request: Request,
    job_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """
    Receives completed media from the 4090 worker and delivers it to the user.
    The bot instance is stored in request.app.state.bot during startup.
    """
    _verify_callback_secret(request)

    from aiogram.types import BufferedInputFile
    from workers.queue_client import get_job, update_job

    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    data = await file.read()
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="bot not available")

    if job.job_type == "image":
        await bot.send_photo(
            job.user_id,
            BufferedInputFile(data, filename=file.filename or "image.jpg"),
        )
        # Cache photo bytes so subsequent video requests can use it as I2V source.
        try:
            from shared.media_store import store_last_photo
            await store_last_photo(job.user_id, data)
        except Exception:
            pass  # non-critical; don't fail the delivery
    else:
        await bot.send_video(
            job.user_id,
            BufferedInputFile(data, filename=file.filename or "video.mp4"),
        )

    job.status = "done"
    await update_job(job)
    return {"ok": True, "job_id": job_id}


@app.post("/internal/media_done_url")
async def media_done_url_callback(request: Request) -> dict:
    """
    Alternative callback that receives a JSON payload with a result_url,
    downloads the media, and delivers it to the user.
    """
    _verify_callback_secret(request)

    import httpx
    from aiogram.types import BufferedInputFile
    from workers.queue_client import get_job, update_job

    payload = await request.json()
    job_id = payload.get("job_id")
    result_url = payload.get("result_url")
    if not job_id or not result_url:
        raise HTTPException(status_code=422, detail="missing job_id or result_url")

    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="bot not available")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(result_url)
            resp.raise_for_status()
            data = resp.content
    except Exception as exc:
        logger.exception("media_download_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=502, detail="failed to fetch media") from exc

    filename = "image.jpg" if job.job_type == "image" else "video.mp4"
    if job.job_type == "image":
        await bot.send_photo(job.user_id, BufferedInputFile(data, filename=filename))
        try:
            from shared.media_store import store_last_photo
            await store_last_photo(job.user_id, data)
        except Exception:
            pass
    else:
        await bot.send_video(job.user_id, BufferedInputFile(data, filename=filename))

    job.status = "done"
    await update_job(job)
    return {"ok": True, "job_id": job_id}


@app.get("/internal/photo/{user_id}")
async def get_last_photo(user_id: int, request: Request) -> bytes:
    """
    Serve the cached last photo for a user (used as I2V source image).
    Protected by the same callback secret header.
    Auth: Authorization: Bearer <media_callback_secret>
    """
    _verify_callback_secret(request)
    from fastapi.responses import Response
    from shared.media_store import get_last_photo_bytes

    data = await get_last_photo_bytes(user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="no cached photo for user")
    return Response(content=data, media_type="image/jpeg")

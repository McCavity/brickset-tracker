"""
Brickset Tracker — FastAPI application.
Start: uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from datetime import date
from urllib.parse import quote

from fastapi import FastAPI, Form, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from execution.db import init_db
from execution.i18n import load_locales, t
from execution.photos import cleanup_stale_staging, upload_to_staging
from execution.rate_limit import get_quota_status
from navigation.lookup_router import route_lookup
from navigation.set_manager import (
    CONDITION_VALUES, count_all_sets, count_owned, delete_set, get_brands,
    get_facet_counts, get_set, get_sets, save_set, update_set
)
from execution.brickset import sync_owned


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    load_locales()
    cleanup_stale_staging()
    yield


app = FastAPI(title="Brickset Tracker", lifespan=lifespan)
app.mount("/static",  StaticFiles(directory="static"),  name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")
templates.env.filters["urlencode"] = lambda s: quote(str(s), safe="")


def _lang(request: Request) -> str:
    return request.cookies.get("lang", "de")


def _ctx(request: Request, **kwargs) -> dict:
    lang = _lang(request)
    quota = get_quota_status()
    return {"request": request, "lang": lang, "t": lambda k, **kw: t(k, lang, **kw),
            "quota": quota, **kwargs}


# ── Pages ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    sort: str = "date_of_purchase",
    dir: str = "DESC",
    q: str | None = None,
    brand: list[str] = Query(default_factory=list),
    condition: list[str] = Query(default_factory=list),
    theme: list[str] = Query(default_factory=list),
    status: list[str] = Query(default_factory=list),
):
    # Sanitise search
    q_clean = (q or "").strip()[:200] or None

    sets = get_sets(
        sort_by=sort, sort_dir=dir, q=q_clean,
        brands=brand, conditions=condition,
        themes=theme, statuses=status,
    )
    facets = get_facet_counts(
        q=q_clean, brands=brand, conditions=condition,
        themes=theme, statuses=status,
    )
    total = count_all_sets()

    return templates.TemplateResponse(request, "index.html", context=_ctx(
        request, sets=sets, facets=facets, total=total,
        active_filters={"brand": brand, "condition": condition,
                        "theme": theme, "status": status},
        q=q_clean or "", sort=sort, dir=dir,
        sort_options=["date_of_purchase", "name", "brand", "part_count", "price_paid"],
    ))


@app.get("/add", response_class=HTMLResponse)
async def add_page(request: Request):
    return templates.TemplateResponse(request, "add.html", context=_ctx(
        request, prefill={}, callout=None, conditions=CONDITION_VALUES,
        brands=get_brands(), today=date.today().isoformat(),
    ))


# ── API ────────────────────────────────────────────────────────────────────

@app.post("/api/lookup")
async def api_lookup(
    ean: str | None        = Form(None),
    brand: str | None      = Form(None),
    set_number: str | None = Form(None),
):
    result = await route_lookup(ean=ean, brand=brand, set_number=set_number)
    return JSONResponse(result)


@app.post("/api/sets")
async def api_save_set(request: Request):
    form  = await request.form()
    data  = dict(form)
    # Parse web_images from hidden field (JSON string)
    import json
    data["web_images"] = json.loads(data.get("web_images_json", "[]") or "[]")
    session_id = data.pop("session_id", None)

    result = save_set(data, session_id=session_id)
    return JSONResponse(result)


@app.get("/sets/{set_id}/edit", response_class=HTMLResponse)
async def edit_page(request: Request, set_id: int):
    s = get_set(set_id)
    if not s:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "edit.html", context=_ctx(
        request, set=s, conditions=CONDITION_VALUES, brands=get_brands(),
    ))


@app.post("/api/sets/{set_id}/update")
async def api_update_set(set_id: int, request: Request):
    form = await request.form()
    data = dict(form)
    import json
    data["web_images"] = json.loads(data.get("web_images_json", "[]") or "[]")
    session_id = data.pop("session_id", None)
    result = update_set(set_id, data, session_id=session_id)
    return JSONResponse(result)


@app.post("/api/sets/{set_id}/delete")
async def api_delete_set(set_id: int):
    delete_set(set_id)
    return JSONResponse({"ok": True})


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), session_id: str = Form(...)):
    content = await file.read()
    result  = upload_to_staging(content, file.filename or "photo", session_id)
    return JSONResponse(result)


@app.post("/api/sets/{set_id}/sync-brickset")
async def api_sync_brickset(set_id: int):
    s = get_set(set_id)
    if not s or s.get("brickset_set_id") is None:
        return JSONResponse({"status": "error", "message": "Kein Brickset-setID gespeichert."})
    qty = count_owned(s["brand"], s["set_number"])
    result = await sync_owned(s["brickset_set_id"], qty)
    return JSONResponse(result)


@app.get("/api/quota")
async def api_quota():
    return JSONResponse(get_quota_status())


@app.get("/api/proxy-image")
async def api_proxy_image(url: str):
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            r = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://www.merlinssteine.de/",
            })
        if r.status_code != 200:
            return JSONResponse({"error": "not found"}, status_code=404)
        return Response(content=r.content, media_type=r.headers.get("content-type", "image/webp"))
    except Exception:
        return JSONResponse({"error": "fetch failed"}, status_code=404)


@app.post("/set-lang")
async def set_lang(lang: str = Form("de"), next: str = Form("/")):
    lang = lang if lang in ("de", "en") else "de"
    # Only allow relative paths to prevent open redirect
    target = next if (next.startswith("/") and not next.startswith("//")) else "/"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365)
    return response

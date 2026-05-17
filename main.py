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
    imported: int | None = None,
    backfilled: int | None = None,
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
        flash_imported=imported,
        flash_backfilled=backfilled,
    ))


@app.get("/api/sets/filter", response_class=HTMLResponse)
async def api_filter(
    request: Request,
    sort: str = "date_of_purchase",
    dir: str = "DESC",
    q: str | None = None,
    brand: list[str] = Query(default_factory=list),
    condition: list[str] = Query(default_factory=list),
    theme: list[str] = Query(default_factory=list),
    status: list[str] = Query(default_factory=list),
):
    """Returns just the results region as an HTML partial — for live filtering."""
    q_clean = (q or "").strip()[:200] or None

    sets = get_sets(
        sort_by=sort, sort_dir=dir, q=q_clean,
        brands=brand, conditions=condition,
        themes=theme, statuses=status,
    )
    total = count_all_sets()

    return templates.TemplateResponse(request, "_results_partial.html", context=_ctx(
        request, sets=sets, total=total,
        active_filters={"brand": brand, "condition": condition,
                        "theme": theme, "status": status},
        q=q_clean or "",
    ))


@app.get("/add", response_class=HTMLResponse)
async def add_page(request: Request):
    return templates.TemplateResponse(request, "add.html", context=_ctx(
        request, prefill={}, callout=None, conditions=CONDITION_VALUES,
        brands=get_brands(), today=date.today().isoformat(),
    ))


@app.get("/import/brickset", response_class=HTMLResponse)
async def import_page(request: Request):
    return templates.TemplateResponse(request, "import_brickset.html", context=_ctx(request))


@app.post("/api/import/brickset/fetch", response_class=HTMLResponse)
async def api_import_fetch(request: Request):
    """Fetch the user's Brickset collection and return a preview partial."""
    import json
    from execution.brickset import fetch_owned_collection
    from navigation.set_manager import count_owned, find_local_rows_missing_brickset_id

    result = await fetch_owned_collection()

    ctx = _ctx(request, fetch_status=result["status"])

    if result["status"] != "ok":
        ctx["fetch_message"] = result.get("message", "")
        ctx["rows"] = []
        ctx["totals"] = {"bs_total": 0, "will_create": 0, "sets_count": 0, "will_backfill": 0}
        return templates.TemplateResponse(request, "_brickset_import_preview.html", context=ctx)

    rows = []
    will_create = 0
    will_backfill = 0
    for s in result["sets"]:
        # Defensive: skip Brickset rows missing essential identifying fields
        if not s.get("set_number") or not s.get("set_id"):
            continue

        brand = "LEGO"
        set_number = s["set_number"]
        local_qty = count_owned(brand, set_number)
        missing_ids = find_local_rows_missing_brickset_id(brand, set_number)

        bs_qty = s.get("qty_owned") or 1
        default_import_qty = max(0, bs_qty - local_qty)
        will_create += default_import_qty
        will_backfill += len(missing_ids)

        if local_qty == 0:
            hint_key = None
        elif local_qty < bs_qty:
            hint_key = "import.hint_partial"
        elif local_qty == bs_qty:
            hint_key = "import.hint_already_covered"
        else:  # local_qty > bs_qty
            hint_key = "import.hint_local_richer"

        payload = {
            "brand":           brand,
            "set_number":      set_number,
            "name":            s.get("name") or "",
            "part_count":      s.get("pieces"),
            "theme":           s.get("theme"),
            "release_year":    s.get("year"),
            "ean":             s.get("ean"),
            "web_images":      [s["image_url"]] if s.get("image_url") else [],
            "brickset_set_id": s["set_id"],
            "local_ids_missing_bs_id": missing_ids,
        }
        rows.append({
            "set_number":         set_number,
            "name":               s.get("name") or "",
            "theme":              s.get("theme"),
            "release_year":       s.get("year"),
            "part_count":         s.get("pieces"),
            "bs_qty":             bs_qty,
            "local_qty":          local_qty,
            "default_import_qty": default_import_qty,
            "hint_key":           hint_key,
            "payload_json":       json.dumps(payload),
        })

    ctx["rows"] = rows
    ctx["totals"] = {
        "bs_total":      sum(r["bs_qty"] for r in rows),
        "will_create":   will_create,
        "sets_count":    len([r for r in rows if r["default_import_qty"] > 0]),
        "will_backfill": will_backfill,
    }
    return templates.TemplateResponse(request, "_brickset_import_preview.html", context=ctx)


@app.post("/api/import/brickset/commit")
async def api_import_commit(request: Request):
    """Commit a Brickset import. Accepts JSON payload {"rows": [...]}.

    Each row must have: brand, set_number, brickset_set_id, name, import_qty
    (non-negative int), local_ids_missing_bs_id (list[int]).
    Optional: part_count, theme, release_year, ean, web_images (list).

    Returns a 303 redirect to /?imported=N&backfilled=K.
    """
    from navigation.set_manager import commit_import_rows

    body = await request.json()
    raw_rows = body.get("rows") or []

    sanitised = []
    for row in raw_rows:
        # Validate required fields
        if not row.get("brand") or not row.get("set_number"):
            continue
        if not row.get("brickset_set_id"):
            continue

        # Schema requires part_count NOT NULL; skip rows without a valid
        # non-negative int (defaulting to 0 would pollute the data with
        # phantom "0-piece sets").
        try:
            part_count = int(row["part_count"])
        except (TypeError, ValueError, KeyError):
            continue
        if part_count < 0:
            continue

        # Clamp import_qty to non-negative int
        try:
            qty = max(0, int(row.get("import_qty") or 0))
        except (TypeError, ValueError):
            qty = 0

        sanitised.append({
            "brand":                   str(row["brand"]),
            "set_number":              str(row["set_number"]),
            "name":                    row.get("name") or "",
            "part_count":              part_count,
            "theme":                   row.get("theme"),
            "release_year":            row.get("release_year"),
            "ean":                     row.get("ean"),
            "web_images":              row.get("web_images") or [],
            "brickset_set_id":         int(row["brickset_set_id"]),
            "import_qty":              qty,
            "local_ids_missing_bs_id": [int(x) for x in (row.get("local_ids_missing_bs_id") or [])],
        })

    result = commit_import_rows(sanitised)
    return RedirectResponse(
        f"/?imported={result['created']}&backfilled={result['backfilled']}",
        status_code=303,
    )


@app.get("/settings/brand-slugs", response_class=HTMLResponse)
async def settings_brand_slugs(
    request: Request,
    error: str | None = None,
    brand: str | None = None,
):
    """Brand → merlinssteine.de URL slug mappings (settings)."""
    from execution.brand_slugs import list_brand_slugs
    pairs = list_brand_slugs()
    return templates.TemplateResponse(request, "settings_brand_slugs.html", context=_ctx(
        request, pairs=pairs,
        error=error, error_brand=brand,
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


@app.get("/sets/{set_id}", response_class=HTMLResponse)
async def details_page(request: Request, set_id: int):
    s = get_set(set_id)
    if not s:
        return RedirectResponse("/", status_code=303)

    from execution.brand_slugs import brand_to_slug
    brickset_url = (
        f"https://brickset.com/sets/{s['set_number']}-1/"
        if s.get("brickset_set_id") is not None else None
    )
    merlinssteine_url = (
        f"https://www.merlinssteine.de/sets/"
        f"{brand_to_slug(s['brand'])}-{s['set_number'].lower()}/"
    )

    return templates.TemplateResponse(request, "details.html", context=_ctx(
        request, set=s,
        brickset_url=brickset_url,
        merlinssteine_url=merlinssteine_url,
    ))


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

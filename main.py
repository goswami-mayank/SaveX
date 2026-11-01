import logging
import os
import httpx
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Literal

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from supabase import Client
from supabase_auth.errors import AuthError, AuthRetryableError, AuthUnknownError

from backend.domain import (
    ItemPatch,
    ItemsIn,
    add_days,
    days_left,
    expiry_preview,
    item_view,
)
from backend.llm import make_plan, parse_items
from backend.config import frontend_origin, trusted_origins, local_today

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

import services as svc

AT, RT = "sx_at", "sx_rt"
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
templates = Jinja2Templates(directory=str(BASE / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = None
    admin = svc.get_admin_db()
    if admin and os.getenv("SCHEDULER_ENABLED", "true").lower() == "true":
        scheduler = BackgroundScheduler(
            timezone=os.getenv("NOTIFICATION_TIMEZONE", "Asia/Kolkata")
        )
        scheduler.add_job(
            lambda: svc.run_alerts(admin),
            "cron",
            minute="*",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="SaveX", lifespan=lifespan)


# ---------- auth plumbing ----------


class NotAuthenticated(Exception):
    pass


class PhoneMissing(Exception):
    pass


@dataclass
class Ctx:
    user_id: str
    email: str
    name: str
    phone: str | None
    db: Client


def set_session_cookies(resp, session) -> None:
    resp.set_cookie(
        AT,
        session.access_token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=session.expires_in or 3600,
    )
    resp.set_cookie(
        RT,
        session.refresh_token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )


def _context(access_token: str, user) -> Ctx:
    db = svc.get_db(access_token)
    # DB errors propagate (500) instead of being mistaken for a bad login
    rows = (
        db.table("users")
        .select("name,whatsapp_number")
        .eq("id", user.id)
        .execute()
        .data
    )
    p = rows[0] if rows else {}
    return Ctx(
        user.id, user.email or "", p.get("name") or "", p.get("whatsapp_number"), db
    )


def auth_ctx(request: Request) -> Ctx:
    at, rt = request.cookies.get(AT), request.cookies.get(RT)
    if at:
        try:
            user = svc.get_db().auth.get_user(at).user
        except AuthError:
            user = None
        if user:
            return _context(at, user)
    if rt:
        try:
            session = svc.get_db().auth.refresh_session(rt).session
        except AuthError:
            session = None
        if session:
            request.state.new_session = session  # middleware writes the new cookies
            return _context(session.access_token, session.user)
    raise NotAuthenticated


def user_ctx(ctx: Ctx = Depends(auth_ctx)) -> Ctx:
    return ctx


@app.middleware("http")
async def persist_refreshed_session(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin.rstrip("/") not in trusted_origins()
    ):
        return JSONResponse({"detail": "Unexpected request origin"}, status_code=403)
    response = await call_next(request)
    session = getattr(request.state, "new_session", None)
    if session:
        set_session_cookies(response, session)
    return response


@app.exception_handler(NotAuthenticated)
async def _not_auth(request: Request, _):
    if request.url.path.startswith(("/api", "/items", "/voice", "/alerts", "/plan")):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(PhoneMissing)
async def _phone_missing(request: Request, _):
    if request.url.path.startswith(("/api", "/items", "/voice", "/alerts", "/plan")):
        return JSONResponse({"detail": "Add your phone number first"}, status_code=403)
    return RedirectResponse("/profile", status_code=303)


def normalize_phone(raw: str) -> str:
    return re.sub(r"[\s\-()]", "", raw)


def page(request: Request, template: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


# ---------- pages ----------


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, ctx: Ctx = Depends(user_ctx)):
    return page(request, "index.html", name=ctx.name or ctx.email, phone=ctx.phone)


@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return page(request, "signup.html")


@app.post("/signup")
def signup(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    name: str = Form(""),
    phone: str = Form(""),
):
    phone = normalize_phone(phone)
    if len(password) < 6:
        return page(
            request, "signup.html", 400, error="Password must be at least 6 characters."
        )
    if phone and not PHONE_RE.match(phone):
        return page(
            request,
            "signup.html",
            400,
            error="Enter the phone number in international format, such as +919876543210.",
        )
    try:
        res = svc.get_db().auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {
                    "data": {"name": name.strip(), "phone": phone or None},
                    "email_redirect_to": frontend_origin(request.headers.get("origin"))
                    + "/login?confirmed=1",
                },
            }
        )
    except AuthError as e:
        if (
            isinstance(e, (AuthRetryableError, AuthUnknownError))
            or (getattr(e, "status", 0) or 0) >= 500
        ):
            logging.getLogger("savex").warning(
                "Signup authentication service unavailable: %s", type(e).__name__
            )
            return page(
                request,
                "signup.html",
                503,
                error="Sign-up is temporarily unavailable. Please try again.",
            )
        return page(request, "signup.html", 400, error=e.message)
    if res.session:
        resp = RedirectResponse("/", status_code=303)
        set_session_cookies(resp, res.session)
        return resp
    return page(
        request, "login.html", info="Account created. Confirm your email, then log in."
    )


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    info = (
        "Email confirmed. You can log in now."
        if request.query_params.get("confirmed")
        else None
    )
    return page(request, "login.html", info=info)


@app.post("/resend-confirmation", response_class=HTMLResponse)
def resend_confirmation(request: Request, email: str = Form()):
    email = email.strip()
    if not email:
        return page(
            request,
            "login.html",
            400,
            error="Enter your email address to request a confirmation link.",
        )
    try:
        svc.get_db().auth.resend(
            {
                "type": "signup",
                "email": email,
                "options": {
                    "email_redirect_to": frontend_origin(request.headers.get("origin"))
                    + "/login?confirmed=1"
                },
            }
        )
    except AuthError as e:
        status = getattr(e, "status", None)
        if status == 429:
            return page(
                request,
                "login.html",
                429,
                error="Please wait a little before requesting another confirmation link.",
            )
        logging.getLogger("savex").warning(
            "Confirmation resend failed: %s", type(e).__name__
        )
        return page(
            request,
            "login.html",
            503,
            error="Could not send a confirmation link. Please try again.",
        )
    return page(
        request,
        "login.html",
        info="If this account needs confirmation, a new link has been requested. Check your email.",
    )


@app.post("/login")
def login(request: Request, email: str = Form(), password: str = Form()):
    try:
        res = svc.get_db().auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except AuthError as e:
        if (
            isinstance(e, (AuthRetryableError, AuthUnknownError))
            or (getattr(e, "status", 0) or 0) >= 500
        ):
            logging.getLogger("savex").warning(
                "Login authentication service unavailable: %s", type(e).__name__
            )
            return page(
                request,
                "login.html",
                503,
                error="Login is temporarily unavailable. Please try again.",
            )
        return page(request, "login.html", 400, error=e.message)
    resp = RedirectResponse("/", status_code=303)
    set_session_cookies(resp, res.session)
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(AT)
    resp.delete_cookie(RT)
    return resp


@app.get("/profile", response_class=HTMLResponse)
def profile_form(request: Request, ctx: Ctx = Depends(auth_ctx)):
    return page(
        request, "profile.html", phone=ctx.phone or "", needs_phone=not ctx.phone
    )


@app.post("/profile")
def profile_save(request: Request, phone: str = Form(""), ctx: Ctx = Depends(auth_ctx)):
    phone = normalize_phone(phone)
    if phone and not PHONE_RE.match(phone):
        return page(
            request,
            "profile.html",
            400,
            phone=phone,
            needs_phone=not ctx.phone,
            error="Enter a valid phone number in international format, e.g. +919876543210.",
        )
    ctx.db.table("users").upsert(
        {"id": ctx.user_id, "whatsapp_number": phone or None, "name": ctx.name or None}
    ).execute()
    return RedirectResponse("/", status_code=303)


# ---------- API ----------


def view(item: dict, today: date) -> dict:
    return item_view(item, today)


class TranscriptIn(BaseModel):
    transcript: str = Field(min_length=1, max_length=12000)


@app.post("/voice")
@app.post("/api/voice")
def voice(body: TranscriptIn, ctx: Ctx = Depends(user_ctx)):
    try:
        items = parse_items(body.transcript, local_today())
    except Exception:
        logging.getLogger("savex").exception("Extraction failed")
        raise HTTPException(
            502, "Could not parse groceries. Review your transcript and retry."
        )
    return {"transcript": body.transcript, "items": items}


@app.post("/items")
@app.post("/api/items")
def save_items(body: ItemsIn, ctx: Ctx = Depends(user_ctx)):
    if not body.items:
        raise HTTPException(400, "No items to save")
    rows = [
        {
            "user_id": ctx.user_id,
            "name": i.name.strip(),
            "bought_date": i.bought_date.isoformat(),
            "shelf_days": i.shelf_days,
            "expiry_date": add_days(i.bought_date.isoformat(), i.shelf_days),
            "location": i.location,
            "status": "expired"
            if date.fromisoformat(add_days(i.bought_date.isoformat(), i.shelf_days))
            < local_today()
            else "active",
        }
        for i in body.items
    ]
    return {"saved": len(ctx.db.table("items").insert(rows).execute().data)}


@app.get("/items")
@app.get("/api/items")
def list_items(ctx: Ctx = Depends(user_ctx)):
    rows = (
        ctx.db.table("items")
        .select("*")
        .neq("status", "used")
        .order("expiry_date")
        .execute()
        .data
    )
    today = local_today()
    return [view(r, today) for r in rows]


@app.patch("/items/{item_id}")
@app.patch("/api/items/{item_id}")
def patch_item(item_id: int, body: ItemPatch, ctx: Ctx = Depends(user_ctx)):
    if not body.model_fields_set:
        raise HTTPException(422, "Supply at least one field to update")
    rows = ctx.db.table("items").select("*").eq("id", item_id).execute().data
    if not rows:
        raise HTTPException(404, "Item not found")
    changes = body.model_dump(exclude_none=True)
    if "bought_date" in changes:
        changes["bought_date"] = changes["bought_date"].isoformat()
    if "bought_date" in changes or "shelf_days" in changes:
        merged = {**rows[0], **changes}
        changes["expiry_date"] = add_days(merged["bought_date"], merged["shelf_days"])
    merged = {**rows[0], **changes}
    if merged["status"] != "used":
        changes["status"] = (
            "expired" if days_left(merged, local_today()) < 0 else "active"
        )
    updated = ctx.db.table("items").update(changes).eq("id", item_id).execute().data
    return view(updated[0], local_today())


@app.get("/alerts")
@app.get("/api/alerts")
def list_alerts(ctx: Ctx = Depends(user_ctx)):
    return (
        ctx.db.table("alerts_log")
        .select("id,item_id,level,channel,message,sent_at,is_read,delivery_status")
        .order("sent_at", desc=True)
        .limit(50)
        .execute()
        .data
    )


@app.post("/api/alerts/read")
def mark_read(ctx: Ctx = Depends(user_ctx)):
    ctx.db.table("alerts_log").update({"is_read": True}).eq("channel", "app").eq(
        "is_read", False
    ).execute()
    return {"ok": True}


@app.post("/api/alerts/check")
def check_alerts(ctx: Ctx = Depends(user_ctx)):
    admin = svc.get_admin_db()
    if not admin:
        raise HTTPException(503, "Notification worker is not configured.")
    return svc.run_alerts(admin, user_id=ctx.user_id)


@app.get("/api/notification-status")
def notification_status(ctx: Ctx = Depends(user_ctx)):
    jobs = (
        ctx.db.table("notification_jobs")
        .select("id,channel,status,scheduled_at,items(name)")
        .gte(
            "scheduled_at", (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        )
        .order("scheduled_at")
        .limit(60)
        .execute()
        .data
    )
    return {
        "sms_enabled": svc.sms_enabled(),
        "sms_number_configured": bool(ctx.phone),
        "timezone": os.getenv("NOTIFICATION_TIMEZONE", "Asia/Kolkata"),
        "jobs": jobs,
    }


class AlertDemoRequest(BaseModel):
    days_remaining: Literal[0, 3, 7] = 0


@app.post("/api/alerts/demo")
def alert_demo(body: AlertDemoRequest, ctx: Ctx = Depends(user_ctx)):
    """Preview the real schedule without writes, SMS, calls, or clock changes."""
    admin = svc.get_admin_db()
    if not admin:
        raise HTTPException(503, "Notification worker is not configured.")
    zone_name = os.getenv("NOTIFICATION_TIMEZONE", "Asia/Kolkata")
    zone = ZoneInfo(zone_name)
    day = datetime.now(zone).date()
    start = datetime.combine(day, time.min, tzinfo=zone)
    slots = (
        admin.rpc(
            "preview_notification_schedule",
            {
                "p_start": start.isoformat(),
                "p_local_day": day.isoformat(),
                "p_expiry": (day + timedelta(days=body.days_remaining)).isoformat(),
                "p_timezone": zone_name,
            },
        )
        .execute()
        .data
    )
    events = []
    for slot in sorted(slots, key=lambda value: value["scheduled_at"]):
        events.append(
            {
                "channel": "in-app",
                "scheduled_at": slot["scheduled_at"],
                "message": "Simulated in-app reminder",
            }
        )
        events.append(
            {
                "channel": "sms_mock",
                "scheduled_at": slot["scheduled_at"],
                "message": "Simulated SMS — no message sent",
            }
        )
        if body.days_remaining == 0 and slot["slot"] == 1:
            events.append(
                {
                    "channel": "call_mock",
                    "scheduled_at": slot["scheduled_at"],
                    "message": "Simulated call — no call placed",
                }
            )
    return {
        "simulated": True,
        "timezone": zone_name,
        "days_remaining": body.days_remaining,
        "events": events,
    }


@app.post("/plan")
@app.post("/api/plan")
def plan(ctx: Ctx = Depends(user_ctx)):
    items = ctx.db.table("items").select("*").eq("status", "active").execute().data
    if not items:
        raise HTTPException(400, "Add some items first")
    try:
        return make_plan(items, local_today())
    except Exception:
        raise HTTPException(502, "Could not generate a valid meal plan. Please retry.")


# Household items intentionally have no expiry requirement.
from backend.household import HouseholdItem, HouseholdPatch, extract_household
from backend.research import search_recipes, search_meal_images, ResearchError


@app.get("/api/household")
def household_list(ctx: Ctx = Depends(user_ctx)):
    return (
        ctx.db.table("household_items")
        .select("*")
        .order("recorded_at", desc=True)
        .execute()
        .data
    )


@app.post("/api/household", status_code=201)
def household_create(body: HouseholdItem, ctx: Ctx = Depends(user_ctx)):
    row = body.model_dump(mode="json")
    row["user_id"] = ctx.user_id
    return ctx.db.table("household_items").insert(row).execute().data[0]


class HouseholdBatch(BaseModel):
    items: list[HouseholdItem] = Field(min_length=1, max_length=50)


@app.post("/api/household/batch", status_code=201)
def household_batch(body: HouseholdBatch, ctx: Ctx = Depends(user_ctx)):
    rows = [
        {**item.model_dump(mode="json"), "user_id": ctx.user_id} for item in body.items
    ]
    result = ctx.db.table("household_items").insert(rows).execute().data
    return {"saved": len(result)}


@app.patch("/api/household/{item_id}")
def household_update(item_id: int, body: HouseholdPatch, ctx: Ctx = Depends(user_ctx)):
    changes = body.model_dump(exclude_unset=True, mode="json")
    if not changes or any(v is None for v in changes.values()):
        raise HTTPException(422, "Supply nonempty update fields")
    rows = (
        ctx.db.table("household_items").update(changes).eq("id", item_id).execute().data
    )
    if not rows:
        raise HTTPException(404, "Household item not found")
    return rows[0]


@app.delete("/api/household/{item_id}")
def household_delete(item_id: int, ctx: Ctx = Depends(user_ctx)):
    rows = ctx.db.table("household_items").delete().eq("id", item_id).execute().data
    if not rows:
        raise HTTPException(404, "Household item not found")
    return {"deleted": True}


@app.post("/api/household/extract")
def household_extract(body: TranscriptIn, ctx: Ctx = Depends(user_ctx)):
    try:
        return {"items": extract_household(body.transcript)}
    except Exception:
        logging.getLogger("savex").exception("Household extraction failed")
        raise HTTPException(502, "Unable to extract household items; retry.")


class PlanOptions(BaseModel):
    research: bool = False


@app.post("/api/plan/research")
def research_plan(body: PlanOptions, ctx: Ctx = Depends(user_ctx)):
    items = ctx.db.table("items").select("*").eq("status", "active").execute().data
    from backend.domain import inventory_context

    active, priority = inventory_context(items, local_today())
    if not active:
        raise HTTPException(400, "Add active food items first")
    try:
        sources = (
            search_recipes(priority or [item["name"] for item in active])
            if body.research
            else []
        )
        result = make_plan(active, local_today(), research=sources)
        images = search_meal_images(result["meals"]) if body.research else {}
        return {**result, "sources": sources, "meal_images": images}
    except ResearchError as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        logging.getLogger("savex").exception("Meal planning failed")
        raise HTTPException(502, "Could not generate a valid meal plan. Please retry.")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "external_notifications": os.getenv("ENABLE_EXTERNAL_NOTIFICATIONS", "false")
        == "true",
    }


@app.get("/api/ready")
def ready():
    try:
        db = svc.get_admin_db()
        if not db:
            raise RuntimeError("Readiness requires the Supabase secret key")
        db.table("users").select("id,whatsapp_number").limit(0).execute()
        db.table("items").select(
            "id,user_id,name,bought_date,shelf_days,expiry_date,location,status"
        ).limit(0).execute()
        db.table("alerts_log").select(
            "id,item_id,user_id,level,channel,message,delivery_status,job_id"
        ).limit(0).execute()
        db.table("notification_jobs").select(
            "id,user_id,item_id,status,scheduled_at"
        ).limit(0).execute()
        db.table("household_items").select(
            "id,user_id,name,category,location,recorded_at"
        ).limit(0).execute()
    except Exception:
        return JSONResponse(
            {
                "status": "not_ready",
                "detail": "Database configuration or migration required",
            },
            status_code=503,
        )
    return {"status": "ready"}


class PreviewIn(BaseModel):
    as_of: date


@app.post("/api/expiry/preview")
def preview(body: PreviewIn, ctx: Ctx = Depends(user_ctx)):
    rows = (
        ctx.db.table("items")
        .select("*")
        .neq("status", "used")
        .order("expiry_date")
        .execute()
        .data
    )
    return {
        "as_of": body.as_of.isoformat(),
        "preview_only": True,
        "items": expiry_preview(rows, body.as_of),
    }


from postgrest.exceptions import APIError as DatabaseAPIError


@app.exception_handler(DatabaseAPIError)
async def database_error(request: Request, exc):
    logging.getLogger("savex").warning("Database request failed: %s", exc.code)
    return JSONResponse(
        {"detail": "Database unavailable or schema migration required. Please retry."},
        status_code=503,
    )


@app.exception_handler(httpx.HTTPError)
async def upstream_connection_error(request: Request, exc: httpx.HTTPError):
    logging.getLogger("savex").warning(
        "Upstream connection failed: %s", type(exc).__name__
    )
    return JSONResponse(
        {"detail": "A service is unavailable. Please try again."}, status_code=503
    )


from backend.audio import create_router

app.include_router(create_router(user_ctx))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

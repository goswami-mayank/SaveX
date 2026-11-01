"""Trusted browser origins for local and Codespaces development."""

import os


def trusted_origins() -> set[str]:
    configured = os.getenv("APP_ORIGIN")
    if configured:
        return {configured.rstrip("/")}
    allowed = {"http://localhost:3000", "http://127.0.0.1:3000"}
    name = os.getenv("CODESPACE_NAME")
    domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if name and domain:
        allowed.add(f"https://{name}-3000.{domain}")
    return allowed


def frontend_origin(request_origin: str | None = None) -> str:
    allowed = trusted_origins()
    if request_origin and request_origin.rstrip("/") in allowed:
        return request_origin.rstrip("/")
    configured = os.getenv("APP_ORIGIN")
    if configured:
        return configured.rstrip("/")
    name = os.getenv("CODESPACE_NAME")
    domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if name and domain:
        return f"https://{name}-3000.{domain}"
    return "http://localhost:3000"


def local_today():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(
        ZoneInfo(os.getenv("NOTIFICATION_TIMEZONE", "Asia/Kolkata"))
    ).date()

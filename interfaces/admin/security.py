"""Frontière administrative : socket locale, Host/Origin et verrou facultatif unique."""

import json
from pathlib import Path
import secrets
from threading import RLock
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
AUTH_FILE = ROOT / ".red-install/admin-auth.json"
_SESSIONS = {}
_LOCK = RLock()
_FAILURES = 0
_BLOCKED_UNTIL = 0.0
COOKIE = "red_admin_session"
LOGIN_HTML = """<!doctype html><html lang="fr"><meta charset="utf-8"><title>Administration Red</title>
<style>body{max-width:440px;margin:12vh auto;font:17px system-ui;background:#11131a;color:#eef0f6}input,button{font:inherit;padding:12px;margin:12px 0;width:100%;box-sizing:border-box}p{color:#adb4c8}</style>
<h1>Administration Red</h1><p>Entre le mot de passe administrateur de ce PC.</p>
<form><input type="password" autocomplete="current-password" required aria-label="Mot de passe"><button>Ouvrir le panneau</button></form><p id="message"></p>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();const field=document.querySelector('input');const password=field.value;field.value='';const r=await fetch('/api/panneau/session/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});if(r.ok)location.reload();else document.querySelector('#message').textContent='Accès refusé. Vérifie le mot de passe ou réessaie plus tard.';};</script></html>"""


def local_request(request):
    try:
        client = getattr(request.client, "host", "")
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
        origin = request.headers.get("origin")
        return (
            client in {"127.0.0.1", "::1"}
            and host in {"127.0.0.1", "localhost", "::1"}
            and not any(
                request.headers.get(k)
                for k in (
                    "forwarded",
                    "x-forwarded-for",
                    "x-forwarded-host",
                    "x-real-ip",
                )
            )
            and (not origin or origin == str(request.base_url).rstrip("/"))
            and request.headers.get("sec-fetch-site") != "cross-site"
        )
    except ValueError:
        return False


def set_password(password):
    """Appelé uniquement par la commande locale interactive, jamais via une route."""
    from nacl import pwhash

    if not isinstance(password, str) or not 10 <= len(password) <= 1024:
        raise ValueError("Utilise de 10 à 1024 caractères.")
    hashed = pwhash.argon2id.str(
        password.encode(), opslimit=3, memlimit=128 * 1024 * 1024
    ).decode()
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    import os, tempfile

    fd, name = tempfile.mkstemp(prefix=".admin-", dir=AUTH_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump({"hash": hashed}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, AUTH_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    with _LOCK:
        _SESSIONS.clear()


class AdminBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(
            ("/panneau", "/api/panneau", "/cockpit", "/api/cockpit", "/api/gestes")
        ):
            return await self.app(scope, receive, send)
        from starlette.requests import Request
        from starlette.responses import JSONResponse, HTMLResponse

        request = Request(scope, receive)
        path = scope["path"]

        def response(message, status=403):
            return JSONResponse(
                {"ok": False, "message": message},
                status_code=status,
                headers={"Cache-Control": "no-store"},
            )

        if not local_request(request):
            return await response("Administration accessible depuis ce PC uniquement.")(
                scope, receive, send
            )
        if request.method not in {
            "GET",
            "HEAD",
        } and "application/json" not in request.headers.get("content-type", ""):
            return await response("Content-Type invalide.", 415)(scope, receive, send)
        configured = AUTH_FILE.is_file()
        now = time.monotonic()
        with _LOCK:
            for token, expires in tuple(_SESSIONS.items()):
                if expires <= now:
                    _SESSIONS.pop(token, None)
            authorized = request.cookies.get(COOKIE) in _SESSIONS
        if path == "/api/panneau/session/logout" and request.method == "POST":
            with _LOCK:
                _SESSIONS.pop(request.cookies.get(COOKIE), None)
            result = JSONResponse({"ok": True})
            result.delete_cookie(COOKIE)
            return await result(scope, receive, send)
        if (
            configured
            and path == "/api/panneau/session/login"
            and request.method == "POST"
        ):
            global _FAILURES, _BLOCKED_UNTIL
            from nacl import pwhash
            from nacl.exceptions import CryptoError

            raw = bytearray()
            try:
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > 4096:
                        raise ValueError()
                data = json.loads(raw)
                password = data.get("password")
                data.clear()
                if not isinstance(password, str) or len(password) > 1024:
                    raise ValueError()
                with _LOCK:
                    if now < _BLOCKED_UNTIL:
                        raise ValueError()
                    hashed = json.loads(AUTH_FILE.read_text(encoding="utf8"))["hash"]
                    try:
                        pwhash.argon2id.verify(hashed.encode(), password.encode())
                    except (ValueError, CryptoError):
                        _FAILURES += 1
                        if _FAILURES >= 5:
                            _BLOCKED_UNTIL = now + 60
                        raise ValueError() from None
                    _FAILURES = 0
                    token = secrets.token_urlsafe(32)
                    _SESSIONS[token] = now + 900
                result = JSONResponse(
                    {"ok": True}, headers={"Cache-Control": "no-store"}
                )
                result.set_cookie(
                    COOKIE, token, httponly=True, samesite="strict", max_age=900
                )
                return await result(scope, receive, send)
            except (ValueError, TypeError, KeyError, AttributeError, OSError):
                return await response("Authentification refusée.", 401)(
                    scope, receive, send
                )
            finally:
                from nacl._sodium import ffi, lib

                if raw:
                    lib.sodium_memzero(ffi.from_buffer(raw), len(raw))
        if configured and not authorized:
            result = (
                HTMLResponse(LOGIN_HTML, headers={"Cache-Control": "no-store"})
                if path == "/panneau"
                else response("Connexion administrateur requise.", 401)
            )
            return await result(scope, receive, send)

        async def no_cache(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"cache-control"
                ] + [(b"cache-control", b"no-store")]
            await send(message)

        return await self.app(scope, receive, no_cache)

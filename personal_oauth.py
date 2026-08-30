"""Single-user OAuth 2.1 authorization server for the hosted Kerr QNM MCP service.

This intentionally supports only OpenAI's stable ChatGPT client metadata document.
It is designed for a private, personal deployment rather than a public multi-user
plugin directory listing.
"""

from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request as URLRequest, urlopen

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response


SCOPE = "kerr-qnm:workspace"
CHATGPT_CLIENT_ID = "https://chatgpt.com/oauth/client.json"
CHATGPT_REDIRECT_URI = "https://chatgpt.com/connector_platform_oauth_redirect"
ACCESS_TOKEN_TTL_SECONDS = 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
AUTH_CODE_TTL_SECONDS = 5 * 60
MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW_SECONDS = 5 * 60


@dataclass(frozen=True)
class AuthorizationCode:
    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str
    scope: str
    expires_at: int


_authorization_codes: dict[str, AuthorizationCode] = {}
_failed_logins: deque[float] = deque()
_used_refresh_tokens: dict[str, int] = {}
_client_metadata_cache: tuple[float, dict[str, Any]] | None = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def public_base_url() -> str:
    value = os.environ.get("KERR_QNM_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("KERR_QNM_PUBLIC_BASE_URL is not configured")
    parts = urlsplit(value)
    allow_http = os.environ.get("KERR_QNM_ALLOW_HTTP_OAUTH") == "1"
    if (
        (parts.scheme != "https" and not allow_http)
        or not parts.netloc
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise RuntimeError("KERR_QNM_PUBLIC_BASE_URL must be a canonical HTTPS origin")
    return value


def resource_identifier() -> str:
    return f"{public_base_url()}/mcp"


def oauth_is_configured() -> bool:
    try:
        public_base_url()
    except RuntimeError:
        return False
    password = os.environ.get("KERR_QNM_OAUTH_PASSWORD", "").encode("utf-8")
    signing_secret = os.environ.get("KERR_QNM_OAUTH_SIGNING_SECRET", "").encode("utf-8")
    return len(password) >= 32 and len(signing_secret) >= 32


def protected_resource_metadata() -> JSONResponse:
    try:
        base = public_base_url()
    except RuntimeError as exc:
        return JSONResponse({"error": "server_error", "error_description": str(exc)}, status_code=503)
    return JSONResponse(
        {
            "resource": resource_identifier(),
            "authorization_servers": [base],
            "scopes_supported": [SCOPE],
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{base}/oauth/about",
        }
    )


def authorization_server_metadata() -> JSONResponse:
    try:
        base = public_base_url()
    except RuntimeError as exc:
        return JSONResponse({"error": "server_error", "error_description": str(exc)}, status_code=503)
    return JSONResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "authorization_response_iss_parameter_supported": True,
            "client_id_metadata_document_supported": True,
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "response_types_supported": ["code"],
            "scopes_supported": [SCOPE],
        }
    )


def about_page() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kerr QNM Toolkit authorization</title></head><body>
<main><h1>Kerr QNM Toolkit</h1><p>This private MCP service can inspect, edit,
test, and execute code in its persistent Julia/Python solver workspace.</p>
<p>Access is limited to the owner through an OAuth 2.1 authorization-code flow
with PKCE.</p></main></body></html>""",
        headers=_html_security_headers(),
    )


def _html_security_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


def _oauth_json_error(error: str, description: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _append_query(url: str, values: dict[str, str]) -> str:
    parts = urlsplit(url)
    existing = parse_qs(parts.query, keep_blank_values=True)
    flattened = {key: item[-1] for key, item in existing.items() if item}
    flattened.update(values)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(flattened), parts.fragment))


def _authorization_error(redirect_uri: str, state: str, error: str, description: str) -> Response:
    if redirect_uri != CHATGPT_REDIRECT_URI:
        return _oauth_json_error(error, description)
    values = {"error": error, "error_description": description, "iss": public_base_url()}
    if state:
        values["state"] = state
    return RedirectResponse(_append_query(redirect_uri, values), status_code=302)


def _requested_value(values: dict[str, list[str]], key: str) -> str:
    items = values.get(key, [])
    return items[-1] if items else ""


def _validate_authorization(values: dict[str, list[str]]) -> tuple[str, str, str, str, str, str] | Response:
    client_id = _requested_value(values, "client_id")
    redirect_uri = _requested_value(values, "redirect_uri")
    state = _requested_value(values, "state")
    resource = _requested_value(values, "resource")
    scope = _requested_value(values, "scope") or SCOPE
    challenge = _requested_value(values, "code_challenge")
    if _requested_value(values, "response_type") != "code":
        return _authorization_error(redirect_uri, state, "unsupported_response_type", "Only response_type=code is supported")
    if client_id != CHATGPT_CLIENT_ID:
        return _oauth_json_error("unauthorized_client", "Only the stable ChatGPT OAuth client is allowed")
    if redirect_uri != CHATGPT_REDIRECT_URI:
        return _oauth_json_error("invalid_request", "The redirect_uri is not allowlisted")
    if _requested_value(values, "code_challenge_method") != "S256" or not (43 <= len(challenge) <= 128):
        return _authorization_error(redirect_uri, state, "invalid_request", "A valid S256 PKCE challenge is required")
    if resource != resource_identifier():
        return _authorization_error(redirect_uri, state, "invalid_target", "The resource parameter does not match this MCP server")
    scopes = set(scope.split())
    if not scopes or not scopes.issubset({SCOPE}):
        return _authorization_error(redirect_uri, state, "invalid_scope", "The requested scope is not supported")
    return client_id, redirect_uri, state, resource, scope, challenge


def _fetch_chatgpt_client_metadata() -> dict[str, Any]:
    global _client_metadata_cache
    now = time.time()
    if _client_metadata_cache and now - _client_metadata_cache[0] < 3600:
        return _client_metadata_cache[1]
    request = URLRequest(CHATGPT_CLIENT_ID, headers={"Accept": "application/json", "User-Agent": "Kerr-QNM-Toolkit/1.1"})
    with urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError("ChatGPT client metadata could not be verified")
        body = response.read(64 * 1024 + 1)
    if len(body) > 64 * 1024:
        raise ValueError("ChatGPT client metadata is too large")
    metadata = json.loads(body)
    if metadata.get("client_id") != CHATGPT_CLIENT_ID:
        raise ValueError("ChatGPT client metadata has an unexpected client_id")
    if CHATGPT_REDIRECT_URI not in metadata.get("redirect_uris", []):
        raise ValueError("ChatGPT client metadata does not allow the stable redirect URI")
    methods = metadata.get("token_endpoint_auth_methods_supported", [])
    if "none" not in methods and metadata.get("token_endpoint_auth_method") != "none":
        raise ValueError("ChatGPT client metadata does not support public-client token exchange")
    _client_metadata_cache = (now, metadata)
    return metadata


def _prune_login_failures(now: float) -> None:
    while _failed_logins and now - _failed_logins[0] > FAILED_LOGIN_WINDOW_SECONDS:
        _failed_logins.popleft()


def _login_form(values: dict[str, list[str]], error: str = "", status_code: int = 200) -> HTMLResponse:
    hidden = []
    for key in ("response_type", "client_id", "redirect_uri", "state", "resource", "scope", "code_challenge", "code_challenge_method"):
        value = _requested_value(values, key)
        hidden.append(f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value, quote=True)}">')
    message = f'<p role="alert" class="error">{html.escape(error)}</p>' if error else ""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize Kerr QNM Toolkit</title><style>
body{{font:16px system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0}}
main{{max-width:34rem;margin:8vh auto;padding:2rem;background:#161b22;border:1px solid #30363d;border-radius:12px}}
input,button{{box-sizing:border-box;width:100%;padding:.8rem;margin-top:.5rem;border-radius:7px}}
input{{background:#0d1117;color:#e6edf3;border:1px solid #8b949e}}button{{background:#238636;color:white;border:0;font-weight:650;cursor:pointer}}
.error{{color:#ff7b72}}small{{color:#8b949e}}</style></head><body><main>
<h1>Authorize Kerr QNM Toolkit</h1><p>ChatGPT is requesting access to inspect, edit, test, and run code in your private persistent Julia/Python solver workspace.</p>
{message}<form method="post" action="/oauth/authorize">{''.join(hidden)}
<label for="password">Toolkit password</label><input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Authorize ChatGPT</button></form>
<p><small>This grants the single <code>{html.escape(SCOPE)}</code> scope. Nothing runs on your PC.</small></p>
</main></body></html>"""
    return HTMLResponse(document, status_code=status_code, headers=_html_security_headers())


async def authorize(request: Request) -> Response:
    if request.method == "GET":
        values = {key: request.query_params.getlist(key) for key in request.query_params}
        validated = _validate_authorization(values)
        if isinstance(validated, Response):
            return validated
        try:
            _fetch_chatgpt_client_metadata()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _oauth_json_error("temporarily_unavailable", f"Could not verify ChatGPT client metadata: {exc}", 503)
        if not oauth_is_configured():
            return _oauth_json_error("server_error", "OAuth secrets are not configured", 503)
        return _login_form(values)

    body = await request.body()
    if len(body) > 32 * 1024:
        return _oauth_json_error("invalid_request", "Request body is too large", 413)
    values = parse_qs(body.decode("utf-8", errors="strict"), keep_blank_values=True)
    validated = _validate_authorization(values)
    if isinstance(validated, Response):
        return validated
    if not oauth_is_configured():
        return _oauth_json_error("server_error", "OAuth secrets are not configured", 503)

    now = time.time()
    _prune_login_failures(now)
    if len(_failed_logins) >= MAX_FAILED_LOGINS:
        return _login_form(values, "Too many failed attempts. Wait five minutes and try again.", 429)
    password = _requested_value(values, "password")
    expected = os.environ.get("KERR_QNM_OAUTH_PASSWORD", "")
    if not hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
        _failed_logins.append(now)
        return _login_form(values, "Incorrect password.", 401)
    _failed_logins.clear()

    client_id, redirect_uri, state, resource, scope, challenge = validated
    code = secrets.token_urlsafe(32)
    _authorization_codes[code] = AuthorizationCode(
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        resource=resource,
        scope=scope,
        expires_at=int(now) + AUTH_CODE_TTL_SECONDS,
    )
    values_out = {"code": code, "iss": public_base_url()}
    if state:
        values_out["state"] = state
    return RedirectResponse(_append_query(redirect_uri, values_out), status_code=302)


def _sign_token(token_type: str, client_id: str, resource: str, scope: str, ttl_seconds: int) -> str:
    now = int(time.time())
    claims = {
        "typ": token_type,
        "iss": public_base_url(),
        "aud": resource,
        "sub": "kerr-qnm-owner",
        "client_id": client_id,
        "scope": scope,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": secrets.token_urlsafe(16),
    }
    payload = _b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    secret = os.environ.get("KERR_QNM_OAUTH_SIGNING_SECRET", "").encode("utf-8")
    signature = _b64url(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())
    return f"kq1.{payload}.{signature}"


def _verify_token(token: str, token_type: str) -> dict[str, Any] | None:
    try:
        prefix, payload, supplied_signature = token.split(".", 2)
        if prefix != "kq1":
            return None
        secret = os.environ.get("KERR_QNM_OAUTH_SIGNING_SECRET", "").encode("utf-8")
        if not secret:
            return None
        expected_signature = _b64url(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        claims = json.loads(_b64url_decode(payload))
        if claims.get("typ") != token_type or claims.get("iss") != public_base_url():
            return None
        if claims.get("aud") != resource_identifier() or int(claims.get("exp", 0)) <= int(time.time()):
            return None
        if SCOPE not in str(claims.get("scope", "")).split():
            return None
        return claims
    except (ValueError, TypeError, json.JSONDecodeError, RuntimeError):
        return None


def validate_access_token(token: str) -> bool:
    return _verify_token(token, "access") is not None


def _token_success(client_id: str, resource: str, scope: str) -> JSONResponse:
    return JSONResponse(
        {
            "access_token": _sign_token("access", client_id, resource, scope, ACCESS_TOKEN_TTL_SECONDS),
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "refresh_token": _sign_token("refresh", client_id, resource, scope, REFRESH_TOKEN_TTL_SECONDS),
            "scope": scope,
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def token(request: Request) -> JSONResponse:
    body = await request.body()
    if len(body) > 32 * 1024:
        return _oauth_json_error("invalid_request", "Request body is too large", 413)
    try:
        values = parse_qs(body.decode("utf-8", errors="strict"), keep_blank_values=True)
    except UnicodeDecodeError:
        return _oauth_json_error("invalid_request", "Request body must be UTF-8")
    grant_type = _requested_value(values, "grant_type")
    client_id = _requested_value(values, "client_id")
    resource = _requested_value(values, "resource")
    if client_id != CHATGPT_CLIENT_ID:
        return _oauth_json_error("invalid_client", "Unknown OAuth client", 401)
    if resource != resource_identifier():
        return _oauth_json_error("invalid_target", "The resource parameter does not match this MCP server")

    if grant_type == "authorization_code":
        code_value = _requested_value(values, "code")
        code = _authorization_codes.pop(code_value, None)
        if not code or code.expires_at <= int(time.time()):
            return _oauth_json_error("invalid_grant", "The authorization code is invalid or expired")
        if code.client_id != client_id or code.redirect_uri != _requested_value(values, "redirect_uri") or code.resource != resource:
            return _oauth_json_error("invalid_grant", "The authorization code binding does not match")
        verifier = _requested_value(values, "code_verifier")
        if not (43 <= len(verifier) <= 128):
            return _oauth_json_error("invalid_grant", "The PKCE verifier is invalid")
        try:
            encoded_verifier = verifier.encode("ascii", errors="strict")
        except UnicodeEncodeError:
            return _oauth_json_error("invalid_grant", "The PKCE verifier must be ASCII")
        challenge = _b64url(hashlib.sha256(encoded_verifier).digest())
        if not hmac.compare_digest(challenge, code.code_challenge):
            return _oauth_json_error("invalid_grant", "The PKCE verifier does not match")
        return _token_success(client_id, resource, code.scope)

    if grant_type == "refresh_token":
        claims = _verify_token(_requested_value(values, "refresh_token"), "refresh")
        if not claims or claims.get("client_id") != client_id:
            return _oauth_json_error("invalid_grant", "The refresh token is invalid or expired")
        now = int(time.time())
        for jti, expiration in list(_used_refresh_tokens.items()):
            if expiration <= now:
                _used_refresh_tokens.pop(jti, None)
        jti = str(claims.get("jti", ""))
        if not jti or jti in _used_refresh_tokens:
            return _oauth_json_error("invalid_grant", "The refresh token has already been used")
        _used_refresh_tokens[jti] = int(claims["exp"])
        requested_scope = _requested_value(values, "scope") or str(claims.get("scope", ""))
        if not set(requested_scope.split()).issubset(set(str(claims.get("scope", "")).split())):
            return _oauth_json_error("invalid_scope", "Refresh cannot increase the granted scope")
        return _token_success(client_id, resource, requested_scope)

    return _oauth_json_error("unsupported_grant_type", "Only authorization_code and refresh_token are supported")


class OAuthBearerGate:
    """Protect /mcp with OAuth access tokens, with a static-token smoke-test fallback."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/mcp":
            await self.app(scope, receive, send)
            return
        if os.environ.get("KERR_QNM_INSECURE_ALLOW_ANONYMOUS") == "1":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        token_value = supplied[7:] if supplied.startswith("Bearer ") else ""
        static_token = os.environ.get("KERR_QNM_MCP_BEARER_TOKEN", "")
        static_valid = bool(static_token) and hmac.compare_digest(token_value, static_token)
        oauth_valid = bool(token_value) and validate_access_token(token_value)
        if static_valid or oauth_valid:
            await self.app(scope, receive, send)
            return
        if not static_token and not oauth_is_configured():
            response = PlainTextResponse("MCP authentication is not configured.", status_code=503)
            await response(scope, receive, send)
            return
        try:
            metadata_url = f"{public_base_url()}/.well-known/oauth-protected-resource"
        except RuntimeError:
            metadata_url = ""
        challenge = f'Bearer resource_metadata="{metadata_url}", scope="{SCOPE}"'
        response = PlainTextResponse("Unauthorized", status_code=401, headers={"WWW-Authenticate": challenge})
        await response(scope, receive, send)

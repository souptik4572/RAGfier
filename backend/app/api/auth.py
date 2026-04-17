from __future__ import annotations

import base64
import json
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Header, status

from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import (
    AuthTokenResponse,
    TenantLoginRequest,
    TenantSignupRequest,
)
from app.utils.api_errors import raise_api_error, with_message
from app.utils.integration_resolver import get_or_create_default_integration
from app.utils.logger import get_logger
from app.utils.messages import get_message

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])

# Module-level httpx client so signup/login calls reuse a single TCP/TLS
# pool instead of paying the handshake tax on every Supabase request.
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=15.0)
    return _HTTP_CLIENT


async def reset_http_client() -> None:
    """Close the shared client — primarily for test teardown."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
        await _HTTP_CLIENT.aclose()
    _HTTP_CLIENT = None


class SupabaseAuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class AuthContext:
    """Resolved identity attached to an authenticated request."""

    def __init__(self, tenant_id: str, user_id: Optional[str] = None) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id


def _decode_jwt_claims(token: str) -> dict:
    """Decode JWT payload *without* verifying the signature.

    Signature verification is delegated to Supabase (the `anon` and
    `authenticated` keys enforce RLS on the DB side). This helper only
    extracts `app_metadata.organization_id` for routing.
    """
    try:
        _, payload_b64, _ = token.split(".")
    except ValueError as exc:
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "auth.malformed_jwt")
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception as exc:
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "auth.invalid_jwt_payload")
    if not isinstance(payload, dict):
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "auth.jwt_payload_not_object")
    return payload


async def get_auth_context(
    authorization: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None),
) -> AuthContext:
    """Extract tenant identity from the `Authorization: Bearer` header.

    An `X-Tenant-Id` header override is accepted to ease local testing;
    production deployments should rely exclusively on the JWT.
    """
    if x_tenant_id:
        return AuthContext(tenant_id=x_tenant_id)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "auth.missing_bearer_token")
    token = authorization.split(" ", 1)[1].strip()
    claims = _decode_jwt_claims(token)
    app_metadata = claims.get("app_metadata") or {}
    tenant_id = app_metadata.get("organization_id")
    if not tenant_id:
        raise_api_error(status.HTTP_403_FORBIDDEN, "auth.missing_organization_id")
    user_id = claims.get("sub")
    return AuthContext(tenant_id=str(tenant_id), user_id=user_id)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-")


def _require_auth_settings() -> None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise_api_error(500, "auth.service_role_not_configured")
    if not settings.supabase_anon_key:
        raise_api_error(500, "auth.anon_not_configured")


def _extract_error_detail(body: object) -> str:
    if isinstance(body, dict):
        for key in ("msg", "message", "error_description", "error"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    return "Supabase authentication request failed."


def _raise_for_supabase_error(status_code: int, body: object) -> None:
    detail = _extract_error_detail(body)
    if status_code == 401:
        raise SupabaseAuthError(401, get_message("auth.invalid_credentials"))
    if "already registered" in detail.lower():
        raise SupabaseAuthError(409, get_message("auth.email_in_use"))
    if "duplicate key" in detail.lower() or "duplicate" in detail.lower():
        raise SupabaseAuthError(409, detail)
    raise SupabaseAuthError(502, detail)


async def _request_supabase(
    method: str,
    path: str,
    *,
    api_key: str,
    bearer_token: Optional[str] = None,
    json_body: Optional[dict] = None,
    extra_headers: Optional[dict[str, str]] = None,
) -> object:
    settings = get_settings()
    url = f"{settings.supabase_url.rstrip('/')}{path}"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if extra_headers:
        headers.update(extra_headers)

    client = _get_http_client()
    response = await client.request(method, url, headers=headers, json=json_body)

    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.is_error:
        _raise_for_supabase_error(response.status_code, body)
    return body


async def _create_tenant(name: str, slug: str) -> dict:
    settings = get_settings()
    body = await _request_supabase(
        "POST",
        "/rest/v1/tenants",
        api_key=settings.supabase_service_role_key,
        bearer_token=settings.supabase_service_role_key,
        json_body={"name": name, "slug": slug, "plan": "free", "settings": {}},
        extra_headers={"Prefer": "return=representation"},
    )
    if not isinstance(body, list) or not body:
        raise SupabaseAuthError(502, "Tenant creation returned no row.")
    tenant = body[0]
    if not isinstance(tenant, dict) or not tenant.get("id"):
        raise SupabaseAuthError(502, "Tenant creation returned an invalid row.")
    return tenant


async def _create_auth_user(email: str, password: str, tenant_id: str) -> dict:
    settings = get_settings()
    body = await _request_supabase(
        "POST",
        "/auth/v1/admin/users",
        api_key=settings.supabase_service_role_key,
        bearer_token=settings.supabase_service_role_key,
        json_body={
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"organization_id": tenant_id},
        },
    )
    if not isinstance(body, dict):
        raise SupabaseAuthError(502, "User creation returned an invalid response.")
    return body


async def _password_sign_in(email: str, password: str) -> dict:
    settings = get_settings()
    body = await _request_supabase(
        "POST",
        "/auth/v1/token?grant_type=password",
        api_key=settings.supabase_anon_key,
        json_body={"email": email, "password": password},
    )
    if not isinstance(body, dict) or not body.get("access_token"):
        raise SupabaseAuthError(502, "Password sign-in returned no access token.")
    return body


def _build_token_response(body: dict, fallback_tenant_id: Optional[str] = None) -> AuthTokenResponse:
    tenant_id = fallback_tenant_id
    user = body.get("user")
    if isinstance(user, dict):
        app_metadata = user.get("app_metadata") or {}
        if isinstance(app_metadata, dict) and app_metadata.get("organization_id"):
            tenant_id = str(app_metadata["organization_id"])
    if not tenant_id:
        claims = _decode_jwt_claims(str(body["access_token"]))
        app_metadata = claims.get("app_metadata") or {}
        tenant_id = app_metadata.get("organization_id")
    if not tenant_id:
        raise SupabaseAuthError(502, "JWT is missing app_metadata.organization_id.")

    user_id = user.get("id") if isinstance(user, dict) else None
    email = user.get("email") if isinstance(user, dict) else None
    return AuthTokenResponse(
        message="",
        access_token=str(body["access_token"]),
        token_type=str(body.get("token_type") or "bearer"),
        expires_in=body.get("expires_in"),
        refresh_token=body.get("refresh_token"),
        tenant_id=tenant_id,
        user_id=str(user_id) if user_id else None,
        email=str(email) if email else None,
    )


@router.post("/auth/signup", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def signup_tenant(payload: TenantSignupRequest) -> AuthTokenResponse:
    _require_auth_settings()
    tenant_slug = payload.tenant_slug or _slugify(payload.tenant_name)
    if not tenant_slug:
        raise_api_error(422, "auth.tenant_slug_invalid")

    try:
        tenant = await _create_tenant(payload.tenant_name, tenant_slug)
        tenant_id = str(tenant["id"])
        await _create_auth_user(payload.email, payload.password, tenant_id)
        token_body = await _password_sign_in(payload.email, payload.password)
        response = _build_token_response(token_body, fallback_tenant_id=tenant_id)
        # Ensure the default global integration exists before returning.
        db_client = get_service_client()
        get_or_create_default_integration(db_client, tenant_id)
    except SupabaseAuthError as exc:
        logger.error(
            "auth.signup_failed",
            tenant_slug=tenant_slug,
            email=payload.email,
            error=exc.detail,
        )
        raise_api_error(exc.status_code, "auth.signup_failed", detail=exc.detail)

    logger.info(
        "auth.signup_succeeded",
        tenant_id=str(response.tenant_id),
        email=payload.email,
    )
    return with_message(response, "auth.signup_succeeded")


@router.post("/auth/login", response_model=AuthTokenResponse)
async def login_tenant(payload: TenantLoginRequest) -> AuthTokenResponse:
    _require_auth_settings()
    try:
        token_body = await _password_sign_in(payload.email, payload.password)
        response = _build_token_response(token_body)
    except SupabaseAuthError as exc:
        logger.error("auth.login_failed", email=payload.email, error=exc.detail)
        raise_api_error(exc.status_code, "auth.login_failed", detail=exc.detail)

    logger.info(
        "auth.login_succeeded",
        tenant_id=str(response.tenant_id),
        email=payload.email,
    )
    return with_message(response, "auth.login_succeeded")

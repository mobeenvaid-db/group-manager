"""
Group Manager — Databricks App
Lets account admins delegate group membership management to designated group managers.

Auth pattern:
- User identity: from forwarded headers (X-Forwarded-Email, X-Forwarded-User). No OBO for IAM/SCIM.
- Groups / SCIM / Access Control: all called with the app's service principal (PAT or OAuth).
- OBO is only used for data/compute features with OBO scopes (e.g. SQL, files); this app does not use OBO for groups.
"""

import os
import time
import threading
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
ACCOUNT_ID = os.environ.get("DATABRICKS_ACCOUNT_ID", "")
SP_CLIENT_ID = os.environ.get("ACCOUNT_SP_CLIENT_ID", "")
SP_CLIENT_SECRET = os.environ.get("ACCOUNT_SP_CLIENT_SECRET", "")
# Optional: use a PAT as the app's service principal instead of OAuth
SP_PAT = os.environ.get("ACCOUNT_SP_PAT", "").strip() or os.environ.get("DATABRICKS_APP_TOKEN", "").strip()

ACCOUNTS_BASE = f"https://accounts.cloud.databricks.com/api/2.0/accounts/{ACCOUNT_ID}"

# Workspace proxy: Account Groups SCIM (called with SP token)
WORKSPACE_ACCOUNT_SCIM_BASE = f"{DATABRICKS_HOST}/api/2.0/account/scim/v2" if DATABRICKS_HOST else ""

# Account Access Control (workspace proxy) — assign/revoke Group: Manager (SP token)
ACCESS_CONTROL_BASE = f"{DATABRICKS_HOST}/api/2.0/preview/accounts/access-control" if DATABRICKS_HOST else ""

# Role identifier for Group: Manager (from assignable roles on a group)
GROUP_MANAGER_ROLE = "roles/groups.manager"

# Ensure host has scheme before building URLs
if DATABRICKS_HOST and not DATABRICKS_HOST.startswith("http"):
    DATABRICKS_HOST = f"https://{DATABRICKS_HOST}"
WORKSPACE_ACCOUNT_SCIM_BASE = f"{DATABRICKS_HOST}/api/2.0/account/scim/v2" if DATABRICKS_HOST else ""
ACCESS_CONTROL_BASE = f"{DATABRICKS_HOST}/api/2.0/preview/accounts/access-control" if DATABRICKS_HOST else ""

# ---------------------------------------------------------------------------
# SP Token (required for groups/SCIM) — PAT or OAuth
# ---------------------------------------------------------------------------

_sp_token: Optional[str] = None
_sp_token_expiry: float = 0
_sp_token_lock = threading.Lock()


def _sp_configured() -> bool:
    """True if app has a way to get an SP token (PAT or OAuth)."""
    return bool(SP_PAT) or (bool(SP_CLIENT_ID) and bool(SP_CLIENT_SECRET))


async def get_sp_token() -> Optional[str]:
    """Get the token used for Groups/SCIM/Access Control. PAT if set, else OAuth client_credentials. Raises 503 if not configured."""
    global _sp_token, _sp_token_expiry

    if SP_PAT:
        return SP_PAT

    if not SP_CLIENT_ID or not SP_CLIENT_SECRET:
        return None

    with _sp_token_lock:
        if _sp_token and time.time() < _sp_token_expiry:
            return _sp_token

    token_url = f"https://accounts.cloud.databricks.com/oidc/accounts/{ACCOUNT_ID}/v1/token"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": SP_CLIENT_ID,
                "client_secret": SP_CLIENT_SECRET,
                "scope": "all-apis",
            },
        )
        if r.status_code != 200:
            return None
        body = r.json()

    with _sp_token_lock:
        _sp_token = body["access_token"]
        _sp_token_expiry = time.time() + body.get("expires_in", 3600) - 120

    return _sp_token


async def require_sp_token() -> str:
    """Return SP token for Groups/SCIM. Raises 503 if SP not configured."""
    token = await get_sp_token()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="Group operations require a service principal. Set ACCOUNT_SP_PAT or ACCOUNT_SP_CLIENT_ID and ACCOUNT_SP_CLIENT_SECRET.",
        )
    return token


# ---------------------------------------------------------------------------
# Identity from forwarded headers (no OBO for IAM/SCIM)
# ---------------------------------------------------------------------------

def get_current_user_from_headers(request: Request) -> dict:
    """Identify the calling user from headers set by Databricks when forwarding to the app.
    Uses X-Forwarded-Email, X-Forwarded-User. Does not call IAM/SCIM with OBO.
    """
    email = request.headers.get("X-Forwarded-Email", "").strip()
    user = request.headers.get("X-Forwarded-User", "").strip()
    # Prefer email for display and for matching Group: Manager principals (often stored as users/email)
    if not email and user and "@" in user:
        email = user
    if not user and email:
        user = email
    if not email and not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Access this app through the Databricks workspace URL (X-Forwarded-Email/X-Forwarded-User required).",
        )
    return {
        "email": email or user,
        "user_name": user or email,
        "sub": user or email,  # id may be resolved later if needed
        "name": email or user,
    }


async def check_is_admin(user_email: str) -> bool:
    """Check whether the user is an account admin via the Account SCIM Users API (SP token).
    Returns False if SP is not configured or user is not an account admin."""
    sp_token = await get_sp_token()
    if not sp_token:
        return False

    async with httpx.AsyncClient() as client:
        # Try by userName (email) and by displayName if needed
        r = await client.get(
            f"{ACCOUNTS_BASE}/scim/v2/Users",
            params={"filter": f'userName eq "{user_email}"'},
            headers={"Authorization": f"Bearer {sp_token}"},
        )
        if r.status_code != 200:
            return False
        resources = r.json().get("Resources", [])
        if not resources:
            return False
        roles = resources[0].get("roles", [])
        return any(role.get("value") == "account_admin" for role in roles)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Group Manager")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Debug (temporary — remove after auth is confirmed working)
# ---------------------------------------------------------------------------

def _redact_headers(headers: dict) -> dict:
    """Return a copy of headers with sensitive values redacted (for debug only)."""
    sensitive = {"authorization", "x-forwarded-access-token", "cookie"}
    return {
        k: "[REDACTED]" if k.lower() in sensitive else v
        for k, v in headers.items()
    }


@app.get("/api/debug")
async def debug(request: Request):
    """Headers and config for troubleshooting. Sensitive headers redacted. Remove in production."""
    return {
        "databricks_host":   DATABRICKS_HOST,
        "account_id_set":   bool(ACCOUNT_ID),
        "sp_configured":    _sp_configured(),
        "sp_client_id_set": bool(SP_CLIENT_ID),
        "sp_pat_set":       bool(SP_PAT),
        "x_forwarded_email": request.headers.get("X-Forwarded-Email"),
        "x_forwarded_user": request.headers.get("X-Forwarded-User"),
        "all_headers":      _redact_headers(dict(request.headers)),
        "auth_debug":       "See GET /api/debug/auth for auth-pattern verification.",
    }


@app.get("/api/debug/auth")
async def debug_auth(request: Request):
    """
    Verify auth pattern without calling any APIs:
    - Identity from forwarded headers (X-Forwarded-Email, X-Forwarded-User).
    - Groups/SCIM use service principal (PAT or OAuth); OBO not used for IAM/SCIM.
    - OBO token presence only (for data/compute if you add those features).
    """
    obo_raw = request.headers.get("X-Forwarded-Access-Token", "")
    email = request.headers.get("X-Forwarded-Email", "").strip()
    user = request.headers.get("X-Forwarded-User", "").strip()

    # Identity this app uses (from headers only)
    identity_from_headers = {
        "email":     email or user or None,
        "user_name": user or email or None,
        "sub":       user or email or None,
    }
    if not identity_from_headers["email"] and not identity_from_headers["user_name"]:
        identity_from_headers["_note"] = "Missing; set X-Forwarded-Email and/or X-Forwarded-User when forwarding to the app."

    # SP source for groups/SCIM
    sp_source = "pat" if SP_PAT else ("oauth" if (SP_CLIENT_ID and SP_CLIENT_SECRET) else "none")

    return {
        "pattern": {
            "identity_source":       "forwarded_headers",
            "groups_scim_auth":      "service_principal",
            "obo_used_for":          "data_compute_only_if_you_add_those_features",
            "obo_not_used_for":      "iam_scim_groups_access_control",
        },
        "forwarded_headers": {
            "X_Forwarded_Email":           email or None,
            "X_Forwarded_User":            user or None,
            "X_Forwarded_Access_Token":    "present" if obo_raw else "absent",
            "X_Forwarded_Access_Token_len": len(obo_raw) if obo_raw else 0,
        },
        "identity_used_by_app": identity_from_headers,
        "service_principal": {
            "configured": _sp_configured(),
            "source":     sp_source,
            "used_for":  "groups_scim_access_control_user_search",
        },
        "checks": {
            "identity_ok":    bool(email or user),
            "sp_ok":          _sp_configured(),
            "ready_for_app":  bool(email or user) and _sp_configured(),
        },
    }


# ---------------------------------------------------------------------------
# Auth / Identity
# ---------------------------------------------------------------------------

@app.get("/api/me")
async def me(request: Request):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or user.get("sub", "")
    user_id = user.get("sub", "")
    user_name = user.get("name", user_email)
    is_admin = await check_is_admin(user_email) if _sp_configured() else False
    return {
        "user_id": user_id,
        "email": user_email,
        "name": user_name,
        "is_admin": is_admin,
        "managed_group_ids": [],
    }


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@app.get("/api/groups")
async def list_groups(request: Request, q: Optional[str] = None, startIndex: int = 1, count: int = 100):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or ""
    token = await require_sp_token()

    # List all groups with SP (paginate loosely)
    params = {"startIndex": 1, "count": 500}
    if q:
        params["filter"] = f'displayName co "{q}"'

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{WORKSPACE_ACCOUNT_SCIM_BASE}/Groups",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to list groups"))
        data = r.json()
    groups = data.get("Resources") or []
    total = data.get("totalResults", len(groups))

    is_admin = await check_is_admin(user_email)
    # Filter to groups this user is allowed to manage (admin or Group: Manager)
    allowed_ids = set()
    for g in groups:
        group_id = g.get("id", "")
        name = _group_rule_set_name(group_id)
        try:
            rs = await _get_rule_set(token, name)
        except HTTPException as e:
            if e.status_code == 404:
                continue
            raise
        if is_admin or _user_is_manager_for_group(user_email, rs.get("grant_rules")):
            allowed_ids.add(group_id)

    filtered = [g for g in groups if g.get("id") in allowed_ids]
    # Apply client-requested pagination slice
    start = max(0, startIndex - 1)
    end = start + count
    page = filtered[start:end]
    return {"Resources": page, "totalResults": len(filtered), "startIndex": startIndex, "count": len(page)}


async def _user_can_manage_group(token: str, user_email: str, group_id: str) -> bool:
    """True if user is account admin or Group: Manager for this group."""
    if await check_is_admin(user_email):
        return True
    name = _group_rule_set_name(group_id)
    try:
        rs = await _get_rule_set(token, name)
    except HTTPException as e:
        if e.status_code == 404:
            return False
        raise
    return _user_is_manager_for_group(user_email, rs.get("grant_rules"))


@app.get("/api/groups/{group_id}")
async def get_group(request: Request, group_id: str):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or ""
    token = await require_sp_token()

    can = await _user_can_manage_group(token, user_email, group_id)
    if not can:
        raise HTTPException(status_code=403, detail="You do not have permission to manage this group.")

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{WORKSPACE_ACCOUNT_SCIM_BASE}/Groups/{group_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to get group"))
        return r.json()


# ---------------------------------------------------------------------------
# Group Members
# ---------------------------------------------------------------------------

class AddMemberRequest(BaseModel):
    user_id: str


@app.post("/api/groups/{group_id}/members")
async def add_member(request: Request, group_id: str, body: AddMemberRequest):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or ""
    token = await require_sp_token()

    can = await _user_can_manage_group(token, user_email, group_id)
    if not can:
        raise HTTPException(status_code=403, detail="You do not have permission to manage this group.")

    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {"op": "add", "path": "members", "value": [{"value": body.user_id}]}
        ],
    }

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{WORKSPACE_ACCOUNT_SCIM_BASE}/Groups/{group_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to add member"))
        return {"detail": "Member added successfully."}


@app.delete("/api/groups/{group_id}/members/{member_id}")
async def remove_member(request: Request, group_id: str, member_id: str):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or ""
    token = await require_sp_token()

    can = await _user_can_manage_group(token, user_email, group_id)
    if not can:
        raise HTTPException(status_code=403, detail="You do not have permission to manage this group.")

    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {"op": "remove", "path": f'members[value eq "{member_id}"]'}
        ],
    }

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{WORKSPACE_ACCOUNT_SCIM_BASE}/Groups/{group_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to remove member"))
        return {"detail": "Member removed successfully."}


def _err_detail(r: httpx.Response, prefix: str) -> str:
    try:
        return r.json().get("message") or r.json().get("detail") or r.text or prefix
    except Exception:
        return r.text or prefix


# ---------------------------------------------------------------------------
# Account Access Control — Group: Manager role (rule sets)
# ---------------------------------------------------------------------------

def _group_rule_set_name(group_id: str) -> str:
    return f"accounts/{ACCOUNT_ID}/groups/{group_id}/ruleSets/default"


async def _get_rule_set(token: str, name: str, etag: Optional[str] = None) -> dict:
    """GET rule set by name. Returns { name, etag, grant_rules } or raises."""
    params = {"name": name}
    if etag:
        params["etag"] = etag
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{ACCESS_CONTROL_BASE}/rule-sets",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to get rule set"))
        return r.json()


async def _update_rule_set(token: str, name: str, rule_set: dict) -> dict:
    """PUT rule set. rule_set must include name, etag, grant_rules."""
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{ACCESS_CONTROL_BASE}/rule-sets",
            json={"name": name, "rule_set": rule_set},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to update rule set"))
        return r.json() if r.content else {}


def _managers_from_grant_rules(grant_rules: list, group_id: str, group_display_name: str) -> list:
    """Extract Group: Manager principals from grant_rules into list of assignment dicts."""
    out = []
    for rule in grant_rules or []:
        if rule.get("role") != GROUP_MANAGER_ROLE:
            continue
        for principal in rule.get("principals") or []:
            # principal can be "users/123" or "users/email@domain.com"
            pid = principal.split("/", 1)[-1] if "/" in principal else principal
            out.append({
                "id": f"{group_id}:{pid}",
                "group_id": group_id,
                "group_display_name": group_display_name,
                "manager_id": pid,
                "manager_email": pid if "@" in pid else "",
                "manager_display_name": pid,
            })
    return out


def _user_is_manager_for_group(user_email: str, grant_rules: list) -> bool:
    """True if user_email is a Group: Manager principal in grant_rules (match by email or users/email)."""
    if not user_email or not grant_rules:
        return False
    needle = user_email.lower().strip()
    for rule in grant_rules or []:
        if rule.get("role") != GROUP_MANAGER_ROLE:
            continue
        for principal in rule.get("principals") or []:
            pid = principal.split("/", 1)[-1] if "/" in principal else principal
            if (pid or "").lower().strip() == needle:
                return True
    return False


# ---------------------------------------------------------------------------
# Group Manager Assignments (Account Access Control API)
# ---------------------------------------------------------------------------

class AssignManagerRequest(BaseModel):
    group_id: str
    group_display_name: Optional[str] = None
    manager_id: str
    manager_email: Optional[str] = None
    manager_display_name: Optional[str] = None


@app.get("/api/group-managers")
async def list_group_managers(request: Request):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or user.get("sub", "")
    is_admin = await check_is_admin(user_email)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only account admins can view all group manager assignments.")

    token = await require_sp_token()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{WORKSPACE_ACCOUNT_SCIM_BASE}/Groups",
            params={"count": 500},
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "Failed to list groups"))
        groups_data = r.json()
    groups = groups_data.get("Resources") or []

    assignments = []
    for g in groups:
        group_id = g.get("id", "")
        display_name = g.get("displayName", group_id)
        name = _group_rule_set_name(group_id)
        try:
            rs = await _get_rule_set(token, name)
        except HTTPException as e:
            if e.status_code == 404:
                continue  # No rule set for this group yet
            raise
        assignments.extend(_managers_from_grant_rules(
            rs.get("grant_rules"), group_id, display_name
        ))

    # Sort by group then manager for stable list
    assignments.sort(key=lambda a: (a["group_display_name"] or "", a["manager_email"] or a["manager_id"]))
    return assignments


@app.post("/api/group-managers")
async def assign_group_manager(request: Request, body: AssignManagerRequest):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or user.get("sub", "")
    is_admin = await check_is_admin(user_email)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only account admins can assign group managers.")

    token = await require_sp_token()
    name = _group_rule_set_name(body.group_id)
    principal = f"users/{body.manager_id}"

    try:
        rs = await _get_rule_set(token, name)
    except HTTPException as e:
        if e.status_code == 404:
            rs = {"name": name, "etag": "", "grant_rules": []}
        else:
            raise

    grant_rules = list(rs.get("grant_rules") or [])
    # Check if already present
    for rule in grant_rules:
        if rule.get("role") == GROUP_MANAGER_ROLE and principal in (rule.get("principals") or []):
            raise HTTPException(status_code=409, detail="This user is already a manager of this group.")

    # Add or extend the Group: Manager rule
    found = False
    for rule in grant_rules:
        if rule.get("role") == GROUP_MANAGER_ROLE:
            rule.setdefault("principals", []).append(principal)
            found = True
            break
    if not found:
        grant_rules.append({"role": GROUP_MANAGER_ROLE, "principals": [principal]})

    rule_set = {"name": name, "etag": rs.get("etag", ""), "grant_rules": grant_rules}
    await _update_rule_set(token, name, rule_set)
    return {"detail": "Manager assigned successfully."}


@app.delete("/api/group-managers/{assignment_id}")
async def revoke_group_manager_by_id(request: Request, assignment_id: str):
    """Revoke by composite id 'group_id:principal_id' (e.g. from list_group_managers)."""
    if ":" not in assignment_id:
        raise HTTPException(status_code=400, detail="Invalid assignment id. Use group_id:principal_id.")
    group_id, principal_id = assignment_id.split(":", 1)
    await _revoke_group_manager_impl(request, group_id, principal_id)
    return {"detail": "Manager assignment revoked."}


@app.delete("/api/groups/{group_id}/managers/{principal_id}")
async def revoke_group_manager(request: Request, group_id: str, principal_id: str):
    """Revoke Group: Manager role for principal on group."""
    await _revoke_group_manager_impl(request, group_id, principal_id)
    return {"detail": "Manager assignment revoked."}


async def _revoke_group_manager_impl(request: Request, group_id: str, principal_id: str):
    user = get_current_user_from_headers(request)
    user_email = user.get("email") or user.get("user_name") or user.get("sub", "")
    is_admin = await check_is_admin(user_email)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only account admins can revoke group manager assignments.")

    token = await require_sp_token()
    name = _group_rule_set_name(group_id)
    principal = f"users/{principal_id}"

    rs = await _get_rule_set(token, name)
    grant_rules = list(rs.get("grant_rules") or [])
    new_rules = []
    removed = False
    for rule in grant_rules:
        if rule.get("role") != GROUP_MANAGER_ROLE:
            new_rules.append(rule)
            continue
        principals = [p for p in (rule.get("principals") or []) if p != principal and p != principal_id]
        if len(principals) < len(rule.get("principals") or []):
            removed = True
        if principals:
            new_rules.append({"role": rule["role"], "principals": principals})
    if not removed:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    rule_set = {"name": name, "etag": rs.get("etag", ""), "grant_rules": new_rules}
    await _update_rule_set(token, name, rule_set)


# ---------------------------------------------------------------------------
# User Search
# ---------------------------------------------------------------------------

@app.get("/api/users/search")
async def search_users(request: Request, q: str = ""):
    get_current_user_from_headers(request)  # require identity
    token = await require_sp_token()

    # Workspace SCIM Users (SP token)
    params = {"count": 25}
    if q:
        params["filter"] = f'displayName co "{q}" or userName co "{q}"'

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{DATABRICKS_HOST}/api/2.0/preview/scim/v2/Users",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=_err_detail(r, "User search failed"))
        data = r.json()

    users = []
    for u in data.get("Resources", []):
        emails = u.get("emails", [])
        primary_email = ""
        for e in emails:
            if e.get("primary"):
                primary_email = e.get("value", "")
                break
        if not primary_email and emails:
            primary_email = emails[0].get("value", "")

        users.append({
            "id": u.get("id", ""),
            "userName": u.get("userName", ""),
            "displayName": u.get("displayName", u.get("userName", "")),
            "email": primary_email or u.get("userName", ""),
        })

    return {"Resources": users, "totalResults": data.get("totalResults", len(users))}


# ---------------------------------------------------------------------------
# Static files (React SPA)
# ---------------------------------------------------------------------------

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
_index_html = os.path.join(FRONTEND_DIST, "index.html")


class SPAMiddleware(BaseHTTPMiddleware):
    """Serve index.html for any non-API 404 so React Router handles the path.
    API routes (/api/*) always return their own responses — this middleware
    never intercepts them, avoiding the /{full_path:path} catch-all conflict.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if (
            response.status_code == 404
            and not request.url.path.startswith("/api/")
            and os.path.exists(_index_html)
        ):
            return FileResponse(_index_html)
        return response


app.add_middleware(SPAMiddleware)

# Serve built static assets (JS/CSS) — must come after middleware registration
if os.path.exists(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

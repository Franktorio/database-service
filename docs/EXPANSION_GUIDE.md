# Expansion Guide — Building Features Beyond the System Layer

Everything under `src/api/system/`, `src/services/system/`, and `src/models/**/system/` is **infrastructure**: authentication, API-key/user administration, rate limiting, backups, health checks. It is designed to be depended *on*, not extended *in place*. This guide walks through adding real, product-specific functionality **alongside** it, reusing the auth/rate-limit/caching primitives that already exist.

Worked example used throughout: a **`notes`** feature — users can create and read short text notes, gated behind the existing API-key auth at a low permission level.

---

## Table of Contents

- [Ground rules](#ground-rules)
- [Where new code goes](#where-new-code-goes)
- [Step 1 — Define the table](#step-1--define-the-table)
- [Step 2 — Generate and apply the migration](#step-2--generate-and-apply-the-migration)
- [Step 3 — Write the CRUD layer](#step-3--write-the-crud-layer)
- [Step 4 — Define request/response models](#step-4--define-requestresponse-models)
- [Step 5 — Write routes and reuse existing auth](#step-5--write-routes-and-reuse-existing-auth)
- [Step 6 — Register the router](#step-6--register-the-router)
- [Choosing a permission model for your feature](#choosing-a-permission-model-for-your-feature)
- [Reusing rate limiting for your own resources](#reusing-rate-limiting-for-your-own-resources)
- [Adding user-facing (cookie) authentication](#adding-user-facing-cookie-authentication)
- [Configuration for your feature](#configuration-for-your-feature)
- [Testing your feature](#testing-your-feature)
- [Things to avoid](#things-to-avoid)

---

## Ground rules

1. **Never import from another feature's internals**, and never modify `src/**/system/**` to special-case your feature. If the system layer is genuinely missing a hook you need (e.g., a new decorator parameter), add it generically, not with an `if feature_name == "notes"` branch.
2. **Reuse, don't reimplement**, the primitives that already exist: `with_ip_block`, `api_key_authorized_factory`/`cookie_authorized_factory` (FastAPI `Depends()` dependencies), the Redis rate-limit/permission cache helpers, `with_session`, `Base`. Every one of these is generic and takes parameters (permission level, cache identifiers, etc.) — you should never need to write a new rate limiter or a new password hasher for a typical feature.
3. **One CRUD module per table**, following the conventions in [`docs/DATABASE.md`](DATABASE.md#crud-layer-conventions) — no direct SQLAlchemy queries in route handlers.
4. **Mirror the existing file layout** so the codebase stays predictable for the next contributor (see below).

## Where new code goes

Mirror the existing `system` structure, but under your own feature name instead of `system`:

```
src/
  api/
    <feature>/                     # e.g. src/api/notes/
      __init__.py
      models.py                    # Pydantic request/response models
      routes/
        __init__.py                # imports _get_routes/_post_routes/etc for side effects
        router.py                  # APIRouter(prefix="/api/notes", tags=["notes"])
        _get_routes.py
        _post_routes.py
        _patch_routes.py           # only if needed
        _delete_routes.py          # only if needed
  models/
    tables/
      <feature>/                   # e.g. src/models/tables/notes/
        note_table.py
    crud/
      <feature>/
        note_crud.py
```

This is exactly the shape `system` already uses (`api_db_endpoints`, `user_db_endpoints`) — new contributors familiar with one part of the codebase will immediately recognize the other.

---

## Step 1 — Define the table

`src/models/tables/notes/note_table.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)

    # Owner reference — reuse the existing users table rather than inventing
    # a parallel identity concept.
    username: Mapped[str] = mapped_column(
        ForeignKey("users.username", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        init=False,
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
```

This follows every convention already established in `src/models/tables/system/*`: `MappedAsDataclass`-friendly `Base`, DB-generated timestamps, `ondelete="CASCADE"` tying feature data to the existing `users` table's lifecycle (deleting a user cleans up their notes automatically, exactly like `auth_cookies` does today).

## Step 2 — Generate and apply the migration

Alembic's target metadata is `Base.metadata`, populated by whatever `src.models.tables` imports (see [`migrations/env.py`](../migrations/env.py) and [`docs/DATABASE.md`](DATABASE.md#migrations-alembic)). Add your new table module to that import chain (e.g., in `src/models/tables/__init__.py`), then:

```bash
alembic revision --autogenerate -m "add notes table"
# review the generated file under migrations/versions/ before applying
alembic upgrade head
```

## Step 3 — Write the CRUD layer

`src/models/crud/notes/note_crud.py` — follow the exact shape used by `src/models/crud/system/user_crud.py`:

```python
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import with_session
from src.models.tables.notes.note_table import Note
from src.services.system.logging import log_message

PRINT_PREFIX = "NOTE CRUD"


@with_session
async def add_note(username: str, title: str, body: str = "", session: AsyncSession | None = None) -> Note:
    note = Note(username=username, title=title, body=body)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@with_session
async def get_notes_for_user(username: str, session: AsyncSession | None = None) -> list[Note]:
    stmt = select(Note).where(Note.username == username).order_by(Note.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@with_session
async def get_note_by_id(note_id: int, session: AsyncSession | None = None) -> Note | None:
    stmt = select(Note).where(Note.id == note_id)
    result = await session.execute(stmt)
    note = result.scalar_one_or_none()
    if note is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Note not found: id={note_id}.")
    return note


@with_session
async def delete_note(note_id: int, username: str, session: AsyncSession | None = None) -> bool:
    """`username` scopes the delete so one user cannot delete another user's note."""
    stmt = delete(Note).where(Note.id == note_id, Note.username == username)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0
```

No caching layer is added here — notes are not on a hot, high-fan-out auth path the way users/API keys are, so a direct query is appropriate. Don't add a Redis cache "because the system layer has one" — add it if and when you actually have a read-heavy hot path that needs it, following the pattern in [`docs/DATABASE.md`](DATABASE.md#cache-interplay).

## Step 4 — Define request/response models

`src/api/notes/models.py`:

```python
from pydantic import BaseModel, Field


class NoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=10_000)


class NoteResponse(BaseModel):
    id: int
    title: str
    body: str
```

**Use `response_model=` on your routes** (see next step), exactly as every existing `system` route now does — this is required for FastAPI to validate and document your response shape rather than leaving it as a hand-built untyped dict. Add your response models (and request models) to your feature's own `models.py`, following the pattern in [`api_db_endpoints/models.py`](../src/api/system/api_db_endpoints/models.py)/[`user_db_endpoints/models.py`](../src/api/system/user_db_endpoints/models.py).

For error responses, reuse [`api_error()`](../src/api/errors.py) instead of raising a bare `HTTPException(...)`:

```python
from src.api.errors import api_error

if note is None:
    raise api_error(404, "Note not found.")
```

This keeps every error response on the same envelope shape (`detail: {"error": "...", "retry_after": <seconds-or-null>}`) that the rest of the API already uses — don't reintroduce a plain-string `detail` for new routes.

## Step 5 — Write routes and reuse existing auth

`src/api/notes/routes/router.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/notes", tags=["notes"])
```

`src/api/notes/routes/_post_routes.py`:

```python
from fastapi import Depends, Request

from src.api.notes.models import NoteCreateRequest, NoteResponse
from src.api.notes.routes.router import router
from src.api.config import EDIT_LEVEL
from src.models.crud.notes.note_crud import add_note
from src.models.tables.system.api_key_table import ApiKey
from src.security.ip_block import with_ip_block
from src.security.validation.api_security import api_key_authorized_factory

require_editor = api_key_authorized_factory(EDIT_LEVEL)


@router.post("", response_model=NoteResponse)
@with_ip_block
async def create_note(request: Request, model: NoteCreateRequest, api_key: ApiKey = Depends(require_editor)):
    # `api_key` (an ApiKey) is resolved by api_key_authorized_factory; request.state.api_data
    # (an APIRequestData) is also populated if you need the caller's fingerprint/permission name.
    note = await add_note(username="api-key-owner", title=model.title, body=model.body)
    return NoteResponse(id=note.id, title=note.title, body=note.body)
```

This reuses `with_ip_block` and `api_key_authorized_factory` exactly as every existing `system` route does — just at a lower permission level (`EDIT_LEVEL = 1` instead of `SUPER_ADMIN_LEVEL`). `with_ip_block` stays a decorator (it must be the outermost wrapper, closest to `@router.post`, so abusive IPs are rejected before any auth/DB work happens — copy this order exactly); the auth check itself is now a normal `Depends(...)` parameter, so it shows up in the route's OpenAPI schema and there's no decorator-ordering footgun for it.

`src/api/notes/routes/__init__.py` (side-effect imports so decorators register the routes on `router`):

```python
from src.api.notes.routes.router import router

from src.api.notes.routes import _get_routes
from src.api.notes.routes import _post_routes
```

## Step 6 — Register the router

In [`src/api/app.py`](../src/api/app.py), alongside the existing includes:

```python
from src.api.notes import routes as notes_routes
...
app.include_router(api_db_routes.router)
app.include_router(user_db_routes.router)
app.include_router(notes_routes.router)   # <-- your feature
```

That's the entire integration surface — nothing else in `app.py`, the lifespan handler, or the background services needs to change for a typical new feature.

---

## Choosing a permission model for your feature

The existing `system` routes hardcode `SUPER_ADMIN_LEVEL` because they *are* system administration. Your features should almost always use a **lower** level:

| Level | Constant | Suggested use for new features |
|:---:|---|---|
| `0` | `VIEW_LEVEL` | Read-only endpoints |
| `1` | `EDIT_LEVEL` | Create/update endpoints for a caller's own resources |
| `2` | `BULK_OPERATIONS_LEVEL` | Bulk import/export, admin-triggered batch jobs |
| `3` | `ADMIN_LEVEL` | Cross-user administrative actions within your feature |
| `4` | `SUPER_ADMIN_LEVEL` | **Reserved for system administration** — do not gate feature routes behind this; it exists specifically so system routes stay separated from everything else. |

If your feature needs more granular permissions than this flat 0–4 scale (e.g., per-resource ownership, team-based access), build that as **your own authorization check inside your route/CRUD layer**, layered *on top of* the existing `api_key_authorized_factory`/`cookie_authorized_factory` dependencies (which still give you IP blocking, rate limiting, and "is this credential valid at all" for free) rather than replacing them.

## Reusing rate limiting for your own resources

If a feature-specific action needs its own rate limit (independent of the caller's overall API-key rate limit), reuse the existing Redis-backed primitives directly instead of writing a new limiter:

```python
from src.services.system.cache.ratelimitcache import (
    ALLOWED, DENIED, INVALID_DATA, NOT_FOUND, TOO_SOON,
    place_in_redis, process_request,
)

async def _check_note_creation_limit(username: str) -> bool:
    identifier = f"note_create:{username}"
    result = await process_request(identifier)
    if result in (NOT_FOUND, INVALID_DATA):
        await place_in_redis(identifier, limit=20, window=3600)  # 20/hour
        result = await process_request(identifier)
    return result == ALLOWED
```

This is the same atomic Lua-script-backed limiter used for login attempts, API keys, and cookies — it is safe under concurrency and already handles the Redis-unavailable case (raises `RateLimitServiceUnavailable`, which you should catch and turn into a `503` exactly like the existing security modules do).

## Adding user-facing (cookie) authentication

The `cookie_authorized_factory()` dependency chain (see [`src/security/validation/cookie_security.py`](../src/security/validation/cookie_security.py)) is fully generic and works today — it's just not exercised by any real (non-test) route yet. To use it for a feature route:

```python
from fastapi import Depends

from src.api.models import CookieRequestData
from src.security.validation.cookie_security import cookie_authorized_factory

require_cookie = cookie_authorized_factory()  # optionally: cookie_authorized_factory(required_roles={"admin"})

@router.get("/my-notes")
@with_ip_block
async def list_my_notes(request: Request, cookie_data: CookieRequestData = Depends(require_cookie)):
    username = cookie_data.username
    ...
```

Before shipping a **mutating** (`POST`/`PATCH`/`DELETE`) cookie-authenticated route to real users, read [Engineering Report §5](ENGINEERING_REPORT.md#5-security) — there is currently no CSRF protection in this codebase, and cookie-based mutation is exactly the pattern that needs it. At minimum, require a custom header (e.g., `X-Requested-With`) that a cross-site form post cannot set, until proper CSRF tokens are added.

You will also need a **real login endpoint** for user-facing features — `/login-auth-test` is a test route gated by `API_EXPOSE_TEST_ENDPOINTS` and is not meant to be the production login flow. Build your own using the same building blocks it demonstrates: `authenticate_password()` from `src/security/validation/password_security.py` + `create_cookie_token()` from `src/security/tokens.py` + `get_cookie_settings()` for the `Set-Cookie` response.

## Configuration for your feature

Don't add new top-level variables to `config/loader.py` for feature-specific tuning unless it's truly global (like a pepper or a pool size). Prefer a new top-level key in `config/service_config.json`, modeled as a typed Pydantic settings class in [`config/settings.py`](../config/settings.py) — following the existing pattern used for `backup`, `dbhealthchecker`, `setup_postgres`, `setup_redis`, and `cookie_expiry`:

```python
# config/settings.py
class NotesSettings(BaseModel):
    """Notes feature tuning (src/models/crud/notes/note_crud.py)."""

    max_note_length: int = Field(
        default=10_000,
        ge=1,
        description="Maximum allowed length of a note body, in characters.",
    )

class ServiceConfig(BaseModel):
    ...
    notes: NotesSettings = Field(default_factory=NotesSettings)

NOTES_SETTINGS: NotesSettings = SERVICE_CONFIG.notes
```

```python
# src/models/crud/notes/note_crud.py
from config.settings import NOTES_SETTINGS

MAX_NOTE_LENGTH = NOTES_SETTINGS.max_note_length
```

`config/service_config.json` is now read and validated exactly once, at import time, through [`config/settings.py`](../config/settings.py) — every module that needs a tunable value should import its typed settings instance from there rather than calling `json.loads(...)` directly.

## Testing your feature

There is currently no unit-test scaffolding in this repository to extend (see [Engineering Report §8](ENGINEERING_REPORT.md#8-testing)) — [`tools/tests/live_system_api_test.py`](../tools/tests/live_system_api_test.py) is a live, end-to-end script, not a `pytest` suite. For new features:

- At minimum, add live smoke-test steps to a copy of that script's pattern (create → read → delete, using a nonce-suffixed identifier and cleaning up after itself), covering your new routes' happy path, a `404`, and a permission-denied case.
- Better: introduce `pytest` + `pytest-asyncio` for this feature's CRUD layer first (it's the easiest layer to test in isolation — call CRUD functions directly against a disposable test database/schema, no HTTP involved), and unit-test your route handlers' validation logic separately from the database.

## Things to avoid

- ❌ Adding feature routes under `src/api/system/**` "because it's already registered" — create your own top-level package instead.
- ❌ Gating feature routes behind `SUPER_ADMIN_LEVEL` for convenience — reserve it for actual system administration.
- ❌ Calling `session.execute(...)` directly from a route handler — always go through a CRUD function.
- ❌ Writing a new password hasher, JWT signer, or rate limiter for a feature-specific need — the existing primitives in `src/security/` and `src/services/system/cache/` are generic and parameterized for exactly this reuse.
- ❌ Writing your own cache-invalidation decorator instead of reusing [`src/models/crud/cache_invalidation.py`](../src/models/crud/cache_invalidation.py) — it already provides a shared `cache_invalidating(invalidator)` factory and identifier helpers used by every existing `system` CRUD module; extend it (or call it directly) rather than adding a new variant.
- ❌ Returning `SomeModel(...).to_dict()` directly from a route without checking every column is safe to expose publicly (see [`docs/DATABASE.md`](DATABASE.md#the-base-model-conventions)).

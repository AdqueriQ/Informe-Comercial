# Project Guidelines

## Code Style
- Keep backend changes aligned with the current Flask style in [app.py](../app.py): small helper functions, explicit request validation, and JSON responses with stable keys.
- Preserve the Spanish user-facing/error text style already used across endpoints unless there is a clear reason to translate.
- For binary payloads, keep base64 handling strict (same approach as the current decode helper) and return 400 for malformed input.

## Architecture
- Single-service Flask app with static frontend served from root:
  - Backend API and integration logic: [app.py](../app.py)
  - Frontend UI and client logic: [index.html](../index.html)
- Session state is intentionally in-memory and shared between admin/client flows.
- XLSX to PDF conversion is delegated to headless LibreOffice via subprocess.
- Telegram delivery is handled server-side via Bot API requests.

## Build And Test
- Install dependencies: `pip3 install -r requirements.txt`
- Run locally: `python3 app.py`
- Health check after startup: `GET /health`
- Container build/runtime reference: [Dockerfile.txt](../Dockerfile.txt)
- There is currently no automated test suite; when adding non-trivial backend behavior, validate endpoints manually and add tests if test infrastructure is introduced.

## Conventions
- Keep session endpoints compatible with existing payload shapes:
  - Save: `/session/save` expects `sid`, `data`, optional `base_ver`
  - Read: `/session/get?sid=...`
  - List: `/session/list` intentionally returns sessions with `cn` only
- Preserve last-write-wins session versioning semantics unless a migration plan is included.
- Keep `SESSION_TTL_SECONDS`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` as env-driven behavior for deployments.
- Avoid introducing features that assume persistent storage unless you also add a clear persistence layer and migration notes.

## Operational Gotchas
- Sessions are pruned on request flow, not by a background scheduler.
- All in-memory sessions are lost on process restart.
- PDF conversion depends on LibreOffice availability in the runtime environment.
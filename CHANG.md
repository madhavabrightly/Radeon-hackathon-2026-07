# Screen-AI Run Change Log

## 2026-07-23 17:03:33 +05:30

Purpose: fine-tune Screen-AI for low-memory 4 GB laptop operation using the review notes in the attached text file.

### Backend Performance And Memory

- Reworked SQLite access to use one shared `aiosqlite` connection instead of opening a new DB connection for every helper call.
- Added serialized `db_session()` access, WAL mode, `synchronous=NORMAL`, and `busy_timeout=5000`.
- Added lifecycle shutdown for the shared DB connection.
- Added missing DB indexes:
  - `idx_approvals_command`
  - `idx_quarantine_command`
- Changed command history to avoid `SELECT *`; it now selects only required fields, truncates `result`, and clamps `limit`.

### Command Pipeline

- Confirmed approval waits yield through `asyncio.wait_for`.
- Added `AgentRouter.shutdown()` to release heavy tool resources.
- Fixed `/command` device verification to await the async pairing verifier.

### Browser Memory

- Added lazy Playwright lifecycle tracking.
- Added Chromium idle eviction after 300 seconds through `BrowserTools.unload_idle()`.
- Browser is closed during FastAPI shutdown.

### File Tools

- Replaced unbounded recursive scans with bounded traversal.
- Limits:
  - max files: 5000
  - max depth: 3
  - timeout: 10 seconds
- Protected paths are rejected for scan unless explicitly handled by higher approval policy.
- Quarantine size calculation now uses bounded traversal.
- Quarantine listing now selects explicit columns and limits results.

### Vault

- Removed module-level cryptography imports for lazy loading.
- Added configurable Argon2id KDF profile.
- Added per-unlock-session derived key cache keyed by salt.
- Wipes cached keys on lock.
- Fixed `last_used` update.
- Made credential insert idempotent with SQLite upsert.
- Smoke tests use a lighter KDF profile; production defaults remain stronger.

### Regex And Redaction

- Precompiled planner intent patterns.
- Precompiled risk classifier patterns.
- Precompiled log redactor secret patterns.
- Fixed redactor output so quoted secrets do not leave doubled quotes.

### Scanner

- Added short identical-screen cache to `screen_element_scanner/scan_screen.py`.
- New option:

```powershell
python .\screen_element_scanner\scan_screen.py --cache-ttl 2
```

- Cache files are ignored through `.gitignore`.

### Dependencies

- Trimmed unused backend dependencies:
  - removed `pywinauto`
  - removed `pytesseract`
  - removed `python-jose[cryptography]`
  - removed `passlib[bcrypt]`
- Updated Playwright pin from `1.40.0` to `1.54.0`.

### Tests And Verification

Commands run:

```powershell
python -m py_compile screen_element_scanner\scan_screen.py ai_pc_operator\backend\app\db\database.py ai_pc_operator\backend\app\agent\planner.py ai_pc_operator\backend\app\security\risk.py ai_pc_operator\backend\app\agent\router.py ai_pc_operator\backend\app\approvals\manager.py ai_pc_operator\backend\app\main.py ai_pc_operator\backend\app\tools\browser_tools.py ai_pc_operator\backend\app\tools\file_tools.py ai_pc_operator\backend\app\security\vault.py ai_pc_operator\backend\app\security\pairing.py ai_pc_operator\backend\app\logs\redactor.py ai_pc_operator\backend\test_basic.py
python -u .\ai_pc_operator\backend\test_basic.py
python .\screen_element_scanner\scan_screen.py --quiet
```

Result:

```text
All passed.
```

### Development Notes

- Earlier timed-out test runs left stale Python processes holding the SQLite DB lock. Those processes were stopped before the final successful smoke test.
- `aiosqlite==0.19.0` was installed locally to run the backend smoke test.


# Mealplanner — Code Review

**Date:** 2026-05-31
**Reviewed version:** v1.0.3
**Scope:** Backend (FastAPI) + Frontend (Angular 21). Focus: security, architecture, clean code, and frontend UX.

> Context: this is a single-user, self-hosted personal app (deployed on cloud7 NAS, port 9005). Severity ratings are calibrated to that context — several "High" items would be critical for a public multi-tenant app but are mitigated here by limited network exposure. They still matter because the app holds a paid Anthropic API key.

---

## Summary

The codebase is in good shape. The hexagonal architecture (ports/adapters), the strict separation of LLM usage to import-time only, and the deterministic per-person normalization are genuinely well done and consistently applied. The issues below are mostly hardening and polish, not structural defects.

| # | Area | Finding | Severity |
|---|------|---------|----------|
| S1 | Security | No authentication on any endpoint; paid LLM endpoints are open | High* |
| S2 | Security | Unbounded upload size — whole file read into memory | Medium |
| S3 | Security | Path-traversal hardening gap in stored upload filename | Medium |
| S4 | Security | Container runs as root; no healthcheck/.dockerignore | Low |
| S5 | Security | Unpinned Python dependencies | Medium |
| S6 | Security | CORS `allow_credentials=True` is unnecessary | Low |
| A1 | Architecture | Doc/behaviour drift: "accept drafts" flow no longer exists | Medium |
| A2 | Architecture | SQLite + background-thread writes can lock under concurrency | Low |
| A3 | Architecture | Invalid-format upload path returns inconsistent error codes | Low |
| C1 | Clean code | Duplicated filter logic in `recipes.ts` | Low |
| C2 | Clean code | Dead import / unused draft status constant | Low |
| C3 | Clean code | Silent error handling on optimistic toggles | Low |
| U1 | UX | Native `alert()` / `confirm()` dialogs | Medium |
| U2 | UX | Shopping-list check state is in-memory only (lost on reload) | Medium |
| U3 | UX | Shopping-list checkbox key collides on same name w/ different units | Low |
| T1 | Testing | Frontend has almost no test coverage (2 spec files) | Medium |

\* High *in principle*; mitigated by private network deployment.

---

## Security

### S1 — No authentication on any endpoint (High*)
`backend/app/routers/*.py` — every route (`/api/recipes`, `/api/plans`, `/api/imports/*`) is open. There is no auth dependency anywhere (verified: no `Depends`-based auth, API key, or bearer check in routers).

Impact: anyone who can reach the host can read/modify/delete all recipes and plans, **and** can:
- upload files and trigger `POST /api/imports/process`, which spends real money against the Anthropic API key baked into the container env (`ANTHROPIC_API_KEY`). This is a cost-amplification vector, not just data exposure.

Recommendation: put the app behind authentication. Cheapest options, in order:
1. Reverse-proxy HTTP Basic auth (nginx/Caddy/Synology) in front of port 9005 — zero code change.
2. A single shared app token checked in a FastAPI dependency.
Add a basic rate limit on `/imports/uploads` and `/imports/process` regardless.

### S2 — Unbounded upload size (Medium)
`backend/app/routers/imports.py:31` — `data = await file.read()` loads the entire upload into RAM with no size cap (verified: no size/Content-Length check anywhere in the backend). A large or repeated upload can exhaust memory. PDFs/images are also held fully in memory again during extraction.

Recommendation: enforce a max size (e.g. reject > 25 MB) by checking `Content-Length` and/or reading in bounded chunks before persisting.

### S3 — Path-traversal hardening gap in stored filename (Medium)
`backend/app/services/import_service.py:94`
```python
stored_name = f"{uuid.uuid4().hex}_{filename}"
(settings.uploads_dir / stored_name).write_bytes(file_bytes)
```
The UUID prefix only protects the *first* path segment. A client-supplied `filename` containing `/../` (API clients don't strip paths the way browsers do) produces extra path segments and can escape `uploads_dir` (e.g. `..%2f..%2f..%2ffoo` → `uploads_dir/<uuid>_../../../foo`). The same untrusted `filename` is later echoed into the `Content-Disposition` header via `FileResponse(..., filename=...)`.

Recommendation: sanitize to the basename before storing — `Path(filename).name` — and/or store purely by UUID and keep the original name only as a DB column (which you already do: `ImportJob.filename`).

### S4 — Container & build hardening (Low)
`Dockerfile`:
- No `USER` directive → the process runs as **root** inside the container.
- No `HEALTHCHECK` (you already have `/api/health` — wire it up).
- No `.dockerignore` observed → risk of copying local `data/` or `node_modules` into the build context (slower builds, possible data leak into image layers).

Recommendation: add a non-root `USER`, a `HEALTHCHECK` hitting `/api/health`, and a `.dockerignore`.

### S5 — Unpinned dependencies (Medium)
`backend/requirements.txt` lists every package with no version constraint (`fastapi`, `anthropic`, `sqlmodel`, …). Builds are not reproducible and a transitive breaking change can silently land on the next image build. The dev tools (`pytest`, `httpx`) also ship into the production image.

Recommendation: pin versions (a lockfile or `==`), and split dev/test deps out of the production install. Run `pip-audit` as part of the release cycle (per the dev-workflow skill).

### S6 — CORS `allow_credentials=True` is unnecessary (Low)
`backend/app/main.py:54-60` — origins are correctly restricted to `localhost:4200`, but `allow_credentials=True` with `allow_methods=["*"]`/`allow_headers=["*"]` is broader than needed. The app uses no cookies/credentials (it's same-origin in production). Drop `allow_credentials` and consider gating the CORS middleware to dev only.

---

## Architecture

### A1 — "Accept drafts" flow no longer exists, but is still documented (Medium)
`CLAUDE.md` and the README describe a draft → review → accept pipeline (`POST /api/imports/{id}/accept`, `status=accepted`). In the current code:
- There is **no** `/accept` endpoint in `routers/imports.py`.
- `import_service._save_recipe` writes recipes directly with `status=RECIPE_ACCEPTED` (`import_service.py:253`).
- `RECIPE_DRAFT` is still defined (`models.py:11`) and `list_recipes` still defaults to `status="accepted"`, but nothing creates drafts anymore.

This matches your stated preference (bulk auto-accept rather than per-item review), so the *behaviour* is fine — but the docs and the unused draft machinery are now misleading. Recommendation: update `CLAUDE.md`/README to describe auto-accept, and remove the dead draft status path (or keep it deliberately and note why).

### A2 — SQLite write concurrency from background threads (Low)
`db.py:11` uses `check_same_thread=False`, and imports run in FastAPI `BackgroundTasks` while HTTP requests also write. With SQLite this can surface as `database is locked` under concurrent writes (e.g. processing several jobs while browsing). Single-user usage makes this unlikely, but it's a latent issue.

Recommendation: if it ever bites, enable WAL mode (`PRAGMA journal_mode=WAL`) and a busy timeout, or serialize import processing.

### A3 — Inconsistent error handling for bad uploads (Low)
`import_service.upload` raises `UnsupportedFormatError` (handled → 415, good). But other failure modes differ: a corrupt PDF surfaces only later during processing and is stored as `job.error` = `str(exc)` (`import_service.py:223`), shown verbatim in the UI. That's acceptable for a personal tool but leaks internal exception text. Consider a friendlier message + logging the detail server-side only.

---

## Clean code

### C1 — Duplicated filter predicate (Low)
`pages/recipes/recipes.ts` — `withoutCourse` (lines 36-53) and `filtered` (78-98) repeat the same multi-field predicate. Extract a single `matches(r, {exceptCourse})` helper to keep them in sync; today a new filter must be added in two places.

### C2 — Dead code (Low)
- `routers/recipes.py:48` — `from sqlmodel import Session as _S` is imported and never used.
- `RECIPE_DRAFT` (`models.py:11`) is effectively unused after A1.

### C3 — Silent failures on optimistic updates (Low)
Favourite / want-to-try toggles call `this.api.updateRecipe(...).subscribe()` with no error callback (`recipes.ts:143,151`; `recipe-detail.ts:160,167`). If the PUT fails, the UI stays optimistically updated and silently diverges from the server. Add an error handler that reverts and shows a toast (you already have `ToastService`).

**Positives worth keeping:** `services/units.py`, `services/shopping_list.py`, and the `ports/`+`adapters/` split are clean, pure, and well-commented. `formatQty` is correctly shared from `settings.service.ts` (no duplication). The Claude extractor's tool-use schema + automatic chunk-halving on truncation (`claude_extractor.py:218-241`) is a nice robustness touch.

---

## Frontend UX / usability

### U1 — Native browser dialogs (Medium)
`alert()` and `confirm()` are used for errors and destructive confirmations in `import-page.ts` (100, 135, 146, 155), `planner.ts:98`, and `recipe-detail.ts:172`. These are jarring, unstyled, block the main thread, and are inconsistent with the existing toast system. Recommendation: replace `alert` with toasts and `confirm` with a small in-app confirmation modal/component.

### U2 — Shopping-list check state is ephemeral (Medium)
`pages/shopping-list/shopping-list.ts:19` keeps `checked` purely in memory. Reloading the page or navigating away and back loses every tick — frustrating mid-shop on a phone. Recommendation: persist per-plan check state to `localStorage` (you already use this pattern for import ETAs).

### U3 — Checkbox key collision (Low)
`itemKey(cat, name)` (`shopping-list.ts:46`) keys by category+name only. The aggregator can legitimately emit two line items with the same name but different units (e.g. "milk" in `g` and in `ml` — see `build_shopping_list`, keyed by `(name, unit)`). Both render with the same key, so checking one visually checks both. Include the unit in the key.

### Minor UX notes
- Import page polls `/llm-status` **and** `/imports/` every 5 s unconditionally, even when idle and the tab is backgrounded — minor battery/network cost. Consider pausing polling when there are no active jobs or when `document.hidden`.
- `recipe-detail` "per serving" nutrition intentionally does not scale with the servings stepper (correct, since values are per-person) — but a user changing servings might expect totals. Consider showing scaled totals alongside.
- No favourite/want-to-try toggle feedback toast (silent success) — fine, but inconsistent with the edit/save flow which does toast.

---

## Testing

### T1 — Frontend coverage is thin (Medium)
Backend has reasonable coverage (35 tests across `test_api`, `test_import`, `test_units`, `test_shopping_list`, using the in-memory DB + `FakeRecipeExtractor` — good). The frontend has only **2 spec files** (`settings.service.spec.ts`, `recipe-detail.spec.ts`), both testing pure functions. No tests cover the filtering logic (`recipes.ts`), planner slot logic, shopping-list rendering, or `api.service` URL construction.

Recommendation: add component tests for the recipe filter predicate (highest-value, most logic) and the planner `entryMap`/`pickRecipe` flow.

---

## Suggested priority order

1. **S1** auth in front of the app (protects data *and* the API key/spend).
2. **S2 / S3** upload size cap + filename sanitization (cheap, removes the two real attack surfaces).
3. **S5** pin dependencies; run `pip-audit`/`npm audit` each release.
4. **U1 / U2** replace native dialogs; persist shopping-list checks (biggest day-to-day UX wins).
5. **A1** reconcile docs with the auto-accept reality; delete dead draft code.
6. Cleanups (C1–C3, S4, S6) and **T1** as time permits.

---
name: api-contract
description: Keep the backend API contract in sync across its three consumers - FastAPI Pydantic schemas, the web client, and the Flutter API client. Use when adding or changing an endpoint, editing backend/app/schemas.py, or when a client stops matching the backend.
---

# API Contract

One backend serves three consumers: the web one-pager, the Flutter app, and the Cloudflare Worker
(which forwards to `/contact`). They live in different languages and are tested separately, so a
schema change breaks them **silently** — the backend suite stays green, the mobile suite stays
green, and the app fails at runtime in front of whoever you were trying to impress.

This is the highest-value cross-cutting check in the repo, and nothing catches it automatically.

## Source of truth

**`backend/app/schemas.py`.** Pydantic models are the contract. Everything else mirrors it.

If a client needs a field the backend doesn't return, the fix goes in the backend first, then
propagates outward. Never patch a client to paper over a mismatch.

## Consumers

| Consumer | What mirrors the contract |
|---|---|
| `backend/` | `app/schemas.py` — request and response models per endpoint |
| `web/` | fetch/response handling for `/chat` and `/contact` |
| `mobile/` | `lib/api/` client models |
| `edge/` | the `/contact` payload it validates and forwards |

The Worker matters and is easy to forget: it validates and forwards `/contact` submissions, so a
field change there breaks the whole contact path even though the Worker never touches `/chat`.

## Procedure — on any endpoint or schema change

1. **Change `backend/app/schemas.py` first.** Add the Pydantic field, update the response model.
2. **Update the backend tests.** Assert the new shape explicitly, including its absence/default.
3. **Walk every consumer** in the table above. For each: does it send the new field, parse it,
   and behave sanely when it's missing?
4. **Update each consumer's tests** to match. A mobile test asserting the old shape is now lying.
5. **Check the Worker's validation.** If it rejects unknown fields or requires a field that moved,
   it will drop valid submissions.
6. **Run all affected suites**, not just the backend's.

## Compatibility rules

The web app and the mobile app deploy on **different schedules** — a published APK can be weeks
behind the backend. Treat every change as if an old client is still live:

- **Additive is safe.** New optional fields with sensible defaults.
- **Removing or renaming a field is breaking.** Deprecate, ship, migrate clients, then remove.
- **Narrowing a type is breaking** — `str` → `enum` rejects payloads that used to work.
- **Making an optional field required is breaking.**

If a breaking change is genuinely needed, say so explicitly and flag that mobile clients in the
wild will fail until rebuilt. Don't slip it through as a routine edit.

## Reviewing for drift

```bash
git log --oneline -- backend/app/schemas.py
```

Cross-check that each schema commit has matching commits in `web/`, `mobile/`, and `edge/`. A
schema change with no corresponding client change is either safely additive or a latent bug —
determine which, don't assume.

## Rules

- **Never change a client to match a backend bug.** Fix the backend.
- **Never let a client define its own idea of the shape.** Mirror the Pydantic model.
- Field names stay identical across languages. Don't re-case them per-language convention — the
  cost of a mental translation table exceeds the cost of a slightly un-idiomatic Dart field name.
- When a contract change lands, note it in the commit body. It's the record a future reader needs.

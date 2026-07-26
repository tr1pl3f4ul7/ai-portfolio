# .github/ — CI/CD

Path-filtered workflows deploying one monorepo to **four independent targets**. Built in Phase 6
for backend/edge/web, since that's what exists by then; don't create these files earlier.
`mobile-build.yml` arrives later, with Phase 7's Step 7.5, once the Flutter app is actually there
to build (decision 50).

## Workflows

| File | Trigger path | Target |
|---|---|---|
| `backend-ci.yml` | `backend/**` | `ruff check` + `pytest`, directly on `ubuntu-latest` — no container needed, unlike the local dev-machine workaround (decision 53) |
| `edge-ci.yml` | `edge/**` | `tsc --noEmit` + `vitest`, directly on `ubuntu-latest` — same reasoning as backend-ci.yml |
| `web-ci.yml` | `web/**` | `npm run build` + `vitest`, no secrets — the real secret-injected build happens in `web-deploy.yml` |
| `backend-deploy.yml` | `backend/**`, `infra/deploy.sh`, `infra/nginx/**`, `infra/systemd/**` | `infra/deploy.sh` on the runner — full rsync + venv/vector-store rebuild + nginx/systemd install + restart, secrets from GitHub Actions written to the VM's env file (decision 52) |
| `edge-deploy.yml` | `edge/**` | `wrangler deploy`, spam-only smoke test against `contact.ljubenvassilev.com` (decision 55) |
| `web-deploy.yml` | `web/**` | Cloudflare Pages project `ai-portfolio-web`, bound to `ljubenvassilev.com` + `www` (decision 48/54) |
| `mobile-build.yml` | `mobile/**` + tags | APK/IPA artefact + store publishing (Step 7.5, decision 42) |

## Rules

- **The default branch is `master`, not `main`.** Every `on: push:` trigger targets
  `branches: [master]`. A workflow pointed at `main` will never fire and gives no error — it
  simply sits there looking correct.
- **Path filters are the whole point.** A web copy change must not redeploy the backend. Every
  workflow declares `paths:` — and remember a workflow editing its own file needs that path
  filtered too, or it won't retrigger.
- **Every deploy workflow ends with a post-deploy smoke test.** Backend → `/health` returns 200.
  Edge → a spam payload against `contact.ljubenvassilev.com` gets the correct response shape,
  deliberately spam-only rather than clean+spam — a clean payload really forwards to the backend
  (a real Claude call, a stored submission, a real email to LJ) on every single deploy, which
  decision 55 rejected as a smoke test's job. Web → the site actually serves. A deploy step that
  reports success without verifying the target is live is worse than no workflow, because it
  manufactures false confidence.
- **Never live-call the Claude API in CI.** Mock it. CI runs on every push; a live call means
  paying for every commit and flaking whenever the API is slow.
- **Secrets by name only, never inlined.** Reference `${{ secrets.NAME }}`. Never `echo` a
  secret, never put one in a step name or an artefact. Names are listed in §5 of
  `docs/PROJECT_PLAN.md`.
- **Pin actions to a version.** `actions/checkout@v4`, not `@main`.
- **Least privilege**: set `permissions:` explicitly per workflow rather than inheriting the
  default token scope.
- Concurrency-guard deploys so two pushes can't deploy over each other:
  ```yaml
  concurrency:
    group: deploy-backend
    cancel-in-progress: false
  ```
  Note `cancel-in-progress: false` — cancelling a half-finished deploy is how you get a broken VM.

## Runner architecture

GitHub's standard runners are **x64 Linux**. The VM is `aarch64`. CI therefore tests on a
different architecture than production. That's acceptable for pure-Python tests, but it means CI
green does **not** prove the VM install works — which is exactly why the post-deploy `/health`
smoke test is mandatory rather than nice-to-have.

Don't add the local ARM64 torch index (`download.pytorch.org/whl/cpu`) to CI. That's a Copilot PC
dev-machine workaround; Linux runners resolve torch from PyPI normally.

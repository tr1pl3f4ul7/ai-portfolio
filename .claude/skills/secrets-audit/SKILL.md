---
name: secrets-audit
description: Scan the repo and pending changes for exposed credentials before committing or deploying. Use before any commit touching config/CI/deploy, before every deploy, after adding a new integration key, or when asked to check for leaked secrets.
---

# Secrets Audit

This project wires together three deploy targets and roughly a dozen credentials. A single leaked
key in a **public** portfolio repo compromises the Anthropic account, the Oracle VM, the
Cloudflare zone, or all three. This audit is cheap; the failure is not.

## Secrets in play

From §5 of `docs/PROJECT_PLAN.md`:

| Secret | Lives in |
|---|---|
| `ANTHROPIC_API_KEY` | VM env file, GitHub Actions secret |
| `ORACLE_VM_SSH_PRIVATE_KEY` | GitHub Actions secret, `~/.ssh` locally |
| `ORACLE_VM_HOST` | GitHub Actions secret |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | GitHub Actions secret, wrangler config |
| `SENTRY_DSN_BACKEND` | VM env file |
| `VITE_SENTRY_DSN` | build-time config — **publishable** |
| `VITE_POSTHOG_KEY`, `VITE_POSTHOG_HOST` | build-time config — **publishable** |
| SMTP credentials / notification webhook | VM env file |

**Publishable vs. secret.** PostHog project keys and Sentry DSNs are designed to ship in client
code — finding one in `web/` is not a leak. `ANTHROPIC_API_KEY` in `web/` is a critical finding,
always.

## Procedure

### 1. Nothing sensitive staged

```bash
git diff --cached --name-only
```

Then scan the staged content for credential-shaped strings: `sk-ant-`, `gho_`, `ghp_`,
`BEGIN OPENSSH PRIVATE KEY`, `BEGIN RSA PRIVATE KEY`, `AKIA`, long base64 blobs assigned to
anything named key/token/secret/password/dsn.

### 2. Ignore rules actually work

Verify `.gitignore` catches them, rather than assuming:

```bash
git check-ignore -v .env backend/.env edge/.dev.vars
```

Every one must report a matching rule. A missing rule is a finding even if no file exists yet —
the file will exist eventually, and the gap is silent until it isn't.

### 3. Committed files that commonly carry secrets

Check `edge/wrangler.toml`, `infra/systemd/*.service`, `.github/workflows/*.yml`, `docker-compose*`,
and any `*.example` file. Rules:

- `wrangler.toml` → `wrangler secret put`, never a literal.
- systemd → `EnvironmentFile=`, never `Environment=` with a real value.
- workflows → `${{ secrets.NAME }}` only. Never `echo` a secret, never put one in a step name.
- `.env.example` → dummy placeholder values only, never a real key "for convenience".

### 4. History, not just the working tree

`.gitignore` does nothing about what's already committed:

```bash
git log --all --diff-filter=A --name-only --format="%h" -- "*.env" "*.pem" "*.key" "*.jks" "*.keystore"
```

Empty output is the pass condition.

### 5. Client bundles

Confirm `ANTHROPIC_API_KEY` appears nowhere under `web/`. If client code needs Claude, it goes
through the backend — that's the architecture, and a direct client call is a design error, not
just a leak.

## If you find one

**Say so immediately and loudly.** Then, in order:

1. **Rotate the credential.** Deleting the file is not remediation — assume it's compromised the
   moment it lands in a public repo.
2. Remove it from the working tree and add the ignore rule.
3. If it was committed, say plainly that history rewriting or rotation is required, and let LJ
   decide. **Never rewrite published history without explicit confirmation.**
4. Record the incident and the rotation in `docs/runbook.md`.

Never quietly fix a leak. LJ needs to know a rotation is required.

## Rules

- Run this **before** the commit, not after.
- Never print a real secret value into terminal output while auditing — that's a new leak. Report
  the file and line, never the value.
- A clean audit is stated plainly. Don't hedge a pass, and don't manufacture findings to look
  thorough.

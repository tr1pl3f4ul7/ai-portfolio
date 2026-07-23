# infra/ — VM Bootstrap, nginx, systemd

Everything that makes the Oracle Ampere A1 VM serve the backend. This directory is the reason
the project can claim "real infrastructure, configured by hand."

**Target:** Ubuntu 22.04/24.04 on `aarch64`, 2 OCPU / 12 GB, Always Free tier.

## Intended layout

```
infra/
├── setup.sh        # one-shot VM bootstrap  (Step 1.2)
├── nginx/          # reverse proxy config templates
└── systemd/        # unit file for the FastAPI service  (Step 2.6)
```

## ⚠️ Line endings will ruin your day

`.gitattributes` pins `infra/**` and `*.sh` to **LF**. Do not override it, and never commit a
CRLF shell script from this Windows machine. The failure mode is a `bad interpreter: /bin/bash^M`
error on the VM that reads like a typo in the shebang and wastes an hour.

## Rules for `setup.sh`

- **Idempotent is a hard requirement**, not a nicety. Running it twice must produce no errors and
  no duplicated config lines. The plan tests exactly this. Guard every append, every user
  creation, every symlink.
- **`shellcheck` clean.** No exceptions without an inline justification comment.
- `set -euo pipefail` at the top.
- **Never disable the firewall to make something work.** `ufw` allows 22/80/443 and nothing else.
  Oracle *also* has its own security list — both must permit a port for traffic to arrive, which
  is the single most common reason "the port is open but nothing connects."
- **The app runs as a dedicated non-root user.** Never as root.
- **No secrets in any file here.** The systemd unit reads an environment file that lives on the
  VM outside the repo (`/etc/ai-portfolio.env`, root-owned, `chmod 600`). It is never committed.
- Pin what you can. An unpinned bootstrap that worked in July and breaks in November is worse
  than no bootstrap.

## Rules for the systemd unit

- `Restart=always` with a sane `RestartSec`.
- `EnvironmentFile=` for config — never inline `Environment=` with a real secret.
- Journald for logs; set up rotation (Step 8.2) so a 12 GB box doesn't fill its disk.
- After any unit file change: `systemctl daemon-reload` before `restart`, or the change silently
  does nothing.

## Rules for nginx

- Reverse proxy to uvicorn on localhost only. **The app port must never be publicly reachable** —
  all external traffic goes through nginx.
- Forward `X-Forwarded-For` / `X-Forwarded-Proto` so the backend sees real client info.
- TLS is decided in Phase 5 (certbot on the VM vs. Cloudflare origin cert + "full strict").
  Don't assume which — it's an open decision until Step 5.2.

## Verification

Post-deploy smoke test hits `/health` — required after **every** backend deploy. A deploy that
isn't smoke-tested isn't finished.

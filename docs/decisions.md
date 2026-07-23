# Decision Log

Every non-obvious choice made while building this project, why it was made, and what was rejected.
Recorded as decisions happen, not reconstructed afterwards — the reasoning is vivid now and gone
in three weeks.

The rejected options matter as much as the chosen ones. A decision with no discarded alternative
usually wasn't a decision.

Format is described in [`docs/CLAUDE.md`](CLAUDE.md). Entries are chronological.

---

## 1. Oracle Cloud Ampere A1 as the server inference layer

**Date:** 2026-07-23
**Status:** accepted

**Context:** The project needs a real server to run a FastAPI RAG chatbot — one that is genuinely
administered rather than clicked together on a managed platform, since the infrastructure work is
part of what the portfolio demonstrates.

**Decision:** Oracle Cloud Always Free Ampere A1 (Arm) VM, Ubuntu, nginx + systemd, TLS via
Let's Encrypt or Cloudflare.

**Rejected:**
- *Managed platforms (Render, Railway, Fly.io):* trivially easy, and that's the problem — they
  hide exactly the layer this project is meant to show.
- *AWS/GCP free tiers:* time-limited, and the x86 micro instances are too small for an embedding
  model.
- *Hetzner/DigitalOcean:* fine machines, but they cost money monthly and demonstrate nothing that
  Oracle's free tier doesn't.

**Consequences:** Committed to `aarch64` Linux, which mostly helps (native PyPI wheels) but rules
out anything x86-only. Hard ceiling of 12 GB RAM shared between nginx, FastAPI, the embedding
model, and the vector store — every server-side change has to respect that budget. Oracle's
Always Free A1 capacity is also genuinely scarce, which forced decision 4 below.

---

## 2. Home region: Australia East (Sydney)

**Date:** 2026-07-23
**Status:** accepted — **irreversible**

**Context:** Oracle requires a home region at signup, and it can never be changed afterwards.
Always Free resources exist only in the home region.

**Decision:** `ap-sydney-1` (Australia East).

**Rejected:** Regions with better-known A1 availability. Latency to LJ and to the likely audience
matters more than provisioning convenience, and a portfolio site served from the wrong hemisphere
is a worse outcome than a slow first provision.

**Consequences:** Every free-tier resource must live in Sydney; anything created elsewhere bills.
Sydney is a capacity-constrained region for Ampere A1, which directly caused decision 4.

---

## 3. Instance shape: 2 OCPU / 12 GB

**Date:** 2026-07-23
**Status:** accepted

**Context:** `VM.Standard.A1.Flex` lets you choose OCPU and memory. The build plan (§4, Step 1.1)
explicitly specifies 2 OCPU / 12 GB and says not to request 4/24.

**Decision:** 2 OCPU / 12 GB, per the plan.

**Rejected:** 4 OCPU / 24 GB. Oracle's Always Free Arm allowance is generally documented as
4 OCPU / 24 GB in total, so 4/24 would likely also be free. This was raised with LJ and the plan's
figure was kept deliberately rather than by oversight — smaller shapes provision more reliably in
a capacity-constrained region, and 12 GB is ample for this workload.

**Consequences:** Roughly half the Always Free Arm allowance stays unused, leaving headroom for a
second instance later. If the embedding model plus vector store ever outgrow 12 GB, the shape can
be resized — which is precisely why decision 5 (no shielded instance) matters.

---

## 4. Upgrade the tenancy to Pay As You Go

**Date:** 2026-07-23
**Status:** accepted

**Context:** Ampere A1 capacity in Sydney is heavily constrained, and "Out of host capacity" is a
common and persistent failure for Always Free accounts. Provisioning was blocked.

**Decision:** Upgrade the tenancy to Pay As You Go. Always Free resources remain free on a PAYG
account; the upgrade exists purely to obtain A1 capacity, not to consume paid resources.

**Rejected:**
- *Retrying until capacity appears:* unbounded, and can take days or never succeed.
- *Switching to an x86 Always Free micro instance:* 1 GB RAM cannot hold the embedding model.
- *Changing region:* impossible, the home region is fixed (decision 2).

**Consequences:** **This removes a safety net.** A free-tier account physically cannot create
billable resources; a PAYG account will create them and charge for them. Compensating controls
adopted at the same time:
- A $1 monthly budget with alerts on both actual and forecast spend.
- A rule that every resource must show the "Always Free eligible" badge before creation.
- Weekly check of Cost Analysis, which should read $0.00.

Note that an Oracle budget is an *alert*, not a hard cap — there is no mechanism that
auto-terminates resources on overspend. Vigilance is the control.

---

## 5. Shielded instances: disabled

**Date:** 2026-07-23
**Status:** accepted

**Context:** Instance creation offers Secure Boot, Measured Boot, and TPM ("shielded instance") to
harden firmware against boot-level attacks.

**Decision:** Leave disabled (the default).

**Rejected:** Enabling it. The protection addresses boot and firmware tampering by an attacker who
already has deep host access. The realistic threats here are exposed ports, SSH configuration,
application vulnerabilities, and leaked API keys — none of which Secure Boot touches. The most
sensitive item on the box is `ANTHROPIC_API_KEY` in an environment file, which it does not protect.

**Consequences:** Oracle states that after a shielded instance launches, only its name can be
changed — so enabling it would forfeit the ability to resize a *Flex* shape, the main reason for
choosing one. It would also restrict placement to hosts with the required firmware support, in the
one region where capacity is already the binding constraint. Not a one-way door: nothing is built
yet, so enabling it later costs one instance rebuild.

---

## 6. Boot volume left at defaults

**Date:** 2026-07-23
**Status:** accepted

**Context:** The storage step offers custom boot volume size, performance (VPU), and
customer-managed encryption keys.

**Decision:** Defaults throughout — ~47 GB, Balanced (10 VPU), Oracle-managed keys, in-transit
encryption on.

**Rejected:**
- *A larger boot volume:* Always Free includes 200 GB of block storage in total; inflating the
  boot volume "just in case" consumes the allowance and buys nothing. It can be expanded later.
- *Higher VPU:* billable, and this is the easiest accidental charge to incur on a PAYG tenancy.
- *Customer-managed keys:* requires Oracle Vault, which is not free and protects against a threat
  model this project doesn't have.

**Consequences:** ~47 GB for OS, Python, the embedding model (~90 MB), and the vector store — far
more than needed.

---

## 7. VCN addressing and topology

**Date:** 2026-07-23
**Status:** accepted

**Context:** The VM needs a network with a route to the internet. Oracle's VCN Wizard builds the
VCN, subnets, internet gateway, and route table together; the plain "Create VCN" page builds only
the VCN.

**Decision:** Used the VCN Wizard ("Create VCN with Internet Connectivity") with:

| Item | Value |
|---|---|
| VCN CIDR | `10.0.0.0/16` |
| Public subnet | `10.0.1.0/24` |
| Private subnet | `10.0.2.0/24` |

**Rejected:** Creating the VCN by hand. It requires separately adding an internet gateway, a
`0.0.0.0/0` route rule, and a public subnet. Missing any one produces a running instance that
silently refuses SSH — a confusing failure with no useful error.

**Consequences:** RFC 1918 space with room for 254 hosts per subnet, far beyond need. The private
subnet is unused by this project but harmless. Ingress rules for 22, 80, and 443 are added to the
default security list separately.

---

## 8. Local Python 3.11 with PyTorch's own wheel index

**Date:** 2026-07-23
**Status:** accepted

**Context:** The dev machine is Windows 11 on ARM64 (Snapdragon X Elite). The plan pins
`sentence-transformers/all-MiniLM-L6-v2`, which depends on PyTorch. Verified by testing:
`pip install torch` fails outright — PyPI publishes **zero** `win_arm64` wheels for torch.

**Decision:** Keep Python 3.11 and install torch from PyTorch's own index for local development:

```
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

Confirmed working: `torch 2.13.0+cpu / cp311 / win_arm64` resolves from that index.

**Rejected:**
- *Switching the local Python version:* unnecessary once the real cause was identified —
  `download.pytorch.org` carries cp311 wheels from torch 2.8 onward.
- *Substituting ONNX Runtime for torch:* would have diverged the local stack from the VM's for no
  benefit, since the VM has native wheels.
- *Developing the backend only on the VM:* slow feedback loop for no gain.

**Consequences:** Local installs need the extra index; **VM and CI installs must not use it.**
Oracle Ampere A1 is Linux `aarch64`, where PyPI ships native `manylinux_aarch64` wheels, and
GitHub's runners are x86-64 Linux. Two different ARM64 targets with opposite requirements is an
easy thing to get wrong, so it is documented in the root `CLAUDE.md` and `backend/CLAUDE.md`.

---

## 9. Flutter x64 SDK under emulation

**Date:** 2026-07-23
**Status:** accepted

**Context:** Flutter publishes no Windows ARM64 build — the release manifest lists `dart_sdk_arch:
x64` for every stable Windows release. There is also no winget package for the SDK.

**Decision:** Install the x64 SDK (3.44.7) to `C:\src\flutter` and run it under Windows' x64
emulation.

**Rejected:** Waiting for a native build (none announced), or developing the Flutter app in a
Linux VM (heavier, and the existing Android Studio + SDK 36.1.0 + JDK 21 install is already on
Windows).

**Consequences:** Builds are slower than native but functional. `flutter doctor` reports a missing
Visual Studio C++ workload — that affects only Flutter *Windows desktop* targets, which are out of
scope, and is safely ignored.

---

## 10. sqlite-vec over a hosted vector database

**Date:** 2026-07-23
**Status:** accepted (from build plan §2)

**Context:** The RAG layer needs vector storage for a modest corpus — a resume and a handful of
project write-ups.

**Decision:** `sqlite-vec`, embedded in the application process.

**Rejected:** Pinecone, Weaviate, Qdrant, and similar. All are more capable and all introduce a
network dependency, an account, a key to rotate, and a monthly cost, in exchange for scale this
project will never approach. A separate service would also consume part of the VM's 12 GB.

**Consequences:** No separate service to run, monitor, or pay for. The index is a build artefact
regenerated by the ingestion script, so it is gitignored rather than committed; the *source*
content in `backend/data/` is committed and reviewable.

---

## 11. Sentry + PostHog over Firebase or Supabase

**Date:** 2026-07-23
**Status:** accepted (from build plan §2)

**Context:** Error tracking and product analytics are needed across three very different runtimes:
Python on the server, JavaScript in the browser, and Dart on mobile.

**Decision:** Sentry for errors across backend, web, and mobile. PostHog for analytics across web
and mobile.

**Rejected:**
- *Firebase (Analytics + Crashlytics):* a perfectly good default, and so ubiquitous it
  demonstrates nothing.
- *Supabase for web + Firebase for mobile:* two unrelated tools with no shared reasoning behind
  the split — the worst answer, because it looks like an accident rather than a choice.

**Consequences:** Each tool spans multiple layers, so the observability story is one coherent
decision rather than one tool per platform. Costs three more secrets to manage
(`SENTRY_DSN_*`, `POSTHOG_API_KEY_*`). Note that Sentry DSNs and PostHog project keys are
publishable by design and are expected to appear in client code — unlike `ANTHROPIC_API_KEY`,
which must never.

---

## 12. flutter_local_ai over a bundled on-device model

**Date:** 2026-07-23
**Status:** accepted (from build plan §2)

**Context:** The mobile app needs on-device summarisation, mirroring the browser's WebLLM layer.

**Decision:** `flutter_local_ai`, which wraps Apple's Foundation Models on iOS and Gemini Nano /
ML Kit GenAI on Android.

**Rejected:** Bundling a quantised model in the app. That would add hundreds of megabytes to the
download, duplicate what the OS already provides, and make the mobile layer a copy of the browser
layer rather than a contrast to it.

**Consequences:** Zero download size and native performance, at the cost of availability —
older devices lack both Gemini Nano and Foundation Models. The app must check availability and
degrade honestly rather than silently falling back to the network, since a silent fallback would
erase the very distinction the app exists to demonstrate.

---

## 13. Conventional Commits for every commit

**Date:** 2026-07-23
**Status:** accepted

**Context:** Requested by LJ immediately after the first commit landed, which had to be amended
and force-pushed to comply.

**Decision:** `<type>[(scope)]: <description>` on every commit. Types: `feat`, `fix`, `chore`,
`docs`, `test`, `refactor`, `ci`, `perf`, `build`. Scopes match top-level directories.

**Rejected:** Free-form messages. Fine for a private scratch repo; this one is public and the
commit history is part of what a reader judges.

**Consequences:** Leaves the door open to automated changelogs and semantic versioning later
without a history rewrite.

---

## 14. Default branch renamed to `master`

**Date:** 2026-07-23
**Status:** accepted

**Context:** The repo was initialised as `main`; LJ asked for `master`.

**Decision:** Renamed local and remote, switched the GitHub default, and deleted `main`.

**Rejected:** A force push. It was requested but is the wrong mechanism — `master` was a new ref
with nothing to overwrite, and a force push would have left `main` in place beside it. Deleting
`main` outright was required, and GitHub refuses to delete a repository's default branch, so the
default had to be switched first.

**Consequences:** No SHAs changed, so nothing was rewritten. **Every CI workflow must target
`branches: [master]`** — a workflow pointed at `main` fires nothing and reports no error, so this
is recorded in `.github/CLAUDE.md` ahead of Phase 7.

---

## 15. The build plan lives in the repo

**Date:** 2026-07-23
**Status:** accepted

**Context:** `PROJECT_PLAN.md` governs every step of the build and was referenced by `CLAUDE.md`
and the `verify-step` skill, but sat in `Downloads`, outside version control.

**Decision:** Moved to `docs/PROJECT_PLAN.md` and committed.

**Rejected:** Leaving it external. It would drift from the repo's own guidance, and a governing
document nobody can see from the repo is not governing anything.

**Consequences:** The plan is versioned alongside the work it describes, and amendments to it show
up in history.

---

## 16. LF line endings pinned for `infra/` and shell scripts

**Date:** 2026-07-23
**Status:** accepted

**Context:** Git on Windows converts checkouts to CRLF by default. `infra/setup.sh` is authored on
Windows and executed on Ubuntu.

**Decision:** A `.gitattributes` pinning `* text=auto eol=lf`, with explicit LF for `*.sh`,
`*.service`, `*.conf`, and `infra/**`, and CRLF for `*.ps1`/`*.bat`/`*.cmd`.

**Rejected:** Doing nothing and fixing it when it broke. The failure mode is a CRLF script landing
on Ubuntu and dying with `bad interpreter: /bin/bash^M` — an error that reads like a typo in the
shebang and reliably wastes an hour.

**Consequences:** This was added ahead of the file it protects, which is a deliberate exception to
the "don't build ahead of the current step" rule: the cost is three lines, and the alternative is
a confusing failure in Step 1.2.

---

## 17. CLAUDE.md hierarchy and two multi-agent orchestrators

**Date:** 2026-07-23
**Status:** accepted

**Context:** LJ asked for proper AI coding infrastructure before the bulk of the code exists.

**Decision:**
- A root `CLAUDE.md` carrying four working principles supplied by LJ, plus four drawn from how the
  project had already gone wrong: follow the plan step by step, secrets discipline, Conventional
  Commits, and never report unobserved success.
- A per-directory `CLAUDE.md` in each layer, recording framework, intended file layout, and
  layer-specific traps.
- Two orchestrators: `.claude/workflows/build-step.js` (coding — survey, competing designs, tests
  first, parallel implementers over disjoint files, integrate, gate) and
  `.claude/workflows/quality-gate.js` (review — six specialist reviewers, adversarial refutation,
  fix, loop).
- Six skills: `implement-step`, `write-tests`, `api-contract`, `quality-gate`, `secrets-audit`,
  `verify-step`.

**Rejected:**
- *Linter/formatter configs, hooks, and a pre-commit framework:* deliberately omitted. None of the
  languages are installed yet, and a hook that misfires is worse than no hook. This would have
  contradicted the Simplicity First principle the same commit introduced.
- *A single generalist review agent:* one reviewer finds the obvious defect and stops. Narrow
  lenses find what each other structurally cannot.
- *Trusting the model to keep parallel file writes disjoint:* file ownership is verified in
  JavaScript instead, because two workers writing one file corrupt each other silently and no test
  catches it.

**Consequences:** Both orchestrators spawn many agents and cost real tokens, so both run only when
explicitly invoked, and both skills carry explicit "when not to use this" guidance. Neither
replaces LJ's `✅ VERIFY`.

---

## 18. Commits use a real email address

**Date:** 2026-07-23
**Status:** accepted

**Context:** `user.email` was unset, and this is a public repository.

**Decision:** `tr1pl3f4ul7@gmail.com`, set repo-locally rather than globally.

**Rejected:** GitHub's `@users.noreply.github.com` address, which keeps the real address out of a
public commit log while still attributing commits to the account.

**Consequences:** The address is visible to anyone who clones the repo. Changing it later would
require rewriting history.

---

## 19. Ubuntu 24.04 LTS with the distribution's Python 3.12

**Date:** 2026-07-23
**Status:** accepted

**Context:** The build plan says "Ubuntu 22.04 or 24.04" (Step 1.1) and "python3.11" (Step 1.2).
Those are incompatible as written — **neither release ships Python 3.11**: 22.04 ships 3.10 and
24.04 ships 3.12. A choice was forced before `setup.sh` could be written.

**Decision:** Ubuntu 24.04 LTS, using the distribution's own Python 3.12. `setup.sh` targets
`python3.12` and installs torch from plain PyPI.

Verified rather than assumed: `torch-2.13.0-cp312-cp312-manylinux_2_28_aarch64.whl` is published
on PyPI, so `pip install` works unmodified on the VM. (24.04 provides glibc 2.39, comfortably
above the `manylinux_2_28` floor.)

**Rejected:**
- *Ubuntu 22.04:* Python 3.10, and standard support ends two years sooner. No advantage.
- *The deadsnakes PPA to obtain exactly 3.11:* adds a third-party archive to a production VM for
  no functional benefit. Every dependency this project uses supports 3.12, and a PPA is one more
  thing that can break an unattended `apt upgrade` or a rebuild months from now.

**Consequences:** A deliberate deviation from the plan's literal "python3.11" — the plan's intent
was a modern Python, not that specific patch line, and hitting 3.11 exactly would have cost more
than it returned. Local development stays on Python 3.11 (decision 8), so **the dev machine and
the VM run different minor versions**. Acceptable because the project pins no 3.11- or
3.12-specific syntax, but it means CI — which should mirror the VM — must target 3.12, and a
version-sensitive bug could in principle appear on one and not the other.

---

## Open decisions

Not yet decided. Each will get a full entry when resolved.

| Decision | Blocked on | Notes |
|---|---|---|
| **Web framework** | Step 3.1 | The plan defers to LJ's choice of design direction. The test tooling follows from it (Vitest vs Playwright). Recorded as open in `web/CLAUDE.md`. |
| **TLS termination** | Step 5.2 | certbot on the VM, or Cloudflare edge TLS with an origin certificate in "full strict" mode. |
| **Contact notification channel** | Step 2.4 | SMTP vs webhook, and the corresponding credentials. |
| **Mobile store submission** | Step 6.4 | Whether Apple Developer / Google Play accounts are in scope at all. |

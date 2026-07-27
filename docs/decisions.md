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
**Status:** accepted — **version choice superseded by decision 23** (the extra-index-URL finding still stands)

**Context:** The dev machine is a Copilot PC (Arm-based Windows). The plan pins
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

**Context:** Flutter publishes no native Arm Windows build — the release manifest lists
`dart_sdk_arch: x64` for every stable Windows release. There is also no winget package for the SDK.

**Decision:** Install the x64 SDK (3.44.7) and run it under Windows' x64 emulation on this Copilot
PC.

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
is recorded in `.github/CLAUDE.md` ahead of Phase 6.

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
than it returned. CI must target 3.12 to mirror the VM.

This initially left the dev machine on 3.11 and the VM on 3.12. That gap is closed by
decision 23.

---

## 20. ufw is the sole firewall; Oracle's blanket REJECT is deleted

**Date:** 2026-07-23
**Status:** accepted

**Context:** Oracle's Ubuntu images ship an iptables ruleset ending in a blanket
`REJECT --reject-with icmp-host-prohibited` on INPUT and FORWARD, persisted in
`/etc/iptables/rules.v4`. The build plan calls for `ufw`. The two interact badly, and the failure
is invisible: the OCI security list allows 80/443, `ufw status` shows them allowed, and the port
is still shut.

**Decision:** `ufw` is the single source of truth. `setup.sh` deletes the blanket REJECT from the
running chains **and** from `rules.v4`, backing the original up to
`rules.v4.pre-ai-portfolio` first.

Two things were tested rather than assumed:
- **Enabling ufw does not displace the REJECT.** It survives and sits ahead of every ufw chain, so
  no ufw rule is ever evaluated.
- **`ufw` and `iptables-persistent` cannot coexist** — the `ufw` package declares
  `Breaks: iptables-persistent`. Attempting to install both fails outright.

**Rejected:**
- *Inserting ACCEPT rules above the REJECT* (the first implementation). It works, but the rules
  cannot be persisted — `netfilter-persistent` comes from `iptables-persistent`, which `ufw`
  breaks — so they would evaporate on the first reboot.
- *Flushing the INPUT chain.* Faster, and a good way to drop your own SSH session mid-run.
- *Dropping ufw in favour of raw iptables.* Contradicts the plan, and hands the reader a less
  conventional setup for no benefit.

**Consequences:** One firewall, one mental model. Oracle's legitimate rules (`RELATED,ESTABLISHED`,
`lo`, ICMP, port 22) are preserved — only the blanket REJECT is removed. Verified by simulated
reboot: re-applying `rules.v4` does not bring it back.

---

## 21. apt operations are bounded and verified

**Date:** 2026-07-23
**Status:** accepted

**Context:** During testing, `apt-get update` hung for over ten minutes against an unreachable
mirror rather than failing. Separately, `apt-get update` **exits 0 even when every index fetch
fails** — the failures are only warnings — so the script reported "package lists current" having
fetched nothing.

**Decision:** All apt calls carry explicit timeouts and bounded retries
(`Acquire::Retries=2`, connect 10s, http 20s). `apt-get update` is judged by inspecting its output
for fetch failures rather than by its exit code, retried up to three times with backoff, and the
script dies with a diagnostic naming the two commands worth running (`getent`, `curl`) if it still
fails.

**Rejected:** Trusting apt's exit code, and accepting apt's default retry behaviour. Both were the
original implementation. A bootstrap that hangs indefinitely is bad on a VM and worse in CI, where
it burns the job's entire timeout before failing with no useful signal. Installing from stale
package lists is a subtler version of the same problem.

**Consequences:** ~30 lines of retry and validation logic — a real cost against Principle 2,
accepted because the failure it prevents is silent and expensive. Note this hardens against
*network* failure, not mirror corruption.

---

## 22. Infrastructure is tested in a container before it touches the VM

**Date:** 2026-07-23
**Status:** accepted

**Context:** Step 1.2 requires proving `setup.sh` is idempotent. The obvious place to run it is the
VM itself.

**Decision:** `infra/test/` boots Ubuntu 24.04 `aarch64` with **systemd as PID 1**, seeds it with
Oracle's real ruleset, runs `setup.sh` twice, and asserts a byte-identical state plus a live HTTP
200 through the firewall and a simulated-reboot check.

**Rejected:**
- *Testing on the VM first.* Rejected on LJ's instruction, and rightly: a bootstrap script that
  can lock you out of your own box via `ufw` is exactly the thing to prove elsewhere first.
- *A plain container without systemd.* `setup.sh` manages units; without an init system it aborts
  at the first `systemctl` and everything below goes untested.

**Consequences:** The container caught three real defects before they reached the VM: `ufw allow
OpenSSH` depending on a package profile that may not exist, the `ufw`/`iptables-persistent`
incompatibility, and apt hanging on network failure. The harness also cost significant time to
stabilise — including a self-inflicted bug where the seed's lone REJECT rule blocked the
container's own DNS replies, which looked for a while like a Docker fault.

A container is not a VM. Real SSH lockout risk, Oracle's actual image contents, and genuine reboot
behaviour are still only provable on the VM.

---

## 23. Local Python aligned to 3.12

**Date:** 2026-07-23
**Status:** accepted — supersedes the version choice in decision 8

**Context:** Decision 19 put the VM on Ubuntu 24.04's stock Python 3.12 while the dev machine ran
3.11, purely because 3.11 was already installed. A dev/production version gap is a latent source
of bugs that reproduce on one and not the other, and it makes CI's target ambiguous.

**Decision:** Install Python 3.12.10 (ARM64) locally. **Local, VM, and CI all run 3.12.**

Verified rather than assumed: `torch-2.13.0+cpu / cp312 / win_arm64` resolves from
`https://download.pytorch.org/whl/cpu`, so the ARM64 workaround from decision 8 works unchanged
on 3.12.

**Rejected:**
- *Keeping the split.* Cheap today, and the class of bug it invites — works locally, fails on the
  VM — is expensive precisely when you can least afford it, mid-deploy.
- *Downgrading the VM to 3.11.* Would need a third-party PPA on the production box, which
  decision 19 rejected for good reason.

**Consequences:** 3.11 remains installed locally and does no harm, but `backend/` targets 3.12 —
the venv must be created with the 3.12 interpreter explicitly, since `python` on PATH may still
resolve to 3.11. `backend/CLAUDE.md` records the exact path.

---

## 24. Oracle's InstanceServices rules re-homed into ufw's before-output chain

**Date:** 2026-07-23
**Status:** accepted

**Context:** Oracle's `rules.v4` defines an `InstanceServices` chain restricting outbound traffic
to the link-local range `169.254.0.0/16` — the metadata service, iSCSI boot volumes, DNS and NTP.
Oracle's documentation asks that it be kept.

Decision 20 removes `netfilter-persistent` as a side effect of installing `ufw`, so nothing
re-applies `rules.v4` at boot. Measured on the VM: **17 InstanceServices rules before a reboot,
0 after.** Nothing breaks — the `OUTPUT` policy is `ACCEPT`, so traffic still flows — but Oracle's
egress hardening silently disappears on the first restart.

**Decision:** `setup.sh` copies the rules into `/etc/ufw/before.rules`, ufw's documented hook for
raw iptables, sourced from the backup taken in decision 20. The chain declaration goes with the
other declarations after `*filter`; the jump goes **inside `ufw-before-output`**, after the last
rule ufw ships there. Both blocks are marker-delimited, and each run rebuilds the intended file
and compares — so a wrongly-placed block from an older run is corrected rather than left alone.

**Rejected:**
- *Appending the jump to `OUTPUT`* — the first implementation, and it was **wrong**. It looked
  right: 17 rules present, `ufw status` clean, site serving. Packet counters showed the chain
  received **zero packets**, because ufw's own chains accept the traffic first. Presence is not
  effectiveness. After the fix the same measurement showed 2 packets: one ACCEPT to the metadata
  service, one REJECT with `tcp-reset` for a probe to a disallowed port.
- *Keeping `netfilter-persistent`* — impossible; `ufw` declares `Breaks` against it (decision 20).
- *Dropping the rules* — a silent, undocumented weakening of the vendor's security posture.

**Consequences:** ufw owns the whole firewall and restores these rules on every boot. The lesson
is written into `infra/test/`: the harness asserts the jump is in `ufw-before-output` and **not**
in plain `OUTPUT`, because the earlier broken version passed a naive "are the rules present?"
check. The packet-counter measurement itself only works on the VM — a container has no route to
`169.254.0.0/16`.

---

## 25. Plain `uvicorn`, not `uvicorn[standard]`

**Date:** 2026-07-23
**Status:** accepted

**Context:** `pip install uvicorn[standard]` fails on this Copilot PC. The extra pulls in
`httptools`, which has **never** published a `win_arm64` wheel — only `win_amd64`, across every
release — so pip falls back to compiling from source and fails. The extra also wants `uvloop`,
which does not support Windows at all.

**Decision:** Depend on plain `uvicorn` everywhere — dev, VM and CI.

**Rejected:**
- *Platform-split dependencies*, e.g. `uvicorn[standard]; sys_platform != "win32"` alongside
  `uvicorn; sys_platform == "win32"`. It works, and it would give the VM the faster HTTP parser
  and event loop. Rejected because it leaves the dev machine and production running **different
  server stacks** — precisely the divergence decision 23 removed by aligning Python to 3.12. A
  bug that only appears under `httptools` would be invisible locally.
- *Building `httptools` from source locally.* Requires a C toolchain, on every machine, forever,
  for no measurable gain.

**Consequences:** Slower HTTP parsing and the default asyncio event loop. Not measurable for this
workload: every `/chat` and `/contact` request waits on a network round-trip to the Claude API,
which dominates latency by orders of magnitude. Also loses `watchfiles` (`--reload` falls back to
stat polling) and `websockets` (unused). Worth revisiting only if profiling ever shows the server
loop as a bottleneck, which for a portfolio site it will not.

This is the third ARM64 packaging trap on this project, after torch (decision 8) and the Flutter
SDK (decision 9).

---

## 26. sqlite-vec retained; backend tests run in a Linux container

**Date:** 2026-07-23
**Status:** accepted

**Context:** `sqlite-vec` publishes wheels for macOS x86 and ARM, Linux x86 and aarch64, and
Windows x64 — but **no `win_arm64`**. It runs on the Oracle VM and in CI, and cannot run natively
on this Copilot PC. Checked at the same time: `chromadb` and `faiss-cpu` have the same gap.
`numpy` and `onnxruntime` do ship `win_arm64` wheels.

This is the fourth ARM64 packaging trap on this project, after torch (8), the Flutter SDK (9) and
`httptools` (25).

**Decision:** Keep `sqlite-vec`, exactly as the plan specifies. The backend test suite runs inside
a Linux container (`backend/test/`, `python:3.12-slim` on linux/arm64, matching the VM). Tests that
need the extension use `pytest.importorskip`, so a native `pytest` run on Windows still executes
the rest of the suite and skips those rather than erroring.

**Rejected:**
- *Storing embeddings as SQLite BLOBs with numpy cosine similarity.* Works identically on both
  platforms with no native extension, and at ~60 chunks a brute-force scan is trivially fast — an
  ANN index at this corpus size is arguably cargo-culting. Rejected on LJ's call: keeping the
  plan's stated component matters more than the convenience.
- *sqlite-vec in production with a numpy fallback locally.* Reintroduces the dev/production
  divergence removed by decisions 23 and 25. A retrieval bug could appear in one and not the other.

**Consequences:** The dev machine cannot run the full backend suite natively. Anything touching
retrieval must be verified through `backend/test/run-tests.sh` before it is presented — the same
discipline already applied to `infra/`. Dependencies are baked into the test image, including the
embedding model, so the loop stays fast and does not re-download ~90 MB per run. The cost is a
container build whenever `requirements.txt` changes.

---

## 27. Ingestion runs on the VM at deploy time

**Date:** 2026-07-23
**Status:** accepted

**Context:** The vector store has to be built from the markdown corpus somewhere. Either it is
built locally and the database shipped to the VM, or it is built on the VM as part of deployment.

**Decision:** Ingestion runs on the VM at deploy time. `python -m app.ingest` rebuilds the index
from `backend/data/*.md`.

**Rejected:** Building locally and shipping the `.db`. Faster deploys, but the database becomes a
binary artefact to move around and keep in sync, and the local and production stacks diverge again.

**Consequences:** No extra dependency — the VM needs the embedding model regardless, because
incoming queries must be embedded to search. Content updates become the same workflow as code
changes: edit markdown, push, CI deploys, ingestion re-runs.

Ingestion is a **full rebuild**, not incremental. At this corpus size the rebuild is cheap, and it
makes stale chunks structurally impossible: deleting a section cannot leave an orphaned vector
behind that the chatbot would go on citing. Incremental ingestion would earn its complexity at
hundreds of documents, not at sixty chunks.

---

## 28. Embedding model: `thenlper/gte-small`, chosen by measurement

**Date:** 2026-07-23
**Status:** accepted — supersedes the plan's `all-MiniLM-L6-v2`

**Context:** The plan (§2) specifies `sentence-transformers/all-MiniLM-L6-v2`. With it, four of the
eight retrieval test cases failed: the correct chunk landed at rank 5 twice — losing to a FAQ entry
by as little as 0.0075 — and at ranks 8 and 9 in the other two. Three chunks also exceeded the
model's 256-token window, making part of their content invisible to retrieval entirely.

**Decision:** Use `thenlper/gte-small`, and raise `TOP_K` from 4 to 6.

Five candidates were evaluated against the real corpus and the real test queries
(`backend/test/compare_models.py`):

| Model | Dims | Max seq | Truncated | top-4 | top-6 | Embed |
|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | 256 | 3/56 | 4/8 | 6/8 | 0.7s |
| all-MiniLM-L12-v2 | 384 | **128** | **23/56** | 5/8 | 6/8 | 0.8s |
| bge-small-en-v1.5 | 384 | 512 | 0 | 5/8 | 6/8 | 1.9s |
| **gte-small** | **384** | **512** | **0** | **6/8** | **7/8** | 1.9s |
| all-mpnet-base-v2 | 768 | 384 | 0 | 4/8 | 5/8 | 6.1s |

**Rejected:**
- *`all-mpnet-base-v2`* — the largest candidate and the **worst performer**, tied last at 4/8 while
  being nine times slower and 768-dimensional. It ranked "certifications" at #17, a query every
  other model placed in the top 4. Bigger was not better.
- *`all-MiniLM-L12-v2`* — has a **128-token** limit, half of L6's despite being the deeper model,
  and truncated 23 of 56 chunks. The intuitive "L12 beats L6" upgrade would have degraded
  retrieval badly.
- *`bge-small-en-v1.5`* — close behind gte-small, but requires an asymmetric query prefix
  (`"Represent this sentence for searching relevant passages: "`) to perform. Extra complexity for
  a worse score.

**Consequences:** 384 dimensions, so the sqlite-vec schema is unchanged. Zero truncation at 512
tokens. Embedding is ~1.9s for the corpus versus 0.7s — irrelevant, since ingestion runs once per
deploy and a single query embed is milliseconds. `gte-small` is a third-party model rather than one
published by the sentence-transformers project; it is widely used and pinned by name.

**One failure no model fixed:** "What is he doing now?" missed on *all five*, ranking between #7
and #23. That was a corpus problem, not a model problem — nothing in the AI Talent section anchored
to "now". Fixed by rewriting the section to say so explicitly. Worth recording because the instinct
was to reach for a better model, and a better model would not have helped.

---

## 29. Chunks are prefixed with the subject, not the document title

**Date:** 2026-07-23
**Status:** accepted

**Context:** Sections are retrieved in isolation, so a chunk headed "Gruntify" needs to say whose
project it was. The first implementation prepended the document title, giving
`"Employment history — Gruntify\n\n..."`.

That had an unintended effect. Every one of the twelve `faq.md` chunks then began
`"Frequently asked questions — "`, which matches *any* question-shaped query regardless of topic.
A FAQ entry ranked **first for 8 of 12** evaluation queries, crowding out the specific project and
role chunks that actually answered them. "What is his security background?" returned three
unrelated FAQ entries; "the most technically difficult thing he has built" returned "What else is
he interested in?".

**Decision:** Prefix with the **subject** — `"Ljuben Vassilev — {heading}"` — configured as
`CORPUS_SUBJECT` and passed into the chunker, so `chunking.py` holds no corpus-specific knowledge.

Measured across twelve queries (`backend/test/compare_chunk_prefix.py`):

| Strategy | top-4 | top-6 | FAQ ranked #1 |
|---|---|---|---|
| Document-title prefix | 8/12 | 8/12 | **8/12** |
| No prefix | 6/12 | 8/12 | 5/12 |
| **Subject prefix** | **8/12** | **9/12** | **4/12** |

**Rejected:** *No prefix at all.* It reduced FAQ dominance but lost the context that makes an
isolated chunk answerable, and scored worst at top-4.

**Consequences:** What you prepend to a chunk is part of what gets embedded, and boilerplate
repeated across a document becomes a retrieval signal in its own right. Worth remembering before
adding any per-document header to chunk text.

Two remaining failures were **corpus gaps, not retrieval failures** — no phrasing anchored "who
does he work for" or "the most technically difficult thing". Both were fixed by writing the answers
into the corpus, which a portfolio should state plainly regardless. After both changes, "what is he
doing now" and "the most challenging thing he has built" each return the correct chunk at rank 1.

---

## 30. Claude Haiku 4.5 generates `/chat` answers

**Date:** 2026-07-24
**Status:** accepted

**Context:** `/chat` needs a model to turn retrieved chunks into an answer. Every request costs
money, and a visitor is watching a chat widget spin while it happens.

**Decision:** `claude-haiku-4-5`, LJ's call. The model is summarising text that retrieval has
already found and ranked — it is not reasoning from scratch — and Haiku is roughly a fifth of
Opus's per-token price and noticeably faster.

**Rejected:** *Opus 4.8* — more capability than the task needs, at five times the cost per token,
on the highest-volume endpoint in the project. *Sonnet 5* — the fallback if Haiku's answers
disappoint, not the starting point.

**Consequences:** Answer quality now depends more heavily on retrieval and on the system prompt
than it would with a larger model; the grounding rules in `app/rag.py` are doing real work. The
model is a single line in `app/config.py` (`ANTHROPIC_MODEL`) and overridable by environment
variable, so switching to Sonnet is a config change rather than a code change. A test pins the
current value so the choice cannot drift silently — changing the model means consciously changing
the bill.

Haiku 4.5 predates adaptive thinking, so no `thinking` parameter is sent. That is correct for this
workload anyway: the answer is a summary of supplied context, not a reasoning problem.

---

## 31. Rate limiting: two daily ceilings, counted in memory

**Date:** 2026-07-24
**Status:** accepted

**Context:** `/chat` is a public endpoint that spends money at the Claude API on every request. It
needs a spend cap. LJ's instruction was to keep it simple: limit by IP in the backend, and per
calendar day regardless of IP.

**Decision:** Two counters, both keyed on the **UTC calendar date** and both reset at the same
instant — one per client IP (default 20/day), one across all callers (default 500/day). The global
counter is checked first. Both are held in a plain dict in the process, behind one lock, with
check-and-increment as a single operation.

**Rejected:** *A rolling window per IP plus a daily global cap.* Two different time semantics in
one limiter, for no gain at this traffic level — and precisely the mixing LJ asked to avoid.
*Redis or SQLite-backed counters.* Durable across restarts, but a whole storage dependency on a
12 GB box to protect against losing a few requests' worth of budget after a deploy.
*Rate limiting at the Cloudflare Worker (Phase 4).* The edge cannot see requests that reach the VM
directly, so the backend is where the cap actually holds.

**Consequences:**

- **One uvicorn worker is now load-bearing.** Adding workers to the systemd unit would give each
  its own counters and silently multiply both limits. Noted in `app/ratelimit.py` and to be noted
  again in the unit file at Step 2.6.
- Counters reset on restart, so a deploy grants a fresh budget. Cheap, and the alternative costs a
  dependency.
- The window rolls over at 10am Brisbane time rather than local midnight. UTC keeps the reset
  deterministic and independent of daylight saving anywhere; for a spend cap the boundary's
  wall-clock position does not matter, but it is worth knowing when reading the numbers.
- A 429 carries `Retry-After` in seconds until the next reset, and names which of the two limits
  was hit, so the web widget can say something more useful than "try again later".

---

## 32. Client IP is taken from `X-Real-IP`, or the **rightmost** `X-Forwarded-For`

**Date:** 2026-07-24
**Status:** accepted

**Context:** Behind nginx every request arrives from `127.0.0.1`, so the per-IP limit in decision 31
needs the real client address — and it must come from a header a visitor cannot forge, or the limit
is decorative.

**Decision:** Prefer `X-Real-IP`. Fall back to the **rightmost** entry of `X-Forwarded-For`, then to
the socket address.

**Rejected:** *The leftmost `X-Forwarded-For` entry* — the conventional reading, and wrong here. A
client can send its own `X-Forwarded-For`, and nginx's `$proxy_add_x_forwarded_for` **appends** the
real peer to whatever arrived. The leftmost value is therefore attacker-controlled and the per-IP
limit could be bypassed by rotating a fake header; the rightmost is the entry our own proxy wrote.

**Consequences:** The reasoning holds only for **exactly one trusted proxy** in front of the
backend. Adding a second (Cloudflare in front of nginx, at Phase 5) means the rightmost entry
becomes Cloudflare's edge address, and the correct entry moves one position left — `X-Real-IP`
would then need to carry `CF-Connecting-IP`. Re-check this at Step 5.2.

The nginx config at Step 2.6 must **set** `X-Real-IP` from `$remote_addr` (overwriting any inbound
value), not merely pass one through.

---

## 33. Contact notifications go out through Resend over HTTPS, not SMTP

**Date:** 2026-07-24
**Status:** accepted — closes the "contact notification channel" open decision

**Context:** `/contact` has to reach LJ when somebody submits the form. Step 2.4 marks the channel
as a manual choice.

**Decision:** Resend's HTTP API, `POST https://api.resend.com/emails`, called with
`urllib.request`. One secret (`RESEND_API_KEY`), sending-only scope.

**Rejected:** *Raw SMTP.* **Oracle Cloud blocks outbound 25, 465 and 587 by default** on new
tenancies — a mail library would need a support request before it ever delivered anything, and it
needs four secrets rather than one. *A Discord or Slack webhook.* Genuinely simpler, and it was the
recommendation, but LJ wants this in an inbox. *An HTTP client library.* This is one POST a few
times a day; the standard library already does it, and the VM does not need to carry a dependency
for it.

**Consequences:**

- Nothing to open in `ufw` — 443 outbound is already allowed, and SMTP never enters the picture.
- **No domain verification needed.** Resend's shared `onboarding@resend.dev` sender may only
  deliver to the account owner's own address, and the notification goes to LJ and nobody else, so
  that restriction is exactly the requirement. Point `CONTACT_NOTIFY_FROM` at a verified
  `ljubenvassilev.com` address if replies should ever come *from* the domain.
- Free tier is 3,000/month, 100/day, against a rate limit of 50 submissions/day. Comfortable.
- Notification is best-effort: the submission is durable before the send is attempted, and a
  failure leaves the row at `notified = 0` rather than failing the visitor's request.

---

## 34. A contact submission is stored before anything that can fail

**Date:** 2026-07-24
**Status:** accepted

**Context:** `/contact` does three things — store, triage, notify. Two of them are network calls to
services that will eventually be down. The ordering decides what happens to somebody's message when
that day comes.

**Decision:** Write to the store **first**, then triage, then notify. Triage and notification are
both best-effort: they log and continue. Only a failure to store returns an error (503).

**Rejected:** *Triage first, so the stored row is complete.* It makes Anthropic's availability
decide whether LJ receives an enquiry at all. *Failing the request when notification fails.* The
message is already saved at that point; telling the sender to try again would produce a duplicate
and imply their first attempt vanished.

**Consequences:**

- Submissions live in **`data/submissions.db`, not `vectors.db`.** Decision 27 has ingestion rebuild
  the vector store from scratch on every deploy — it is a disposable build artefact, and a
  stranger's message is the opposite of disposable.
- A triage failure still emails LJ, with the raw message and a subject saying triage did not run.
- `notified = 0` is the recovery query: rows that reached the store but never reached him.
- The store holds personal data — a real name, email and message. It stays on the VM, is gitignored,
  and is never printed. Backing it up is a Phase 8 runbook item.
- The sender's response body contains **only** `received` and `reference`. Returning the
  classification would eventually tell someone they had been filed as low-priority spam.

---

## 35. Real credentials are removed from the test process, not just blocked at the boundary

**Date:** 2026-07-24
**Status:** accepted — written after a live leak, not before

**Context:** The suite already refused to construct a real Anthropic client, which is what
`backend/CLAUDE.md` asks for. During Step 2.4 a test reached `rag.get_client()` unmocked — a real
bug, caught exactly as designed. But the guard raises from a function whose `kwargs` hold the API
key, and pytest renders the locals of the frame that raised. **The genuine `ANTHROPIC_API_KEY` was
printed to the terminal.** The outbound call was blocked and the credential leaked anyway.

**Decision:** An autouse fixture replaces both keys with obvious dummies (`sk-ant-api03-TEST-KEY-NOT-REAL`,
`re_TEST_KEY_NOT_REAL`) in `os.environ` and in every module that bound a copy at import. The
boundary guards stay; this sits underneath them. `tests/test_guards.py` pins both properties.

**Rejected:** *Suppressing pytest's locals output.* Treats the symptom, and only for pytest — the
same key would still be in scope for anything else that renders a stack trace. *Not loading `.env`
during tests.* `config.py` reads it at import, before any fixture runs; overriding after the fact is
the reliable point of control.

**Consequences:** A leaked value from the suite is now visibly a fake. The real lesson is more
general and belongs in every later phase: **a guard that blocks an action is not the same as a guard
that removes the capability.** Blocking the call out did nothing about the secret sitting in memory
waiting for a traceback. Prefer taking the credential away over intercepting its use.

The key printed during that run **must be rotated** — the fix above prevents a recurrence but does
nothing about the value already exposed. Update this line once the old key is revoked.

---

## 36. Sentry error tracking, initialised with PII off and a hand-scrub on top

**Date:** 2026-07-24
**Status:** accepted

**Context:** Step 2.5 calls for error tracking before the backend deploys. The obvious risk is the
one the rest of Phase 2 spent effort avoiding: this service handles a stranger's name, email and
message on `/contact`, and a visitor's questions on `/chat`. An error tracker that ships request
context by default would exfiltrate exactly that to a third party, inside every stack trace.

**Decision:** `sentry-sdk` with the FastAPI/Starlette integrations, initialised at module load
(before the app is constructed, so the ASGI integration wraps it), and **off unless `SENTRY_DSN`
is set** — so it does nothing locally or in tests and is a VM-only act. Two layers of privacy:
`send_default_pii=False`, and a `before_send` / `before_send_transaction` hook that additionally
strips the request body, cookies, query string, client IP, and the `Authorization` /
`Cookie` / `X-Real-IP` / `X-Forwarded-For` headers by hand.

**Rejected:** *The SDK quickstart as written.* It relies on `send_default_pii` alone, which is one
default-flip away from leaking, and captures more context than this service can safely send.
*A self-hosted error store.* Real infrastructure to run and secure on a 12 GB box, for a volume of
errors a hosted free tier absorbs trivially. *No error tracking.* Deploying a public service with
no visibility into its failures is the actual bigger risk.

**Consequences:**

- Off by default is load-bearing: forgetting to set the DSN fails safe (no reporting) rather than
  unsafe (reporting to the wrong project).
- The hand-scrub is defence in depth — if a future SDK version changes a default, the events are
  still cleaned on the way out. `test_observability.py` pins every field it removes and, as
  importantly, the fields it keeps (stack trace, error type, request *path*), so scrubbing cannot
  quietly start throwing away what makes an error useful.
- The DSN is write-only, so it is less sensitive than the API keys — but it still lives in `.env`,
  never the repo, and is set only on the VM.
- A hidden `GET /debug/error` raises a fixed-string exception on purpose. It is how the VERIFY step
  is done and the fastest way to confirm reporting still works after any later change. It is out of
  the OpenAPI schema and carries no request data, so triggering it reveals nothing.
- Performance tracing is sampled at 0.1; every *error* is still captured regardless.

---

## 37. First deploy is rsync-from-local over SSH, not a Git pull

**Date:** 2026-07-24
**Status:** accepted

**Context:** Step 2.6 puts the backend on the VM for the first time. The code has to get there
somehow, and the six Phase 2 commits are deliberately local — `origin/master` on GitHub still
sits at the Phase 0/1 infra work.

**Decision:** `infra/deploy.sh` runs from the dev machine and rsyncs `backend/` straight to the VM
over the existing SSH key, then provisions the rest remotely (venv, `python -m app.ingest`, the
systemd unit, the nginx site, restart, `/health` smoke). No push, no clone.

**Rejected:** *Push to GitHub and have the VM clone/pull.* It would force a push now — reversing the
local-only stance — and, for a private repo, a deploy key on the VM. It also front-runs Phase 6,
whose whole job is the path-filtered GitHub Actions pipeline. This first deploy is a bridge to that,
not a substitute for it.

**Consequences:**

- Phase 6 replaces `deploy.sh` with CI/CD. Until then this is the deploy path, and it is manual by
  design — I run it and watch the output.
- `deploy.sh` needs `rsync` on the VM; it is not in `setup.sh`'s package set, so the script
  installs it on first run (a guarded, one-off apt call).
- Ingestion runs on the VM at deploy time (decision 27), so the first deploy is slow: torch and the
  embedding model download before the vector store can be built. Subsequent deploys reuse both.
- The unit file is boot-tested in a container first (`infra/test/verify-unit.sh`) — it reproduces
  the VM's layout, starts the real unit, and asserts `/health` answers, the process is non-root,
  and the service refuses to start without `/etc/ai-portfolio.env`. We do not test in production;
  the unit is proven before the deploy touches the VM.
- The post-deploy smoke test (`infra/smoke-remote.sh`) checks `/health` always, and `/chat` +
  `/contact` only behind `--all`, because those two spend money and send real email. A routine
  redeploy does not, a first deploy does.

---

## 38. The VM environment file must be LF; PowerShell writes CRLF

**Date:** 2026-07-24
**Status:** accepted — written after it bit us

**Context:** The secrets were placed in the local `.env` with PowerShell's `Add-Content` and
`Set-Content`, which write **CRLF** line endings. The first deploy piped that file to the VM with
`cat .env | ssh … install …`, carrying the carriage returns across unchanged. The shape check gave
it away: every value from `.env` was exactly one character longer than expected (a trailing `\r`),
while the one line added with bash `echo` was correct.

**Why it matters:** `systemd`'s `EnvironmentFile` does **not** strip `\r`. The service would have
booted with `ANTHROPIC_API_KEY=sk-ant-…\r` — a key with a garbage byte on the end. `/health` uses
no keys, so it would have gone green; `/chat` and `/contact` would have failed auth and Sentry
would not have initialised. A deploy that looks successful and is quietly broken — the worst kind.
(Note the local smoke tests passed earlier only because Docker's `--env-file` happens to strip
`\r`; systemd does not, which is why it surfaced on the VM and not on the dev machine.)

**Decision:** Strip carriage returns everywhere the env file is handled. The VM copy was fixed in
place (`sed -i 's/\r$//'`), the local `.env` converted to LF (`tr -d '\r'`), and the shape check —
names and byte-lengths, never values — is now the standard proof that a secrets file is clean, on
the VM or locally.

**Consequences:**

- The byte-length check is not cosmetic. A value one longer than expected is a `\r`; run it after
  any PowerShell-authored secrets edit.
- This is the env-file cousin of the shell-script line-ending rule (`.gitattributes` pins `*.sh`
  and `infra/**` to LF). `.env` is gitignored so `.gitattributes` cannot police it — the discipline
  has to live in how the file is written and checked.
- If `deploy.sh` ever grows a path that writes the env file (it does not today — it only reads it),
  that path must normalise line endings.

---

## 39. Visual direction: terminal-native, dark only

**Date:** 2026-07-25
**Status:** accepted — closes Step 3.1

**Context:** Step 3.1 asks for a visual direction before any building. The goals: be memorable,
don't blend in, and keep text short ("smart brevity"). A further question worth settling early was
how far the site should signal its Anthropic-ecosystem affinity visually, given that much of the
intended audience uses these tools daily.

**Decision:** Terminal-native — dark ground (`#0C1013`, near-black with a blue-green bias),
lowercase monospace headings, one teal accent, and **the four-layer inference trace as the hero**.
The page opens by *showing* the architecture running, annotated with where each layer executed and
what it cost, rather than describing it in prose. Dark only.

**Rejected:**

- *Mirroring the Claude desktop app's palette and feel* — considered as the most direct way to
  signal ecosystem affinity, and dropped on three counts. It fights the technical register (that
  identity is warm, soft and editorial). It edges into trade-dress territory, since designing so
  users read a site as an Anthropic product implies an affiliation that does not exist. And
  decisively: warm cream `#F4F1EA` with a serif display and terracotta accent is what current LLMs
  produce **by default** when asked to design anything — so the most ecosystem-native-looking
  option is also the most generic one available.

  The underlying aim survived by targeting the right tool. The daily driver here is **Claude
  Code**, which is a terminal — so terminal DNA delivers the affinity, the technical register,
  distinctiveness and brevity at once, with no visual confusion with anyone's product.

- *Acid-green-on-black* — terminal costume, and the default skin of every other engineer's
  portfolio.

- *A light theme alongside dark* — the register commits to one visual world, and a light variant
  would be a different design rather than a translation of this one.

**Consequences:** The palette must do work, not decorate: cool = runs near the visitor, warm = runs
on LJ's infrastructure (see `docs/design-system.md`). The trace is the whole bet — if it does not
land, the page has no hero. Every number in it must be **real and measured at request time**;
faking a latency would make the site a lie about the thing it exists to demonstrate.

---

## 40. Web: Vite + vanilla TypeScript, tested with Vitest

**Date:** 2026-07-25
**Status:** accepted — closes the "web framework" open decision

**Context:** The plan says "HTML/CSS/JS (or lightweight framework)" and defers the choice to Step
3.1, because the test tooling follows from it. `web/CLAUDE.md` forbade picking unilaterally.

**Decision:** Vite with vanilla TypeScript. No component framework. **Vitest** for component and
interaction tests, plus the manual cross-browser check the plan already requires for WebLLM.

**Rejected:** *Astro* — genuinely the best fit on paper for a static page with interactive islands,
but its routing and content-collection strengths are irrelevant to a single page, and it is another
dependency to justify. *SvelteKit / Next.js* — far more than a one-pager needs. *No build step at
all* — loses TypeScript, and WebLLM plus a chat widget is enough state to want type safety.

**Consequences:** The decisive argument is already a rule in `web/CLAUDE.md`: *"Model download is
the UX problem… keep the page fast without the model loaded."* WebLLM pulls hundreds of megabytes,
so every kilobyte of framework JavaScript competes with the one download that actually matters.
Three small islands — chat widget, summariser, contact form — do not justify that cost.

Vitest is Vite-native, so testing needs no extra configuration. If the page later grows past what
vanilla TS handles comfortably, revisit this rather than bolting a framework on top.

---

## 41. Design tokens are generated into both clients, never hand-written

**Date:** 2026-07-25
**Status:** accepted

**Context:** LJ asked for a shared design system so the web page and the Flutter app look like one
product. The two clients cannot read each other's formats — CSS custom properties mean nothing to
Dart.

**Decision:** `design/tokens.json` is the single source of truth. `python design/generate.py`
emits `web/src/styles/tokens.css` now, and `mobile/lib/theme/tokens.dart` from Phase 7 onwards
(the Dart target is skipped until `mobile/lib/` exists, so nothing is pre-created for an unreached
phase). Both outputs are committed and neither is ever hand-edited. `--check` fails when they are
stale, ready to wire into CI at Phase 6.

**Rejected:** *An external design tool* (Figma, Penpot) as the source of truth — an account, a
manual export on every change, and a source of truth living outside version control. *Hand-mirrored
values with a "keep these in sync" comment* — which is exactly what the `api-contract` skill exists
to prevent for the API, and design drift is worse because it is **silent**: nothing fails, the two
clients simply stop looking like one product.

**Consequences:** Changing a colour is now: edit the JSON, regenerate, commit both files. A
generated file edited by hand is reverted on the next run, which is the intended behaviour. This
adds a small Python step to a JavaScript and Dart workflow — acceptable, since Python is already
the repo's scripting language and the alternative is a Node dependency that exists only to move
twenty values around.

---

## 42. Both store submissions are in scope

**Date:** 2026-07-25
**Status:** accepted — closes the "mobile store submission" open decision

**Context:** Step 7.4 is written as optional and asks whether Apple Developer and Google Play
Developer accounts are in scope, since producing a build artefact does not require either.

**Decision:** Both are in scope. The Flutter app ships to the **Apple App Store** and **Google
Play** from the one codebase. Step 7.4 stops being optional.

**Rejected:** *Build artefacts only.* Enough to demonstrate the app runs, and free — but a
published listing is materially stronger evidence than a `.apk` in a release page, and shipping
through review is itself part of the mobile skillset the portfolio is arguing for.

**Consequences:**

- **A Mac is required for iOS, and the dev machine is a Windows Copilot PC.** Flutter cannot build
  or sign an iOS app off macOS — this is the hard constraint of the whole phase and it has no
  workaround on Windows. The repo being **public** resolves it cheaply: GitHub Actions provides
  free `macos` runners for public repositories, so iOS builds and uploads can run in CI without
  owning Apple hardware. Confirm that at Phase 7 rather than assuming it, and treat "no Mac" as a
  live risk until an iOS archive has actually been produced.
- **First recurring cost in the project.** Apple Developer Program is charged annually
  (~99 USD at time of writing); Google Play is a one-off registration (~25 USD). Verify both at
  signup. Everything else here has been deliberately free-tier — decision 4 exists precisely to
  keep the cloud bill at zero — so this is a conscious exception, not drift.
- **Both stores require accurate data-collection declarations** (Apple's privacy labels, Google
  Play's Data Safety form). The app sends visitor-authored text to the backend and on to the
  Claude API, and the contact form collects a name, an email address and a message. Those answers
  must match what the code actually does; the `/contact` triage flow and its retention are the
  parts to describe carefully.
- **Phase 7 gains signing secrets**: an Android upload keystore and Apple certificates plus a
  provisioning profile, added to §5 of the plan. `mobile/android/key.properties` is already
  gitignored. Signing material never enters the repo.
- Review timelines are outside our control and can add days. Do not schedule the store submission
  as the last task before showing the portfolio to anyone.

---

## 43. On-device summariser: transformers.js over WebLLM

**Date:** 2026-07-25
**Status:** accepted for the engine choice; the model and device-branching below are superseded by
[decision 44](#44-on-device-project-finder-retrieval-instead-of-generation), which replaced the
summariser entirely. Supersedes the plan's "using WebLLM" wording for Step 3.3.

**Context:** Step 3.3 named WebLLM, which only runs on WebGPU. LJ's own dev machine — a Copilot PC
— got "No WebGPU adapter is available" in real Chrome. Research showed this is not a bug in the
widget: Chrome and Edge ship WebGPU disabled by default on Copilot PCs
([gpuweb/gpuweb#5272](https://github.com/gpuweb/gpuweb/issues/5272), filed against the same
hardware class), gated behind the experimental `chrome://flags/#enable-unsafe-webgpu` flag. LJ
enabled that flag and it still found no adapter — a driver-level gap underneath the browser's
blocklist, not a flag away from fixed. WebLLM has no fallback path for this; it is WebGPU or
nothing.

**Decision:** Replace WebLLM with [transformers.js](https://github.com/huggingface/transformers.js),
running `onnx-community/Qwen2.5-0.5B-Instruct`. It runs on WASM by default — every browser has
that — and upgrades to WebGPU automatically when `chooseDevice()` confirms a real adapter with
`shader-f16` support, rather than trusting `navigator.gpu`'s mere presence (which is exactly what
was true, and misleading, on LJ's own machine).

**Rejected:**

- *Keep WebLLM, improve the failure message only.* Matches the plan exactly and is a smaller
  change, but does nothing for a visitor on this class of hardware — and LJ's own laptop is that
  hardware. Asking a recruiter to flip an experimental browser flag is not a real fallback.
- *Run both engines, WebLLM where WebGPU exists and transformers.js elsewhere.* Two inference
  paths to maintain for one small widget, against Principle 2 (Simplicity First) — transformers.js
  alone already covers both cases through one API.
- *ONNX Runtime Web's own multi-provider fallback* (`device: 'auto'`, letting the runtime try
  WebGPU then WASM itself). Rejected in favour of our own adapter check: `'gpu' in navigator` is
  all transformers.js's own availability check does internally, which is the exact condition that
  is true and useless on LJ's machine. Multi-provider EP fallback also has a documented open issue
  for at least one other provider (webnn) not falling back cleanly on an init error, so a single
  explicit device chosen ahead of time is more predictable than trusting the chain.

**Consequences:**

- Smaller model than planned: Qwen2.5-0.5B-Instruct instead of Llama-3.2-1B-Instruct. Weaker
  summaries, accepted because the model runs on every device rather than a subset.
- Two download weights depending on device: ~512 MB (q8, WASM) or ~483 MB (q4f16, WebGPU) for the
  model, plus the WASM build of ONNX Runtime Web itself (~24 MB) the first time any visitor without
  a working WebGPU adapter uses it — fetched lazily, on click, same as the model weights.
- WASM generation is genuinely slower than WebGPU — CPU-bound token generation, expect tens of
  seconds rather than a few, for a three-to-four-sentence summary. The widget reports the actual
  measured time and which device ran, so this is disclosed rather than hidden.
- `web/CLAUDE.md`'s "On-device model" row is updated to match. `docs/PROJECT_PLAN.md`'s Step 3.3
  wording is left as originally written, per the standing convention for this log (see decision 28
  for the embedding-model precedent) — this entry is the record of what was actually built.

---

## 44. On-device project finder: retrieval instead of generation

**Date:** 2026-07-25
**Status:** accepted — replaces the summariser built under decision 43 with a different feature

**Context:** Decision 43 fixed the availability problem (transformers.js runs everywhere WebLLM
couldn't) but not a deeper one. LJ tested the shipped summariser against the real
`Qwen2.5-0.5B-Instruct` model on WASM and got two results, not one: a 283-second wait for a single
summary, and a summary that invented facts — "ten years in AI development" (false: ten years total
career, AI is the recent specialisation), "languages including Unity3D" (Unity3D is a game engine,
not a language), unearned claims like "known for his ability to create complex AI systems." No
system-prompt change reliably stops a sub-1B model from filling gaps with plausible fiction when
asked to freely generate prose about a multi-paragraph biography — that is a capability ceiling of
models this size on open-ended generation, not an implementation bug. On a page whose entire
argument is that the numbers and claims shown are real, a feature that lies is worse than no
feature.

**Decision:** Replace free-text summarisation with retrieval. The widget now embeds the real
`<li class="work-item">` project entries already in `index.html` plus whatever the visitor typed,
using `onnx-community/all-MiniLM-L6-v2-ONNX` (encoder-only, `q4`, ~54 MB), and reports whichever
project sits closest by cosine similarity — implemented in `web/src/project-finder.ts`. The result
is always one of the real entries on the page; the model is never in a position to say anything
that isn't already true, because it isn't generating text, only pointing at some.

This also resolved the speed and size problems as a side effect rather than requiring separate
fixes: an encoder-only model needs no KV cache and no autoregressive loop, so embedding a short
query is a single forward pass measured in tens of milliseconds, not the 283 seconds the generative
version took. The WebGPU/WASM device split decision 43 built became unnecessary too — an embedding
model this cheap per call doesn't need GPU acceleration to feel instant, so the widget now always
runs on WASM, and that whole branch of complexity was deleted along with it.

**Rejected:**

- *Keep generation, pick a smaller model and fix the threading.* Considered: adding
  `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` headers would let ONNX Runtime Web's
  threaded WASM backend run (LJ's 283s wait was on a single thread, blocking the page for its
  entire duration), and a smaller decoder would download faster. Rejected because neither touches
  the actual complaint — hallucination is a property of asking a small model to freely generate,
  not of how fast or how large it is. A faster liar is still a liar.
- *Cut the browser layer entirely, rely on the Flutter app's on-device story.* Seriously
  considered — `flutter_local_ai` calls the OS's own shipped model (Apple's on-device Foundation
  Model / Android's Gemini Nano), which is dramatically more capable and needs no download at all,
  and `mobile/CLAUDE.md` already frames that contrast with web deliberately. Rejected because it
  would drop the hero's "four different places" thesis to three and required rewriting the
  page's central pitch, when a same-scope fix (change the task, not the count of layers) was
  available.
- *Keep the four-layer count but replace the browser demo with something unrelated to the
  project content* (e.g. a generic on-device classifier). Rejected because retrieval over the
  actual project list is strictly more relevant to a portfolio visitor than a disconnected demo,
  and reuses content that already exists rather than inventing a new corpus to maintain.

**Consequences:**

- `web/src/summariser.ts` and `web/src/profile.ts` are deleted. The condensed-bio text in
  `profile.ts` no longer has a consumer — project text is read straight from the DOM
  (`readProjects()`) instead of maintained as a second copy, closing the drift risk that a
  duplicated corpus would have created.
- No cancel-download affordance was added, despite LJ asking for one against the old ~500 MB
  generative download. transformers.js exposes no abort/cancel hook for an in-flight model fetch
  (confirmed by reading the installed package's source, not assumed), and at ~54 MB the download
  is fast enough on any real connection that the original motivation — a visitor stuck waiting
  minutes for something they no longer want — mostly no longer applies. Revisit if a slow-connection
  visitor reports otherwise.
- The matched project is highlighted (`.work-item.is-matched`, `--color-signal` outline), so the
  browser layer's result visibly lands on the same real content the visitor can already see and
  read — a stronger demonstration than a disconnected text output. An earlier version also
  scrolled the match into view; dropped after live testing found it disorienting — a visitor
  mid-read in this section shouldn't get yanked elsewhere without asking.
- `web/CLAUDE.md`, root `CLAUDE.md`, `README.md`, `mobile/CLAUDE.md`, and the `write-tests` skill
  are updated to describe the project finder rather than the summariser. `docs/PROJECT_PLAN.md`'s
  Step 3.3 wording is left as originally written, same convention as decisions 28 and 43.

---

## 45. Edge Worker tests run in a Linux container; workerd has no Windows ARM64 build

**Date:** 2026-07-26
**Status:** accepted

**Context:** `npm install` in `edge/` fails outright on this Copilot PC: `workerd` — the runtime both
`wrangler` and `@cloudflare/vitest-pool-workers` shell out to — throws `Unsupported platform:
win32 arm64 LE` from its own install script. Unlike sqlite-vec (decision 26), this isn't a partial
gap where native `pytest` still runs and only the affected tests skip — `npm install` cannot
complete at all, so nothing in `edge/` runs natively here, not even a `--dry-run`.

This is the fifth ARM64 packaging trap on this project, after torch (8), the Flutter SDK (9),
`httptools` (25) and `sqlite-vec` (26).

**Decision:** Run the edge test suite inside a Linux container, exactly the pattern
`backend/test/` already uses for sqlite-vec: `edge/test/Dockerfile` builds a `node:24-slim` image
with `npm install` baked in (workerd's `linux/arm64` binary resolves fine there), and
`edge/test/run-tests.sh` bind-mounts the source with an anonymous volume over `node_modules` so
the image's Linux-built dependencies aren't shadowed by whatever — or nothing — sits in the
host's own `node_modules`. `package-lock.json` is generated inside the container and copied back
out to commit, since a lockfile resolved on Windows would be missing the platform-specific
optional dependencies entirely.

Also needed: `@cloudflare/vitest-pool-workers`'s `cloudflareTest()` plugin starts a live remote
proxy connection to Cloudflare merely from `wrangler.toml` declaring an `[ai]` binding — Workers AI
has no local simulation, so the pool tries to authenticate against the real service before a
single test runs, and fails non-interactively without `CLOUDFLARE_API_TOKEN`. Set
`remoteBindings: false` in `vitest.config.ts`: nothing in this suite touches the pool-injected
`env` at all (edge/CLAUDE.md's own rule — classification stays pure and separately testable —
means every test builds its own fake `env` and calls `worker.fetch()` directly), so the real
binding was never needed for these tests in the first place.

**Rejected:**
- *Skip edge/ testing on the dev machine, same as sqlite-vec's `importorskip` pattern.* Not
  available here — sqlite-vec's failure is a Python import-time error inside an otherwise-working
  interpreter; `workerd`'s is a fatal `npm install` failure that stops the whole package from
  existing locally. There's no partial state to skip from.
- *Install workerd's x64 build under Windows' x64 emulation, mirroring decision 9's Flutter SDK
  workaround.* npm's package resolution picks the platform-tagged optional dependency matching
  `process.platform`/`process.arch` of the Node binary actually running the install, not an
  emulation layer beneath it — there is no x64 Node install on this machine to invoke it from, and
  adding one just to route around a single package felt like more permanent surface than a
  container that already exists for exactly this class of problem.

**Consequences:**
- Before presenting any edge/ work for verification: `cd edge/test && ./run-tests.sh`, matching
  `backend/test/run-tests.sh`'s existing convention exactly.
- `edge/vitest.config.ts` documents the `remoteBindings: false` reasoning inline, so a future
  binding that genuinely needs the pool-injected `env` (and therefore real remote access) doesn't
  get silently broken by copying this file without reading the comment.
- The actual `wrangler dev` live smoke test the plan requires (Step 4.1's manual clean/spam
  verification) still needs real Cloudflare Workers AI enabled and `wrangler` authenticated — the
  container only covers the pure unit-test layer, not that step.

---

## 46. Edge classifier model: `@cf/meta/llama-3.1-8b-fast-v2`, not `llama-3.2-1b-instruct`

**Date:** 2026-07-26
**Status:** accepted

**Context:** Running Step 4.1's required manual smoke test (`edge/CLAUDE.md`, decision 45's
consequences) surfaced two real bugs, both only visible once the test was actually exercised for
real rather than trusted from a prior report:

1. `edge/test/Dockerfile`'s `node:24-slim` base has no CA certificate bundle at all — confirmed
   with `dpkg -l | grep ca-cert` and `ls /etc/ssl/certs/ca-certificates.crt` inside the running
   container, both empty. Every `env.AI.run()` call therefore failed TLS validation
   (`kj/compat/tls.c++:269: TLS peer's certificate is not trusted`), and `classify()`'s intentional
   fail-open (`edge/CLAUDE.md`: "Fail open, not closed") silently turned every submission "clean"
   regardless of content. A prior smoke-test pass reported in this same step was invalid — it
   never exercised classification at all, only the fail-open path.
2. With certs fixed, `@cf/meta/llama-3.2-1b-instruct` answered backwards on both of the plan's own
   representative test cases — a plain hiring enquiry classified `SPAM`, an obvious SEO/casino/crypto
   blast classified `CLEAN` — reproduced four times for consistency (`temperature: 0` makes this
   deterministic per input, not evidence either way of general reliability) and confirmed against
   Cloudflare's raw Workers AI REST API directly, bypassing the Worker entirely, to rule out a bug
   in `classify.ts`'s own parsing or prompt-construction code. One prompt-engineering attempt
   (few-shot examples) fixed the hiring-enquiry case but caused the model to refuse the casino/crypto
   case outright (`"I cannot provide a"`), which the existing "does the reply start with SPAM"
   parse also treats as `clean` — no net improvement.

**Decision:** Swap the classifier model to a Workers AI 8B-class instruct model, keeping the
existing system prompt and parsing logic unchanged (both are known to work — decision 45's
container/pool setup already unit-tests `classify()`'s pure logic against a mocked `AiRunner`).
The specific model ID needed a second correction: `@cf/meta/llama-3.1-8b-instruct` returns correct
results over the raw REST API (which silently aliases deprecated IDs to their replacement) but
throws inside the `env.AI` Workers binding itself — `5028: This model was deprecated on
2026-05-30. Please use an alternative model.` — caught by `classify()`'s fail-open catch block,
so every submission again went silently "clean" with no visible error until a temporary
`console.error` in the catch block surfaced it. The REST API's own responses named the model that
actually served the request — `@cf/meta/llama-3.1-8b-fast-v2` — so that's the ID now pinned in
`edge/src/classify.ts`. Repeated smoke-test rounds after the fix showed correct, consistent
classification on both the original and a second worded-differently hiring enquiry, and on a
repeat of the casino/crypto spam message.

**Rejected:**
- *Keep the 1B model and iterate further on the prompt.* The one attempt made traded one failure
  mode (backwards classification) for another (outright refusal on the clearest spam example) with
  no net gain, for a model this project's own `edge/CLAUDE.md` already flags as "small and will be
  wrong sometimes." An 8B model's cost is still tiny for a low-volume portfolio contact form.
- *Add a deterministic keyword pre-filter in front of the AI call.* Would have removed reliance on
  the small model for the obvious cases, but adds a second piece of classification logic to
  maintain and tune (keyword lists rot) for a problem the 8B model solved outright with the
  existing prompt, unchanged.

**Consequences:**
- `edge/src/classify.ts`'s `MODEL` constant is now `@cf/meta/llama-3.1-8b-fast-v2`; the existing
  unit test (`test/classify.test.ts`) asserts against the exported `MODEL` constant rather than a
  hardcoded string, so it needed no change.
- Workers AI model IDs used via the `env.AI` binding can be deprecated and start throwing without
  warning at the REST-API layer, since Cloudflare aliases deprecated IDs there but not inside the
  binding. A model swap in `edge/` should re-run the live `wrangler dev` smoke test, not just the
  mocked unit suite, to catch this class of failure — the unit tests cannot see it, since they
  mock `AiRunner` entirely.
- The plan's Step 4.1 manual verify (LJ confirming correct routing) is still outstanding: the
  backend's own real per-IP daily rate limit (5 requests/day, decision TBD) was exhausted by this
  step's repeated testing against the live Oracle VM, so the final "clean submission actually
  reaches the backend" hop currently returns the backend's own 429 rather than a success response.
  This is expected and unrelated to classifier correctness — the classification itself (clean vs.
  spam, and spam's early-return-without-forwarding behaviour) was fully confirmed via container
  logs and response shapes.

---

## 47. Step 4.2's clean-forward verify deferred to after Step 5.1

**Date:** 2026-07-26
**Status:** accepted

**Context:** `wrangler deploy` succeeded — the Worker is live at
`https://ai-portfolio-contact-filter.tr1pl3f4ul7.workers.dev` — and the spam test case passes
correctly against the deployed Worker (short-circuited with a synthetic receipt, backend never
touched). The legit test case instead returned a Cloudflare edge error, `error code: 1003`, on the
Worker's own `fetch()` subrequest to `env.BACKEND_URL`.

Confirmed via Cloudflare's own support documentation: error 1003 ("Direct IP Access Not Allowed")
fires because `wrangler.toml`'s `BACKEND_URL` is a bare IP literal
(`http://140.238.207.203`) — Workers running on Cloudflare's real production network cannot
`fetch()` a raw IP address, only a domain name. This is a platform-level restriction, not a bug:
the backend itself is confirmed reachable and correctly configured (a direct `curl` from outside
the Worker gets the real `/health` and `/contact` responses). It only surfaces now because
`wrangler dev`'s local simulation doesn't route subrequests through Cloudflare's actual network,
so this same `fetch()` call worked fine in Step 4.1's local smoke test — the deployed Worker is the
first point in the plan where the request genuinely leaves Cloudflare's edge, hence the first place
this restriction can bite.

**Decision:** Leave `BACKEND_URL` as the bare IP for now and defer the clean-submission
live-verify to after Step 5.1 (DNS cutover), rather than inventing an interim domain to unblock it
today. Step 4.2 is the last step of Phase 4, and Step 5.1 immediately follows and is exactly the
step that gives the backend a real domain name — the natural fix arrives one step later regardless
of what's done here. Step 4.2 is otherwise complete: the Worker is deployed, and spam filtering
(the actual point of this phase) is fully verified live. Once 5.1 lands, `BACKEND_URL` gets updated
to the real domain and both live test cases get re-run end to end to confirm the whole path.

**Rejected:**
- *A temporary unproxied DNS-only A record just to unblock today's verify.* Would work, but adds
  a throwaway DNS record to track and later clean up or reconcile with Step 5.1's real cutover, to
  save all of one step's wait — LJ's call, declined in favour of just proceeding to 5.1.
- *Pull Phase 5.1 forward and do the real Cloudflare DNS cutover now.* Skips ahead of the plan's
  own sequencing (CLAUDE.md Principle 5) for a problem that resolves itself by reaching 5.1 in the
  normal order.

**Consequences:**
- Step 4.2's `✅ VERIFY` is: the Worker is deployed, and the spam path is confirmed live. The
  clean-forward path stays unverified against the real backend until Step 5.1 is done.
- `edge/wrangler.toml`'s `BACKEND_URL` must change from the bare Oracle IP to the real production
  domain as part of Step 5.1's own work, not as a separate follow-up — Phase 5's DNS cutover is now
  a hard functional dependency for the edge Worker, not just a cosmetic domain swap.

---

## 48. Domain split: api.ljubenvassilev.com for the backend, contact.ljubenvassilev.com for the Worker, apex reserved for Cloudflare Pages

**Date:** 2026-07-26
**Status:** accepted

**Context:** Step 5.1 needed a real domain for `BACKEND_URL` (decision 47), and the plan's own
wording ("A record → VM IP, proxied") reads as if the whole domain points at the VM. But
`web/CLAUDE.md` already commits the static site to GitHub Pages or Cloudflare Pages, neither of
which is the VM — pointing the apex at the VM now would have to be undone the moment Phase 6
picks one. Separately, the frontend's `web/src/api.ts` used one shared `API_BASE_URL` for both
`/chat` and `/contact`, but only `/contact` is meant to go through the edge Worker — if the
Worker's own hostname were the same one its internal forward targets, that forward would re-match
whatever rule put the Worker there in the first place and re-trigger itself (Cloudflare's own docs
warn about exactly this: a Worker `fetch()`-ing its own bound hostname). Asked LJ directly whether
serving the static site from the VM, GitHub Pages, or Cloudflare Pages was the better choice for a
portfolio meant to demonstrate infra reasoning — see the "Rejected" alternatives below for that
part of the discussion, and a separate detour into whether spreading across more cloud providers
(AWS/GCP/Azure) would strengthen the story, declined for the same reason: it wouldn't demonstrate
anything the current stack doesn't already, just more accounts to secure.

**Decision:** Three-way split, all under the `ljubenvassilev.com` zone (already added to
Cloudflare in Step 0.1):
- `api.ljubenvassilev.com` — A record → the Oracle VM, proxied. Carries `/chat` directly and is
  the target of the Worker's *own* forward to the real `/contact`. No Worker route of any kind
  touches this hostname.
- `contact.ljubenvassilev.com` — a Cloudflare Workers **Custom Domain** (not a path-scoped Route)
  bound entirely to `ai-portfolio-contact-filter`. This is what the frontend's contact form
  actually posts to. Because it's a wholly separate hostname from `api.`, the Worker's internal
  forward can never loop back into itself.
- The apex `ljubenvassilev.com` is left untouched for now, reserved for whichever static host
  Phase 6 sets up.

Cloudflare Pages was chosen over GitHub Pages or serving the static build from the VM itself,
specifically for the portfolio's own sake: the VM option couples the marketing page's uptime to
the backend's (no reason for a chat outage to take the homepage down too) and serves everything
from one Sydney region with no CDN, working against `web/CLAUDE.md`'s own stated priority on page
speed. GitHub Pages works but adds a second, unrelated CDN/TLS provider to reason about for no
benefit, when the project already leans on Cloudflare for DNS, the edge Worker, and Workers AI —
Pages completes that single-platform story rather than fragmenting it.

`web/src/config.ts` now exports `API_BASE_URL` and `CONTACT_BASE_URL` separately (both still
default to `/api` in dev, unchanged local proxy behaviour), and `web/src/api.ts`'s `postJson`
takes an explicit base URL per call — `askQuestion` uses `API_BASE_URL`, `submitContact` uses
`CONTACT_BASE_URL`. All 100 existing web tests passed unchanged, since they only assert the URL
*contains* `/chat` or `/contact`, not the exact origin.

**Rejected:**
- *Serving the static site from the VM.* Couples two independent concerns (marketing page uptime,
  backend uptime) for no benefit, and loses CDN distribution entirely — directly against
  `web/CLAUDE.md`'s page-speed priority.
- *GitHub Pages.* A perfectly normal choice in isolation, but adds a second CDN/TLS provider
  alongside Cloudflare for no reason tied to this project's actual needs, fragmenting rather than
  completing the platform story Workers/Workers AI already started.
- *Spreading further across AWS, GCP, and Azure "to show multi-cloud skills."* Would not add any
  capability the current stack lacks — every inference layer already has a deliberate, justified
  home. More providers means more accounts, more IAM surface, and more billing relationships to
  secure for a demonstration that "I can create accounts on many clouds," which isn't the same
  claim as "I chose infrastructure deliberately." The real multi-provider story (Oracle + Cloudflare
  + Anthropic, each picked for a specific reason) already exists without padding it.
- *One shared `api.` hostname for both the Worker's public endpoint and its own internal forward,
  scoped apart only by path (`/contact` vs the rest).* Technically possible with a path-scoped
  Route instead of a Custom Domain, but leaves a standing footgun: the Worker's own outbound
  `fetch()` to `${BACKEND_URL}/contact` would need to *never* match the very Route pattern that put
  the Worker there, which is fragile to get right and easy to break by editing either side later
  without noticing. A wholly separate hostname removes the possibility outright rather than relying
  on the two patterns never colliding.

**Consequences:**
- `edge/wrangler.toml` carries a `[[routes]]` entry (`contact.ljubenvassilev.com`,
  `custom_domain = true`) and `BACKEND_URL = "https://api.ljubenvassilev.com"`. Adding a route
  also switched off the Worker's own `*.workers.dev` URL by Wrangler's default behaviour once any
  route exists — expected for a Worker that now has a real domain, but means Step 4.1/4.2's
  `*.workers.dev` test URL is no longer live for future ad hoc checks.
- Production web builds now need **two** env vars, `VITE_API_BASE_URL` and
  `VITE_CONTACT_BASE_URL`, wired up whenever Phase 6's CI/CD build step is built — not yet, since
  that's Phase 6's own job.
- Discovered while inspecting the zone: a pre-existing wildcard `*.ljubenvassilev.com` CNAME to a
  domain-parking service (`11776.BODIS.com`), plus apex/`www` A records and an ACME-challenge CNAME
  pointing at what looks like prior free hosting (Epizy/InfinityFree, matching the registrar-observed
  `ns1/ns2.epizy.com`), and existing CAA/MX records — all left untouched as outside this step's
  scope, but Phase 6 will need to replace the apex/`www` records when Cloudflare Pages takes over,
  and should double check the wildcard doesn't shadow anything unexpected. Confirmed these don't
  conflict with `api.`/`contact.` — an exact-name DNS record always wins over a wildcard for that
  name — and confirmed Cloudflare already mirrors all of them, so the nameserver cutover itself
  doesn't break whatever they currently serve.

---

## 49. TLS: Cloudflare edge TLS + Origin CA certificate, Full (strict) mode

**Date:** 2026-07-26
**Status:** accepted

**Context:** Step 5.2 needed to resolve the TLS termination question left open since Step 1.2
(certbot on the VM vs. a Cloudflare origin certificate). With `api.ljubenvassilev.com` and
`contact.ljubenvassilev.com` both already proxied through Cloudflare (decision 48), certbot would
only ever protect the Cloudflare-to-origin leg — visitors never touch the VM directly — while
needing its own separate renewal automation (a cron/systemd timer) on top of what Cloudflare
already manages automatically for everything else in front of it.

**Decision:** Cloudflare's free Universal SSL terminates TLS for visitors automatically — no
action needed once the zone activated. For the Cloudflare-to-VM leg, generated a 2048-bit RSA key
and CSR locally (`openssl req`, in a scratch directory, never in the repo), submitted the CSR to
Cloudflare's Origin CA API (`POST /certificates`, `origin-rsa`, 15-year validity — the certificate
itself is only ever trusted by Cloudflare, so a long validity avoids needless rotation), and
installed the resulting certificate and private key on the VM at `/etc/ssl/cloudflare/`
(`root:root`, key `chmod 600`) — never committed, never round-tripped through this machine after
installation. `infra/nginx/ai-portfolio.conf` now terminates TLS on 443 with that certificate and
redirects 80→443; `ufw` already allowed 443 from Step 1.2. Set the zone's SSL/TLS mode to **Full
(strict)** in the dashboard (the `cloudflare-api` MCP connection could create DNS records but
returned `Unauthorized` for zone-settings and activation-check calls, so this one toggle needed
LJ directly) — Full Strict means Cloudflare validates the origin's certificate is real and
current, not just present, closing the gap a plain "Full" mode would leave.

Verified end-to-end, not just that a certificate loaded: `openssl s_client` against Cloudflare's
actual edge IP (bypassing this machine's stale local DNS cache, the same propagation-lag pattern
seen in Step 5.1) showed a live, currently-valid Google Trust Services certificate for
`CN=ljubenvassilev.com`, accepted by curl's default trust store with no `-k` needed — the same
check a browser makes. Then sent both the plan's spam and legit test payloads to
`contact.ljubenvassilev.com` and confirmed via the backend's own `journalctl` output — not just
the client-visible response, which is identical either way by design — that exactly one real
`POST /contact` reached the VM (the legit message, `200 OK`, sourced from a genuine Cloudflare
edge IP) and the spam message never touched the backend at all. Closes the gap decision 47 left
open in Step 4.2.

**Rejected:**
- *certbot/Let's Encrypt directly on the VM.* Would only secure a leg visitors never traverse
  directly, while adding a second, independently-maintained certificate lifecycle next to the one
  Cloudflare already runs for every other hostname in this project.

**Consequences:**
- Certificate renewal: the origin certificate is valid until 2041, so there's nothing to rotate
  for the life of this project. Cloudflare's own Universal SSL cert (the one visitors see, ~90 day
  validity) renews automatically with no action needed on our side.
- `docs/runbook.md` (Phase 8) should document where the origin cert/key live on the VM
  (`/etc/ssl/cloudflare/`) and that they're Cloudflare Origin CA-issued, not Let's Encrypt, so a
  future reader doesn't go looking for a certbot timer that doesn't exist.
- The Workers Observability query for the edge Worker's own logs came back empty when checked
  during this step's verify — logs may not be enabled for this Worker, or the query needs
  different filters. Not investigated further since the backend's own journal gave a more
  direct, sufficient answer for this step's purposes, but worth revisiting if Worker-side log
  visibility is ever actually needed.

---

## 50. Phases 6 and 7 swapped: CI/CD before the Flutter app, mobile gets its own CI/CD step

**Date:** 2026-07-26
**Status:** accepted

**Context:** The plan originally ran Phase 6 (Flutter Mobile App) before Phase 7 (CI/CD). LJ asked
to swap them — get CI/CD running for what already exists (backend, edge, web) before starting
the mobile app, and fold mobile's own CI/CD, including store publishing, into the mobile phase
itself once there's something to build and publish.

**Decision:** Phase 6 is now CI/CD, scoped to only the three targets that exist by then:
`backend-ci.yml`, `edge-ci.yml`, `web-ci.yml` (added — the original plan's CI step never actually
covered `web/`, an oversight this reorder surfaced), `backend-deploy.yml`, `edge-deploy.yml`, and
`web-deploy.yml` (Cloudflare Pages, decision 48). Phase 7 is now the Flutter Mobile App, with a
new Step 7.5 — Mobile CI/CD and store publishing — added after the existing scaffold/summarizer/
analytics/store-readiness steps, covering `mobile-build.yml` (test, build, and publish to the
Google Play internal track and TestFlight) once Step 7.4's developer accounts and signing
credentials are in place.

This ordering also resolves a structural problem the original order didn't have to face yet: a
"Flutter test workflow" and `mobile-build.yml` can't meaningfully exist in a CI/CD phase that runs
before the Flutter app itself does. Building mobile's CI/CD as part of the mobile phase, right
after the app exists and store readiness is confirmed, means Step 7.5 is building automation
against real, already-written code — the same pattern this project already uses everywhere else
(edge's Worker was built and locally verified before Step 4.2 deployed it; the backend was built
and tested before Step 2.6 put it on the VM).

Corrected every cross-reference to the old phase numbers accordingly: `.github/CLAUDE.md`,
`CLAUDE.md`'s MCP server table, `docs/design-system.md`, and every phase-number mention across
decisions 14, 37, 41, and 47–49 (this decision log's own historical entries) — decision 42's
references to "Phase 7" for the macOS-runner confirmation and signing secrets needed no change,
since Step 7.5 now supplies exactly that within the (renumbered) mobile phase itself. Also fixed
decision 42's own now-stale `Step 6.4` references to `Step 7.4`, and removed the "(optional)" /
"if pursued" framing that decision 42 had already overridden by settling both app stores as in
scope — a pre-existing inconsistency this pass happened to surface, not something introduced by
the reorder itself.

**Rejected:** *Leave the phase numbers as-is and just reorder the work informally.* Would leave
`docs/PROJECT_PLAN.md` — "the governing document" per its own description — actively describing a
sequence nobody is following, which defeats the entire point of a written plan.

**Consequences:**
- Section 5 (secrets checklist) and Section 6 (Definition of Done) needed no changes for the
  reorder itself — both are already phase-agnostic, listing outcomes and credentials rather than
  referencing phase numbers. Section 5 got a separate, unrelated correction at Step 6.1 (decision
  51) when its secret names turned out not to match what the code actually reads.
- Any future reference to "Phase 6" now means CI/CD, and "Phase 7" means the mobile app — the
  opposite of what those numbers meant before this decision. A reader relying on memory rather
  than the current file is exactly the failure mode this entry exists to prevent.

---

## 51. Corrected Section 5's secret names to match what the code actually reads

**Date:** 2026-07-26
**Status:** accepted

**Context:** Step 6.1 needed the exact secret names for Phase 6's GitHub Actions workflows. Section
5 was written early (Phase 0) and drifted from decisions made since: it listed `SENTRY_DSN_WEB`,
`POSTHOG_API_KEY_WEB`, and `POSTHOG_HOST`, but `web/.env.example` and the actual source
(`web/src/observability.ts`, `web/src/analytics.ts`) read `VITE_SENTRY_DSN`, `VITE_POSTHOG_KEY`,
and `VITE_POSTHOG_HOST` — Vite only exposes the `VITE_`-prefixed form to client code, so the
old names would never have worked if used literally. It also still said "SMTP credentials or
notification webhook URL," predating decision 33's move to Resend's HTTP API entirely.

**Decision:** Rewrote Section 5 against the real `.env.example` files rather than by memory, and
split it into three groups instead of one flat list: GitHub Actions secrets Phase 6 actually needs
now, secrets already configured directly on the VM that should *not* become GitHub secrets
(`ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `CONTACT_NOTIFY_TO`, backend `SENTRY_DSN` — decision 37
already established the VM's `/etc/ai-portfolio.env` as their home, and `backend-deploy.yml` only
restarts systemd, it never writes secrets), and what Phase 7 will need once it exists.

**Rejected:** *Add the missing `VITE_` secrets alongside the old wrong names, leaving both.*
Would silently carry forward a checklist item nobody should ever actually create
(`SENTRY_DSN_WEB` was never going to do anything), the exact kind of stale-but-plausible-looking
entry that erodes trust in the rest of the list.

**Consequences:**
- Section 5 now explicitly separates "needed now" from "already handled elsewhere" from "not yet"
  — a future step reading it shouldn't need to cross-check three `.env.example` files again to
  know what actually applies.
- If backend secrets are ever automated into CI (rather than living only on the VM), Section 5's
  "already configured directly on the VM" framing will need revisiting.

---

## 52. `backend-deploy.yml` reuses `infra/deploy.sh` directly; GitHub Secrets becomes the source of truth for backend runtime secrets

**Date:** 2026-07-26
**Status:** accepted

**Context:** `.github/CLAUDE.md`'s workflow table described `backend-deploy.yml` as "SSH to Oracle
VM, restart systemd" — accurate as a summary of the *service* restart, but read as though the
workflow wouldn't actually deploy new code. LJ caught this while reviewing Step 6.1 and asked for
two things: make sure the workflow does a real deploy, and have it supply the backend's runtime
secrets from GitHub Actions rather than relying on `/etc/ai-portfolio.env` having been populated
by hand on the VM (decision 37's original design — never a deliberate security stance, just a
property of a script that ran from a dev machine and had no reason to touch a file the VM already
had).

**Decision:** `backend-deploy.yml` doesn't reimplement deploy logic in YAML — it checks out the
repo and runs `infra/deploy.sh` on the runner, the exact same script and steps already used for
manual deploys (rsync code, rebuild venv and vector store, install the systemd unit and nginx
site, restart, health-check), so there is exactly one deploy path to maintain rather than two that
can drift apart. `deploy.sh` gained one new, narrowly-gated step: when `CI=true` (set automatically
by GitHub Actions, never by a human) and `ANTHROPIC_API_KEY`/`RESEND_API_KEY`/`CONTACT_NOTIFY_TO`/
`SENTRY_DSN` are all present in its own environment, it writes `/etc/ai-portfolio.env` from them
(root-owned, `chmod 640`, piped over SSH via stdin — never a command-line argument or an echoed
value) before the existing env-file guard even runs. A plain local `./deploy.sh` run is
unaffected: without `CI=true`, the file is left exactly as before, still expected to already
exist.

Requiring both `CI=true` and every value non-empty (rather than either alone) means a stray
locally-exported `ANTHROPIC_API_KEY` — plausible if LJ is testing something else in the same
shell — can never accidentally trigger a silent overwrite of the VM's real environment file.

The workflow's own post-deploy smoke test hits `https://api.ljubenvassilev.com/health` — the real
public domain, not the VM's bare IP — deliberately stronger than `deploy.sh`'s own internal
127.0.0.1/nginx checks, since it's the only check in the whole pipeline that exercises DNS,
Cloudflare's edge TLS, and the origin certificate together, on every single deploy.

**Rejected:**
- *Reimplement the deploy steps directly in the workflow YAML.* Two copies of the same logic
  (rsync, venv, vector store, systemd, nginx) that could quietly diverge — exactly what decision
  52 exists to avoid. `deploy.sh` already worked and was already tested manually across several
  real deploys; the workflow's job is to supply credentials and invoke it, nothing more.
- *Leave secrets on the VM, populated by hand, permanently.* Was accepted as a reasonable state
  for `deploy.sh`'s original scope (a manual, local-machine script), but decision 51 already
  flagged it as something "will need revisiting" the moment CI could plausibly own it — this is
  that revisit. A single source of truth in GitHub Secrets means rotating
  `ANTHROPIC_API_KEY` is one action, not "update GitHub *and* remember to SSH into the VM."

**Consequences:**
- Section 5 moved `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `CONTACT_NOTIFY_TO`, and a new
  `SENTRY_DSN_BACKEND` (named to disambiguate from web's `VITE_SENTRY_DSN` in the GitHub UI, written
  into the VM's file as plain `SENTRY_DSN`) from "already on the VM" into "GitHub Actions secrets
  needed now."
- `/etc/ai-portfolio.env` is no longer something LJ needs to maintain by hand going forward, but it
  still needs to exist correctly *once* before the very first CI-driven deploy overwrites it — no
  change needed there, since it's already populated from Step 2.6.
- `deploy.sh`'s header comment "this script never transports or echoes a secret" is no longer
  categorically true — it's true for a local run, not a CI one. The comment was rewritten rather
  than left stale.
- Every future backend runtime secret needs adding in two places: `backend/.env.example` (shape
  reference) and the `for var in ...` list plus the heredoc in `deploy.sh`'s new step — easy to
  forget one, worth checking both when the app's config surface grows.
- Found and fixed a latent bug while in this file for an unrelated reason: `deploy.sh`'s own
  internal nginx health check (step 2h) still curled plain `http://127.0.0.1/health`, unchanged
  since before Step 5.2. Port 80 now redirects to 443 rather than proxying directly, so that check
  had quietly degraded into "did nginx return a redirect" — still exit-0, still logged as a pass,
  no longer actually testing what it claimed to. Fixed to `--resolve
  api.ljubenvassilev.com:443:127.0.0.1` against the real HTTPS path — but the *first* fix was
  itself wrong in a way nothing caught until `backend-deploy.yml`'s actual first live run: a plain
  `curl` against nginx's Cloudflare Origin CA certificate (decision 49) always fails trust
  validation, since no system CA bundle trusts that CA — only Cloudflare's edge does. Added `-k`
  with a comment explaining why it's deliberate: this check's job is "does nginx terminate TLS and
  proxy to uvicorn," not "is the cert publicly trusted" — the workflow's separate post-deploy smoke
  test already covers real trust validation, against the public domain through Cloudflare's actual
  edge, with no `-k`. Nothing had exercised either version of this check between Step 5.2 shipping
  and this step's first real deploy run, which is exactly how both went unnoticed until then.

---

## 53. CI workflows run directly on `ubuntu-latest`, no container; added `ruff` as backend's lint tool

**Date:** 2026-07-26
**Status:** accepted

**Context:** Step 6.2 needed `backend-ci.yml`, `edge-ci.yml`, and `web-ci.yml`. Both `backend/` and
`edge/` have a Docker-container test path for local use (`backend/test/run-tests.sh`,
`edge/test/run-tests.sh`), built specifically because this dev machine is Windows on Arm and
`sqlite-vec` (decision 26) and `workerd` (decision 45) have no wheel/build for that combination.
Neither limitation has anything to do with Linux itself — GitHub's runners are already Linux (x64),
where both install natively, as `.github/CLAUDE.md`'s "Runner architecture" section already
anticipated for the backend case specifically.

Separately, the plan's own Step 6.2 wording ("lint/test") assumed a lint tool existed for the
backend. None did — `requirements-dev.txt` had only `pytest` and `httpx`. Running `ruff check .`
against the untouched codebase surfaced 11 pre-existing issues: unsorted imports, one stale
`# noqa`, one unused import, and one mutable class-level default in a test helper.

**Decision:** All three CI workflows run directly on `ubuntu-latest` with no Docker wrapper —
`backend-ci.yml` (`ruff check` + `pytest`), `edge-ci.yml` (`tsc --noEmit` + `vitest`), `web-ci.yml`
(`npm run build` + `vitest`, deliberately without secrets — the real, secret-injected build is
`web-deploy.yml`'s job, not CI's). Added `ruff==0.16.0` to `requirements-dev.txt` and fixed all 11
existing violations before wiring it into CI, rather than shipping a lint step that's red from its
first run: `ruff check . --fix` resolved 9 automatically (import sorting, the stale `noqa`, the
unused import), one generator-to-set-comprehension rewrite in `app/ingest.py` was applied by hand,
and the mutable default in `tests/test_ratelimit.py`'s `_AlwaysAnswers.messages` helper was
annotated `ClassVar[list]` rather than restructured — the shared list is deliberate there (a
static call-tracking namespace, never instantiated), so the fix is purely the type annotation
ruff asks for, not a behaviour change. Verified: the full 159-test suite still passes in
`backend/test/run-tests.sh`'s Linux container after these changes.

**Rejected:**
- *Reuse the Docker containers in CI, matching the local dev workflow exactly.* Would work, but
  adds a Docker build step and image layer to every CI run for a limitation that is specifically
  about this Windows Arm dev machine and does not exist on GitHub's own Linux runners at all.
- *Skip lint entirely for backend-ci.yml, since none existed before.* The plan explicitly asks for
  "lint/test," and the fixes needed were small and mostly mechanical — not enough reason to leave
  the gap open now that it's been noticed.

**Consequences:**
- Discovered, but did **not** fix, a separate pre-existing gap while verifying `web-ci.yml`'s build
  step locally: `web/CLAUDE.md` says the build should "fail loudly if a dependency ever pushes the
  bundle past a sane size," and `vite.config.ts` sets `chunkSizeWarningLimit: 150` — but Vite only
  *warns* past that limit by default, it doesn't fail the build. Several chunks already exceed it
  today, most unavoidably `transformers.js` itself at ~500 KB gzipped. Making the build actually
  fail on this would need either a higher limit specifically for known-necessary vendor chunks or
  some other CI-side check for genuine app-code bloat — a real design decision, not something to
  make silently while building CI workflows for an unrelated step.
- `edge-ci.yml`/`web-ci.yml` need no Cloudflare or Sentry/PostHog credentials at all — edge's
  `vitest.config.ts` already sets `remoteBindings: false` (decision 45), and web's CI build simply
  runs with both integrations off, exactly as the app already behaves locally without a key.
- Any future backend code needs to pass `ruff check .` before merging — a rule that didn't exist
  before this step.

---

## 54. Cloudflare Pages project `ai-portfolio-web`, bound to the apex and `www`, replacing the old free-hosting DNS

**Date:** 2026-07-26
**Status:** accepted

**Context:** Step 6.3 needed `web-deploy.yml`. Decision 48 had already chosen Cloudflare Pages
over GitHub Pages or the VM, but left the apex domain's actual DNS untouched, since nothing had
built the Pages project yet. The apex and `www` still carried the pre-existing A records to
whatever free host (Epizy/InfinityFree) the domain used before this project — flagged in decision
48 as something Phase 6 would need to replace.

Checked what those records were actually serving before touching them: `curl`-ing
`https://ljubenvassilev.com` through its real, live Cloudflare-proxied path returned HTTP 526
("Invalid SSL Certificate") — Cloudflare's edge already couldn't establish a trusted connection to
that origin. The apex was not successfully serving anything today, proxied or not.

**Decision:** Created the Cloudflare Pages project `ai-portfolio-web` via the API
(`production_branch: master`), confirmed the account's `CLOUDFLARE_API_TOKEN` does **not** have
Pages permission yet (`wrangler pages project list` returned an authentication error) — LJ needs
to add `Account / Cloudflare Pages / Edit` to the existing token via the dashboard, not create a
new one, so the same value already used everywhere keeps working. Deleted the apex and `www` A
records (confirmed already non-functional, per the 526 above) and bound both hostnames to the
Pages project. Cloudflare Pages custom domains, unlike Workers Custom Domains, do **not**
auto-create their own DNS record — the project's `/domains` endpoint returned `status:
initializing` with `"CNAME record not set"` until a CNAME to `ai-portfolio-web.pages.dev` was
created explicitly (Cloudflare's CNAME flattening makes this valid at a bare apex, unlike
standards-compliant DNS elsewhere).

**Rejected:** *Leave the apex DNS alone until LJ manually confirms what the old hosting was for.*
Asked directly instead, given the 526 was concrete evidence nothing there currently works —
LJ confirmed replacing it. MX records (email) are untouched; they're a completely separate record
type from what web-serving DNS changes touch.

**Consequences:**
- `web-deploy.yml` cannot fully deploy until the Pages permission is added to the token — built and
  committed regardless, so it's ready to test the moment that's done.
- `web/src/config.ts`'s `VITE_API_BASE_URL`/`VITE_CONTACT_BASE_URL` are set directly in
  `web-deploy.yml`'s `env:` block as plain values, not GitHub secrets — they're public production
  URLs, not sensitive, the same class as `VITE_POSTHOG_HOST`.
- If the Pages custom domain's `verification_data` still shows `"CNAME record not set"` well after
  the CNAME was created, that's the same kind of Cloudflare-side propagation lag seen in Step 5.1's
  zone activation — not necessarily a misconfiguration.
- Confirmed live: `web-deploy.yml`'s first real run built and deployed successfully, but its own
  smoke test failed with a `522` — the fresh custom domain binding wasn't fully propagated across
  Cloudflare's edge yet, seconds after its very first deploy. The real bug was the smoke test
  itself: curl's `--retry` only retries a fixed set of standard HTTP codes
  (408/429/500/502/503/504), which doesn't include Cloudflare's own 522/524, so `--retry 5
  --retry-delay 5` never actually engaged. Replaced with an explicit bash retry loop (12 attempts,
  10s apart) in both `web-deploy.yml` and `edge-deploy.yml` — the latter has the identical exposure
  the moment its own custom domain is freshly touched, even though it hadn't failed this way yet.
  `backend-deploy.yml`'s smoke test was left alone; `api.ljubenvassilev.com` has been live long
  enough that this specific race isn't a live risk there, and it already has a real successful run
  proving it works as written.

## 55. Edge deploy's smoke test is spam-only, not clean-and-spam

**Date:** 2026-07-26
**Status:** accepted

**Context:** `.github/CLAUDE.md` originally stated the edge smoke test should answer "both a clean
and a spam payload," mirroring Step 4.1/5.2's manual verification. But a clean payload sent
automatically on every `edge/**` push isn't a harmless check — the Worker genuinely forwards it to
the backend, which stores it, triages it with a real Claude API call, and emails LJ a notification
(decision 34's own "store before anything that can fail" design means the side effects are real
and unconditional, not mockable from outside the backend). Asked LJ directly rather than build
this silently, since it's LJ's inbox and Claude spend, not a purely technical call.

**Decision:** The smoke test sends only the spam payload and checks for the correct
`{"received": true, ...}` response shape — proving the Worker deployed correctly, parsed the
payload, called Workers AI, and returned the right shape, entirely without touching the backend.
It deliberately does **not** re-verify that the forward-to-backend path still works on every edge
deploy; that was proven once, by hand, in Step 5.2, and nothing about a typical edge/** change
(prompt tweaks, model swaps, validation logic) touches the forwarding `fetch()` call itself.

**Rejected:**
- *Test both paths, accept a real submission/email/API-call on every deploy.* Technically the most
  complete coverage, but turns every edge code change into a real production side effect — LJ's
  own call to make, and declined.
- *Add a dry-run mode to the Worker so a "clean" test payload can be verified without a real
  forward.* Would give full coverage without side effects, but changes the Worker's actual
  contract/behavior to support a CI concern — a bigger change than this step's scope, worth
  reconsidering later if the forward path starts changing often enough that Step 5.2's one-time
  manual proof stops feeling sufficient.

**Consequences:**
- A regression that breaks specifically the forward-to-backend call (not the classification logic)
  would not be caught by CI — only by another manual check like Step 5.2's, or the next real
  contact submission.
- `.github/CLAUDE.md`'s smoke-test rule and workflow table were updated to state this explicitly,
  so a future edit doesn't "restore" the clean-payload check assuming its absence was an oversight.

## 56. CORS was missing entirely — added an explicit origin allowlist to both the backend and the edge Worker

**Date:** 2026-07-26
**Status:** accepted

**Context:** LJ reported the chat widget failing on the live site with "Couldn't reach the server.
Check your connection." Reproduced directly in a real browser: `fetch('https://api.ljubenvassilev.com/chat', ...)`
from a page loaded on `https://ljubenvassilev.com` threw a generic `TypeError: Failed to fetch` —
browsers deliberately give JS no further detail on this class of failure. Confirmed the actual
cause with `curl`, which does not enforce CORS and so isn't blind to it: an `OPTIONS` preflight
against `/chat` returned `405 Method Not Allowed` with no `Access-Control-Allow-Origin` header at
all, and even the real `POST` itself succeeded server-side (`200`, a genuine answer) but without
that header either — the browser was correctly refusing to hand the response to page JS. No CORS
middleware had ever been configured anywhere in the stack; every prior test of `/chat` and
`/contact` was either server-to-server (`curl`, `TestClient`, one Worker fetching another) or the
local dev proxy, which makes browser requests same-origin on purpose
(`web/vite.config.ts`) — so this gap was invisible until the first real browser hit the first real
production cross-origin request. The edge Worker's `contact.ljubenvassilev.com` had the identical
gap for the same reason, confirmed the same way before it was ever reported.

**Decision:** Added an explicit origin allowlist in both places, admitting exactly
`https://ljubenvassilev.com` and `https://www.ljubenvassilev.com` — never a wildcard, since a
contact/chat endpoint that spends real money per request (Claude API calls) and stores real data
should not answer arbitrary origins.
- Backend: `app.config.ALLOWED_ORIGINS` (comma-separated env var,
  `AI_PORTFOLIO_ALLOWED_ORIGINS`, defaulting to the two production origins) wired in via Starlette's
  `CORSMiddleware` in `app/main.py`, `allow_methods=["POST"]`. New `tests/test_cors.py` pins three
  things: an allowed origin gets preflight approval, a disallowed one doesn't, and — the actual gap
  that shipped — the *real* response carries the header too, not just the preflight.
- Edge Worker: mirrored the same allowlist locally in `src/index.ts` (no shared config module to
  put it in, unlike the backend), handling `OPTIONS` explicitly and wrapping every response path —
  including the one forwarded verbatim from the backend — through a `withCors()` helper. New tests
  in `test/index.test.ts` cover the same three cases, plus confirming CORS wrapping doesn't corrupt
  the forwarded backend body.

**Rejected:** *`allow_origins=["*"]`.* The simplest possible fix, and wrong for exactly this
project: `/chat` spends a real Claude API call per request and `/contact` writes a real database
row and sends a real email, both behind daily spend caps (decision 31) that a wildcard origin does
nothing to protect from being exhausted by an unrelated site embedding a request to this API.

**Consequences:**
- Adding a future web origin (a staging domain, a different subdomain) means updating the allowlist
  in **two** places now — `AI_PORTFOLIO_ALLOWED_ORIGINS` on the VM and the `ALLOWED_ORIGINS` set in
  `edge/src/index.ts` — since the Worker has no shared config mechanism with the backend to draw
  from.
- This shipped to production without either allowlist ever being exercised by a real browser before
  now — Step 5.2 and Step 6.3's own verification all used `curl`/`TestClient`/`wrangler dev`'s local
  proxy, none of which enforce CORS. Worth remembering for future cross-origin work: a
  same-origin-only test suite cannot catch a CORS gap, no matter how thorough.

---

## 57. Portfolio copy moved into six per-section JSON files behind a `/content/*` API, shared by web and the future mobile app

**Date:** 2026-07-27
**Status:** accepted

**Context:** Phase 7 planning surfaced that the mobile app would need the same hero text, project
list, and section copy already hardcoded into `web/index.html`. Two ways to avoid writing it
twice: give mobile its own copy of the same strings (drifts the moment either side edits without
the other), or make the backend the single source of truth both clients fetch from. The same
question applies to the summarizer screen mobile is getting that web has no equivalent of — it
needs backend-served copy of its own, mobile-only, with no web client ever calling it.

**Decision:** Six JSON files under `backend/data/content/` — `profile`, `browser`, `ask`,
`contact`, `projects`, and the mobile-only `summarizer` — each loaded once at import by
`app/content.py` (mirroring `config.py`'s read-once convention) and served by its own `GET
/content/<name>` endpoint, backed by a matching Pydantic model in `schemas.py`. One endpoint per
concern rather than a single combined `/content` payload: `browser` is web-only, `summarizer` is
mobile-only, and a client fetching one shouldn't have to pull the others along — the same
separation-of-concerns reasoning already behind this API's other endpoints. `web/index.html`'s
hero, section copy, and the 17-item project list are now empty elements with stable `id`s,
populated at runtime by `src/render-content.ts` from `src/api.ts`'s fetches, wired together in
`src/main.ts` before any widget mounts.

**Rejected:**
- *A database instead of JSON files.* Considered and pushed back on: this content has exactly one
  writer (LJ editing a file and redeploying), no queries or joins, and git already gives free
  version history and diff review on every change — a database would trade that away for
  concurrency guarantees this content will never need. No admin UI is planned that would want
  query access either.
- *A single combined `/content` endpoint.* Simpler to call once, but couples web and mobile to
  pulling data neither of them displays, and breaks the existing pattern of one schema per concern.

**Consequences:**
- Editing site copy is now a backend deploy, not a web deploy — a wording change no longer needs a
  Cloudflare Pages rebuild, but it does need `backend-deploy.yml` to run.
- Six endpoints to keep in sync across three clients (web now, mobile once Phase 7 builds it, plus
  the backend's own schemas) is more moving parts than the old hardcoded HTML — worth it only
  because mobile is about to need the same data web already renders.
- `web/src/project-finder.ts` reads its corpus by scraping `.work-item` DOM elements lazily on
  first submit, not at mount time, so it needed no changes to keep working against
  dynamically-rendered cards — confirmed by both a unit test and manual verification in a real
  browser.

---

## 58. Mobile app scope: a full five-screen dashboard, not a lean summarizer-only app

**Date:** 2026-07-27
**Status:** accepted

**Context:** Phase 7 planning raised whether chat and contact belong in the mobile app at all —
both already exist on web, and only the on-device summarizer is unique to mobile. Claude Code's
initial recommendation was to descope the app to summarizer + projects only, on the reasoning that
duplicating chat/contact adds surface area without adding a capability the web app doesn't already
have.

**Decision:** LJ overrode that recommendation: build the full app — a home/dashboard screen
carrying the hero text and buttons to four tabs (summarizer, projects, chat, contact) behind
bottom navigation. Explicit reasoning given: this is a portfolio, and a mobile engineer's
portfolio app should demonstrate complete, polished mobile work, not the minimum needed to avoid
duplication. A visibly full-featured app is itself part of what's being demonstrated.

**Rejected:** *Summarizer + projects only.* Would have been the more minimal, arguably more
elegant scope on pure capability-non-duplication grounds, but undersells mobile engineering
experience relative to the web app sitting right next to it.

**Consequences:**
- Step 7.1 now scaffolds all five screens (home, summarizer, projects, chat, contact) rather than
  "an API client hitting `/contact` and `/chat`" as originally scoped — updated in
  `docs/PROJECT_PLAN.md` to match.
- The mobile API client covers every `/content/*` endpoint (decision 57), not just `/chat` and
  `/contact`, since the dashboard, projects, and chat-suggestion-chip screens all need fetched copy
  the same way web does.
- Chat and contact on mobile call the same live backend and edge Worker as web, so they carry the
  same real per-request costs (Claude API call, Resend email) — no separate rate-limit or spend
  consideration was needed since both already sit behind the daily caps decision 31 put in place.

---

## 59. Project cards were invisible on the live site — a scroll-reveal race against decision 57's async content fetch

**Date:** 2026-07-27
**Status:** accepted

**Context:** LJ reported the project cards section missing on the live site after the decision 57
deploy, confirmed by refreshing repeatedly with no change. Investigation ruled out the backend
(`curl` against `/content/projects` returned a real 200 with the correct payload, from a
cache-busted request, with `cf-cache-status: DYNAMIC`) and ruled out a thrown JS error (Sentry
showed zero real errors in the prior 7 days — the SDK itself was confirmed working via the
deliberate `?debug-error` test events from Step 6 — and the browser console showed only unrelated
`ERR_BLOCKED_BY_CLIENT` entries from an ad blocker killing PostHog/Sentry/Cloudflare-Insights
requests, not the app's own code). A direct DOM check on the live page
(`document.getElementById('work-list')`) showed all 17 cards present with `display: grid` and a
real, non-zero height — the content was there, just invisible.

The actual cause: `motion.ts`'s `mountMotion()` runs synchronously at page load, before
`main.ts`'s content fetch resolves — deliberately, so scroll-reveal animations for the page's
static parts don't wait on a network round trip (web/CLAUDE.md: "first paint shouldn't wait on AI
anything"). At that point `#work-list` is still the empty `<ol>` `index.html` ships with (decision
57 removed the hardcoded 17-item list), so `mountMotion()`'s `querySelectorAll(".work-item")` finds
nothing to register with its `IntersectionObserver`. When `renderContent()` later inserts the real
cards, they immediately match `motion.css`'s `.js-motion .work-item { opacity: 0; }` — a plain,
live CSS selector that applies to any matching element regardless of when it was created — but
were never `observer.observe()`'d, so `.is-revealed` never arrives and they stay at `opacity: 0`
forever. Before decision 57, this selector only ever matched elements that already existed at
`mountMotion()` time, so the race was latent and harmless until content became async.

**Decision:** After `renderContent(content)` populates `#work-list`, call `mountMotion(workList)`
again, scoped to just that subtree. `mountMotion()` was already designed to be idempotent
(`splitWords`'s "already-split element is left alone" guard, `prepare()`'s attribute/style writes
being safe to repeat) — the fix is a second, scoped call rather than new machinery. A regression
test in `motion.test.ts` reproduces the exact sequence (empty list → `mountMotion()` → append an
item → scoped `mountMotion()` → confirm it's observed and revealable) so this can't regress
silently again.

**Rejected:**
- *Delay `mountMotion()` until after the content fetch resolves.* Would fix the race but reintroduce
  the problem the current ordering deliberately avoids — every above-the-fold reveal (hero, trace
  rows, headings) would wait on a network round trip it has no need to wait on.
- *Drop `.work-item` from `REVEAL_SELECTOR` entirely.* Removes the race by removing the animation,
  but throws away real design intent (the alternating slide-in on the work grid) to fix a wiring
  bug, not a design problem.

**Consequences:**
- Any future dynamically-inserted content that should participate in scroll-reveal needs the same
  pattern: render it, then call `mountMotion(scopedRoot)` against the container it landed in. This
  is now the second call site (after `renderContent()`'s project cards) and worth remembering if a
  Step 7-style feature adds another async section to the web page.
- `mountMotion()` calling `prepare()` twice on already-settled elements (on a whole-document
  re-scan, not the scoped call used here) is harmless but wasteful — scoping to the specific
  subtree that changed, as done here, avoids that entirely.

---

## Open decisions

Not yet decided. Each will get a full entry when resolved.

| Decision | Blocked on | Notes |
|---|---|---|
| **Scope `CLOUDFLARE_API_TOKEN`'s Workers Routes:Edit permission down to just the `ljubenvassilev.com` zone** | LJ finding the per-zone scoping control in Cloudflare's token editor | Added as All Zones on 2026-07-26 to unblock `edge-deploy.yml` (needed to reconcile the Custom Domain route on every deploy) — broader than necessary, works for now. |

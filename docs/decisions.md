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

**Context:** `pip install uvicorn[standard]` fails on the Windows ARM64 dev machine. The extra
pulls in `httptools`, which has **never** published a `win_arm64` wheel — only `win_amd64`, across
every release — so pip falls back to compiling from source and fails. The extra also wants
`uvloop`, which does not support Windows at all.

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
on the dev machine. Checked at the same time: `chromadb` and `faiss-cpu` have the same gap.
`numpy` and `onnxruntime` do ship ARM64 Windows wheels.

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
local-only stance — and, for a private repo, a deploy key on the VM. It also front-runs Phase 7,
whose whole job is the path-filtered GitHub Actions pipeline. This first deploy is a bridge to that,
not a substitute for it.

**Consequences:**

- Phase 7 replaces `deploy.sh` with CI/CD. Until then this is the deploy path, and it is manual by
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
emits `web/src/styles/tokens.css` now, and `mobile/lib/theme/tokens.dart` from Phase 6 onwards
(the Dart target is skipped until `mobile/lib/` exists, so nothing is pre-created for an unreached
phase). Both outputs are committed and neither is ever hand-edited. `--check` fails when they are
stale, ready to wire into CI at Phase 7.

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

**Context:** Step 6.4 is written as optional and asks whether Apple Developer and Google Play
Developer accounts are in scope, since producing a build artefact does not require either.

**Decision:** Both are in scope. The Flutter app ships to the **Apple App Store** and **Google
Play** from the one codebase. Step 6.4 stops being optional.

**Rejected:** *Build artefacts only.* Enough to demonstrate the app runs, and free — but a
published listing is materially stronger evidence than a `.apk` in a release page, and shipping
through review is itself part of the mobile skillset the portfolio is arguing for.

**Consequences:**

- **A Mac is required for iOS, and the dev machine is Windows ARM64.** Flutter cannot build or
  sign an iOS app off macOS — this is the hard constraint of the whole phase and it has no
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

## Open decisions

Not yet decided. Each will get a full entry when resolved.

| Decision | Blocked on | Notes |
|---|---|---|
| **TLS termination** | Step 5.2 | certbot on the VM, or Cloudflare edge TLS with an origin certificate in "full strict" mode. |

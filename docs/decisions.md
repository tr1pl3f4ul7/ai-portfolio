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

## Open decisions

Not yet decided. Each will get a full entry when resolved.

| Decision | Blocked on | Notes |
|---|---|---|
| **Web framework** | Step 3.1 | The plan defers to LJ's choice of design direction. The test tooling follows from it (Vitest vs Playwright). Recorded as open in `web/CLAUDE.md`. |
| **TLS termination** | Step 5.2 | certbot on the VM, or Cloudflare edge TLS with an origin certificate in "full strict" mode. |
| **Contact notification channel** | Step 2.4 | SMTP vs webhook, and the corresponding credentials. |
| **Mobile store submission** | Step 6.4 | Whether Apple Developer / Google Play accounts are in scope at all. |

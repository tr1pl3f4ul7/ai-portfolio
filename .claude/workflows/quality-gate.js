export const meta = {
  name: 'quality-gate',
  description: 'Orchestrator-workers review loop that iterates on the current build step until it clears a defined quality bar',
  whenToUse: 'After implementing a step from docs/PROJECT_PLAN.md, before presenting it to LJ for VERIFY. Also before any deploy.',
  phases: [
    { title: 'Baseline', detail: 'establish the diff and run the layer test suite' },
    { title: 'Review', detail: 'one specialist worker per quality dimension' },
    { title: 'Verify', detail: 'adversarially refute each finding to kill false positives' },
    { title: 'Fix', detail: 'apply confirmed findings' },
    { title: 'Gate', detail: 're-run tests and evaluate the gate' },
    { title: 'Report', detail: 'synthesise the VERIFY checklist' },
  ],
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const cfg = args || {}
const step = cfg.step || 'unspecified'
const scope = cfg.scope || 'the current uncommitted working diff'
const testCommand = cfg.testCommand || null
const maxRounds = cfg.maxRounds || 3
// 'strict' also blocks on minor findings; default blocks on blocker/major only.
const strict = cfg.strict === true

const BLOCKING = strict
  ? ['blocker', 'major', 'minor']
  : ['blocker', 'major']

// ---------------------------------------------------------------------------
// Worker dimensions. Each is a specialist with ONE lens — diversity is the
// point. A single generalist reviewer finds the obvious and misses the rest.
// ---------------------------------------------------------------------------

const DIMENSIONS = [
  {
    key: 'correctness',
    severityFloor: 'major',
    prompt: `Review ${scope} for CORRECTNESS defects only.

Look for: logic errors, wrong conditionals, off-by-one, unhandled realistic inputs
(empty/malformed payloads, network failure, API timeout), incorrect async handling,
resource leaks, and state that can go inconsistent.

This project has specific correctness traps — check them:
- The Cloudflare Worker must FAIL OPEN. If Workers AI errors or times out, the
  submission must still be forwarded, never silently dropped.
- The backend /health endpoint must not depend on Claude or the vector store.
- The embedding model must load once at startup, not per request (the VM has 12GB
  shared with nginx and the OS).
- Frontend on-device inference must not silently fall back to a server call.

Do NOT report style, naming, formatting, or hypothetical-input issues.
Report only defects with a concrete failure scenario you can describe.`,
  },
  {
    key: 'simplicity',
    severityFloor: 'minor',
    prompt: `Review ${scope} against Principle 2 (Simplicity First) in CLAUDE.md.

Flag ONLY:
- Features or options that were not asked for.
- Abstractions wrapping a single call site.
- Configurability, plugin points, or "flexibility" nobody requested.
- Error handling for scenarios that cannot occur.
- Code that is materially longer than the problem requires.

The test: would a senior engineer call this overcomplicated? If a 200-line
implementation could be 50, that is a finding.

Be concrete. "This could be simpler" is not a finding; "these three wrapper
functions each have one caller and can be inlined" is. Do not propose adding
abstraction — you are looking for excess, not absence.`,
  },
  {
    key: 'scope',
    severityFloor: 'major',
    prompt: `Review ${scope} against Principles 3 and 5 in CLAUDE.md.

This repo is built strictly one plan step at a time. The current step is: ${step}.

Flag:
- Any changed line that does NOT trace to this step's stated deliverable.
- Work belonging to a LATER phase (files created ahead of their owning step —
  see the Repo Map table in CLAUDE.md for which phase owns which directory).
- Drive-by refactors, reformatting, or "improvements" to adjacent untouched code.
- Deletion of pre-existing dead code that was not part of this step.
- Style that diverges from the surrounding file for no reason.

Orphans the change itself created (now-unused imports, variables, functions) are
NOT findings if they were correctly removed — they are findings only if they were
left behind.`,
  },
  {
    key: 'secrets',
    severityFloor: 'blocker',
    prompt: `Review ${scope} for CREDENTIAL EXPOSURE. This is the highest-stakes dimension —
this project has four deploy targets and roughly a dozen secrets.

Flag anything that is:
- A hardcoded key, token, password, DSN, connection string, or private key.
- A real secret in a committed file: wrangler.toml, a systemd unit, a workflow
  YAML, a test fixture, a .env that is not gitignored.
- A secret echoed into logs, error messages, telemetry, or CI step output.
- A gitignore gap that would let one be committed.
- ANTHROPIC_API_KEY referenced anywhere in web/ — client-side code must never hold it.

Note the legitimate exceptions so you do not raise false alarms: the PostHog
project key and the Sentry DSN are publishable by design and are expected to
appear in frontend code.

Severity for any real exposure is ALWAYS 'blocker'.`,
  },
  {
    key: 'tests',
    severityFloor: 'major',
    prompt: `Review ${scope} against the Testing Standard table in CLAUDE.md.

Determine whether this step's work carries the tests the plan requires for its
layer, and flag gaps:
- backend: pytest for logic, TestClient/httpx for endpoints, Claude API MOCKED.
- edge: vitest unit tests over pure classification logic, plus a wrangler dev smoke test.
- web: component/interaction tests; WebLLM verified manually in a real browser.
- infra: shellcheck clean, and idempotent (running twice must be a no-op).

Also flag:
- Any automated test that makes a LIVE Claude API call. Always a finding.
- Tests asserting on implementation detail rather than behaviour.
- Tests that would pass even if the feature were deleted.
- Missing coverage of the failure paths, not just the happy path.`,
  },
  {
    key: 'conventions',
    severityFloor: 'minor',
    prompt: `Review ${scope} against the directory-level CLAUDE.md rules.

Read the CLAUDE.md in whichever directories the change touches and check compliance.
High-value checks:
- backend: config read through app/config.py only; Pydantic response model on every
  endpoint; no per-request model loading.
- edge: classification logic testable without a Workers runtime; no secrets in
  wrangler.toml; decision logged but never the message body (personal data).
- web: backend URL is configuration not a literal; scroll animations honour
  prefers-reduced-motion; model download requires an explicit click.
- infra: LF line endings; set -euo pipefail; idempotent; app runs as non-root.
- Commit messages follow Conventional Commits.

Flag deviations from the documented rule, not from your personal preference.`,
  },
]

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'file', 'severity', 'summary', 'failure_scenario'],
        properties: {
          title: { type: 'string', description: 'Short label, under 60 chars' },
          file: { type: 'string', description: 'Repo-relative path' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          summary: { type: 'string', description: 'One sentence stating the defect' },
          failure_scenario: { type: 'string', description: 'Concrete inputs/state to wrong outcome' },
          suggested_fix: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['real', 'reasoning'],
  properties: {
    real: { type: 'boolean', description: 'true only if the defect genuinely holds' },
    reasoning: { type: 'string' },
    corrected_severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
  },
}

const BASELINE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['summary', 'files_changed', 'tests_ran', 'tests_passed'],
  properties: {
    summary: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    tests_ran: { type: 'boolean' },
    tests_passed: { type: 'boolean' },
    test_output: { type: 'string' },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['applied', 'skipped'],
  properties: {
    applied: { type: 'array', items: { type: 'string' } },
    skipped: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

log(`quality-gate | step ${step} | scope: ${scope} | max ${maxRounds} rounds | strict=${strict}`)

phase('Baseline')
const baseline = await agent(
  `You are establishing a baseline before a review loop. Do NOT change any code.

1. Identify exactly what changed: run 'git status --short' and 'git diff' (plus
   'git diff --cached' for staged work). Scope under review: ${scope}.
2. ${testCommand
    ? `Run the test suite with: ${testCommand}\n   Report the REAL output. Do not summarise a run you did not perform.`
    : 'No test command was supplied. Infer the correct one from the touched directory\'s CLAUDE.md (pytest / vitest / shellcheck) and run it. If no tests exist yet for this step, set tests_ran=false.'}
3. Summarise the change in two sentences.

Report honestly. A failing suite here is expected input to the loop, not a problem to hide.`,
  { label: 'baseline', phase: 'Baseline', schema: BASELINE_SCHEMA },
)

if (!baseline) {
  log('baseline agent failed; aborting so the gate cannot report a false pass')
  return { status: 'error', reason: 'baseline failed' }
}

log(`baseline: ${baseline.files_changed.length} files changed | tests_ran=${baseline.tests_ran} passed=${baseline.tests_passed}`)

const seen = new Set()
const rounds = []
let round = 0
let gatePassed = false
let testsPassing = baseline.tests_ran ? baseline.tests_passed : false

while (round < maxRounds) {
  round++
  log(`--- round ${round}/${maxRounds} ---`)

  // Fan out: every dimension reviews, and each finding is adversarially verified
  // as soon as THAT dimension finishes. No barrier between review and verify.
  const reviewed = await pipeline(
    DIMENSIONS,
    (d) =>
      agent(
        `${d.prompt}

Round ${round} of a quality-gate loop. Files in scope:
${baseline.files_changed.join('\n') || '(see git status)'}

Read the code before judging it. Report only defects you can point at with a file
and a concrete failure scenario. An empty findings array is a perfectly good result
and is far better than padding with speculation.`,
        { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
      ),
    (review, d) => {
      const found = (review && review.findings) || []
      // Drop anything already adjudicated in an earlier round so the loop converges.
      const fresh = found.filter((f) => !seen.has(`${d.key}|${f.file}|${f.title}`))
      return parallel(
        fresh.map((f) => () =>
          agent(
            `Adversarially REFUTE this review finding. Your default position is that it is wrong.

  dimension: ${d.key}
  title:     ${f.title}
  file:      ${f.file}${f.line ? `:${f.line}` : ''}
  severity:  ${f.severity}
  claim:     ${f.summary}
  scenario:  ${f.failure_scenario}

Open the file and check whether the claim actually holds in this codebase. Common
reasons a finding is NOT real:
- The scenario cannot occur given how callers actually invoke the code.
- It is a style preference dressed up as a defect.
- It describes code the current step did not touch.
- It asks for abstraction or handling that Principle 2 explicitly forbids.
- It is already handled elsewhere in the call path.

Set real=false unless the defect genuinely holds. If it holds but the severity is
inflated, set real=true and give corrected_severity.`,
            { label: `verify:${d.key}:${f.title.slice(0, 28)}`, phase: 'Verify', schema: VERDICT_SCHEMA },
          ).then((v) => ({ ...f, dimension: d.key, verdict: v })),
        ),
      )
    },
  )

  const adjudicated = reviewed.flat().filter(Boolean)
  adjudicated.forEach((f) => seen.add(`${f.dimension}|${f.file}|${f.title}`))

  const confirmed = adjudicated
    .filter((f) => f.verdict && f.verdict.real)
    .map((f) => ({ ...f, severity: (f.verdict && f.verdict.corrected_severity) || f.severity }))

  const blocking = confirmed.filter((f) => BLOCKING.indexOf(f.severity) !== -1)
  const advisory = confirmed.filter((f) => BLOCKING.indexOf(f.severity) === -1)

  log(`round ${round}: ${adjudicated.length} raised, ${confirmed.length} survived refutation, ${blocking.length} blocking`)

  rounds.push({ round, raised: adjudicated.length, confirmed: confirmed.length, blocking: blocking.length })

  // ---- Gate ----
  if (blocking.length === 0) {
    phase('Gate')
    const gate = await agent(
      `Confirm the quality gate. Do NOT change code — only verify and report.

${testCommand
        ? `Run: ${testCommand}`
        : 'Run the appropriate test command for the touched layer (see that directory\'s CLAUDE.md).'}

Report the genuine result. If the suite fails, say so — a false pass here defeats
the entire purpose of this loop.`,
      { label: 'gate-check', phase: 'Gate', schema: BASELINE_SCHEMA },
    )
    // A dead gate agent means NOTHING was confirmed. Never let that read as a pass.
    if (!gate) {
      log('gate agent failed — cannot confirm; treating as not passed')
      testsPassing = false
    } else {
      const noTestsExist = !gate.tests_ran
      testsPassing = noTestsExist ? false : gate.tests_passed
      if (gate.tests_passed || noTestsExist) {
        gatePassed = true
        log(`gate PASSED on round ${round}${noTestsExist ? ' (no test suite exists for this step)' : ''}`)
        rounds[rounds.length - 1].advisory = advisory.map((f) => `${f.severity}: ${f.title} (${f.file})`)
        return {
          status: 'pass',
          step,
          rounds,
          testsPassing,
          testsExist: !noTestsExist,
          advisory: advisory.map((f) => ({ severity: f.severity, title: f.title, file: f.file, summary: f.summary })),
          note: noTestsExist
            ? 'No blocking findings survived verification, but NO TEST SUITE RAN. The plan requires tests for every code-producing step — say this explicitly to LJ rather than presenting it as a clean pass.'
            : 'No blocking findings survived adversarial verification. Advisory items are listed but were not auto-fixed.',
        }
      }
      log('no blocking review findings, but tests are failing — continuing the loop')
    }
  }

  // ---- Fix ----
  phase('Fix')
  const fixList = blocking.length ? blocking : []
  const fixed = await agent(
    `Apply fixes for the confirmed findings below. These survived an adversarial
refutation pass, so treat them as real.

${fixList.map((f, i) => `${i + 1}. [${f.severity}] ${f.file}${f.line ? `:${f.line}` : ''} — ${f.title}
   defect: ${f.summary}
   scenario: ${f.failure_scenario}
   suggested: ${f.suggested_fix || '(none given — use your judgement)'}`).join('\n\n') || '(no review findings — the failing test suite is the defect; fix that)'}

${testsPassing ? '' : 'The test suite is currently FAILING. Fixing it is part of this task.'}

Rules — these are not optional:
- Make the SMALLEST change that resolves each finding. No refactoring beyond it.
- Do not "improve" adjacent code, comments, or formatting.
- Do not add abstraction, configurability, or speculative error handling.
- Remove only orphans your own fix created.
- Re-run the tests when done and report the real result.
- If you believe a finding is wrong, SKIP it and say why. Do not implement
  something you disagree with just because it was listed.`,
    { label: `fix:round-${round}`, phase: 'Fix', schema: FIX_SCHEMA },
  )

  if (fixed) {
    log(`round ${round}: applied ${fixed.applied.length}, skipped ${fixed.skipped.length}`)
    rounds[rounds.length - 1].applied = fixed.applied
    rounds[rounds.length - 1].skipped = fixed.skipped
  }
}

// ---------------------------------------------------------------------------
// Exhausted the round budget without clearing the gate.
// ---------------------------------------------------------------------------

phase('Report')
const report = await agent(
  `The quality-gate loop ran ${maxRounds} rounds for step ${step} without clearing the gate.

Round history:
${JSON.stringify(rounds, null, 2)}

Do NOT change code. Produce an honest handover for LJ:
1. What is still outstanding and why it resisted ${maxRounds} rounds.
2. Whether the remaining items are genuine defects or disagreements about approach.
3. The single most useful next action.

Be blunt. An unresolved problem stated plainly is worth more than an optimistic summary.`,
  { label: 'report', phase: 'Report' },
)

return {
  status: gatePassed ? 'pass' : 'incomplete',
  step,
  rounds,
  testsPassing,
  report,
  note: `Gate not cleared within ${maxRounds} rounds. Do NOT present this step for VERIFY without telling LJ what is outstanding.`,
}

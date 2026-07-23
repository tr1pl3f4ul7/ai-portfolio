export const meta = {
  name: 'build-step',
  description: 'Coding orchestrator: explores approaches, writes tests first, fans implementation out to workers over disjoint files, integrates, then runs the quality gate',
  whenToUse: 'When implementing a numbered step from docs/PROJECT_PLAN.md that is more than a trivial edit. Not for typos or one-line changes.',
  phases: [
    { title: 'Survey', detail: 'read the plan step, the layer CLAUDE.md, and existing code' },
    { title: 'Design', detail: 'independent approach proposals' },
    { title: 'Adjudicate', detail: 'pick an approach and break it into disjoint work units' },
    { title: 'Contract', detail: 'write the failing tests first' },
    { title: 'Implement', detail: 'one worker per unit, over non-overlapping files' },
    { title: 'Integrate', detail: 'wire the units together and get the suite green' },
    { title: 'Gate', detail: 'hand off to the quality-gate workflow' },
  ],
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const cfg = args || {}
const step = cfg.step || null
const task = cfg.task || null
const testCommand = cfg.testCommand || null
const skipGate = cfg.skipGate === true
const testFirst = cfg.testFirst !== false // default ON — Principle 4

if (!step && !task) {
  return { status: 'error', reason: 'Pass either a plan step number ({step:"2.3"}) or a free-form task ({task:"..."}).' }
}

const subject = step ? `Step ${step} of docs/PROJECT_PLAN.md` : task

// More design proposals when the user has funded a bigger budget; two is enough
// to expose a genuine fork in approach, which is the point.
const designCount = budget.total && budget.total > 400000 ? 3 : 2

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const SURVEY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['deliverable', 'layer', 'test_command', 'constraints', 'existing_files'],
  properties: {
    deliverable: { type: 'string', description: 'One sentence: what this step must produce' },
    layer: { type: 'string', description: 'backend | web | edge | mobile | infra | docs | ci | mixed' },
    test_command: { type: 'string', description: 'Exact command to run this layer tests' },
    constraints: { type: 'array', items: { type: 'string' }, description: 'Binding rules from the plan and the layer CLAUDE.md' },
    existing_files: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' }, description: 'Genuine ambiguities needing a human decision' },
  },
}

const DESIGN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['approach', 'rationale', 'files', 'tradeoffs'],
  properties: {
    approach: { type: 'string', description: 'The approach in 3-5 sentences' },
    rationale: { type: 'string' },
    files: { type: 'array', items: { type: 'string' }, description: 'Files this approach creates or edits' },
    tradeoffs: { type: 'string', description: 'What this gives up. Required — every approach gives something up' },
    estimated_loc: { type: 'integer' },
  },
}

const BREAKDOWN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['chosen', 'rationale', 'units'],
  properties: {
    chosen: { type: 'string', description: 'The selected approach, synthesised' },
    rationale: { type: 'string', description: 'Why this one, and what was grafted from the others' },
    units: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title', 'files', 'description'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          files: { type: 'array', items: { type: 'string' }, description: 'Files this unit OWNS. Must not overlap any other unit' },
          description: { type: 'string', description: 'Precise enough to implement without further questions' },
          success_criteria: { type: 'string', description: 'How to tell this unit is done' },
        },
      },
    },
  },
}

const UNIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['unit_id', 'files_written', 'summary', 'blocked'],
  properties: {
    unit_id: { type: 'string' },
    files_written: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    blocked: { type: 'boolean' },
    blocker_reason: { type: 'string' },
    deviations: { type: 'string', description: 'Anything done differently from the brief, and why' },
  },
}

const RUN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['tests_ran', 'tests_passed', 'output'],
  properties: {
    tests_ran: { type: 'boolean' },
    tests_passed: { type: 'boolean' },
    output: { type: 'string', description: 'Real test output — never a paraphrase' },
    changes_made: { type: 'array', items: { type: 'string' } },
  },
}

// ---------------------------------------------------------------------------
// 1. Survey
// ---------------------------------------------------------------------------

log(`build-step | ${subject}`)

phase('Survey')
const survey = await agent(
  `You are surveying before any code is written. Do NOT write or edit code in this task.

Target: ${subject}

1. Read docs/PROJECT_PLAN.md${step ? ` and locate step ${step} exactly` : ''}. State precisely what
   it must deliver — no more.
2. Read the root CLAUDE.md and the CLAUDE.md of whichever directory this step touches. Extract the
   binding constraints (framework, file layout, layer-specific rules, test requirements).
3. List files that already exist and are relevant. Note what is deliberately absent.
4. Determine the exact test command for this layer.
5. List genuine open questions — real ambiguities a human must resolve, not things you can decide.
   Be strict here: if the plan or a CLAUDE.md already answers it, it is NOT an open question.

Remember the repo rule: never build ahead of the current step. If the step's scope looks smaller
than you expected, that is correct and intentional.`,
  { label: 'survey', phase: 'Survey', schema: SURVEY_SCHEMA },
)

if (!survey) {
  return { status: 'error', reason: 'survey failed; nothing was implemented' }
}

const cmd = testCommand || survey.test_command
log(`layer=${survey.layer} | tests: ${cmd}`)

if (survey.open_questions && survey.open_questions.length) {
  log(`⚠ ${survey.open_questions.length} open question(s) — surfacing rather than guessing`)
  return {
    status: 'needs-input',
    subject,
    deliverable: survey.deliverable,
    open_questions: survey.open_questions,
    note: 'Principle 1: do not pick silently between interpretations. Put these to LJ before implementing.',
  }
}

// ---------------------------------------------------------------------------
// 2. Design — independent proposals, then adjudicate
// ---------------------------------------------------------------------------

phase('Design')
const ANGLES = [
  'Bias hard toward the SIMPLEST thing that satisfies the deliverable. Assume any abstraction is unnecessary until proven otherwise.',
  'Bias toward the approach that is EASIEST TO TEST and hardest to get silently wrong, even if it costs a little more structure.',
  'Bias toward the approach that best fits the EXISTING conventions in this repo, minimising new patterns a reader must learn.',
]

const designs = (await parallel(
  ANGLES.slice(0, designCount).map((angle, i) => () =>
    agent(
      `Propose an implementation approach. Do NOT write code — this is design only.

Deliverable: ${survey.deliverable}
Layer: ${survey.layer}
Binding constraints:
${survey.constraints.map((c) => `- ${c}`).join('\n')}
Relevant existing files:
${survey.existing_files.join('\n') || '(none yet)'}

Your assigned bias for this proposal: ${angle}

Read the actual code and the layer CLAUDE.md first. Give a concrete approach: which files, what
each contains, how the pieces connect. State the tradeoffs honestly — an approach with no
downsides means you have not looked hard enough.

Hard limits from CLAUDE.md Principle 2: no speculative features, no abstraction over a single call
site, no configurability nobody asked for, no handling for impossible cases.`,
      { label: `design:${i + 1}`, phase: 'Design', schema: DESIGN_SCHEMA },
    ),
  ),
)).filter(Boolean)

if (!designs.length) {
  return { status: 'error', reason: 'all design agents failed; nothing was implemented' }
}

log(`${designs.length} approaches proposed`)

phase('Adjudicate')
const breakdown = await agent(
  `Choose an implementation approach and break it into work units. Do NOT write code.

Deliverable: ${survey.deliverable}
Constraints:
${survey.constraints.map((c) => `- ${c}`).join('\n')}

Proposals:
${designs.map((d, i) => `
--- Proposal ${i + 1} ---
approach:  ${d.approach}
rationale: ${d.rationale}
files:     ${d.files.join(', ')}
tradeoffs: ${d.tradeoffs}
est. LOC:  ${d.estimated_loc || 'n/a'}`).join('\n')}

Pick the strongest and graft in anything better from the others. Prefer the simplest proposal
unless another is clearly more correct — "more capable" is not a reason to prefer one here.

Then decompose into work units for parallel implementation. CRITICAL RULES:

1. Each unit OWNS an explicit list of files. **No file may appear in two units.** Two workers
   editing one file will corrupt each other's work.
2. Units must be independently implementable — no unit may depend on another's output.
3. If the work genuinely cannot be split that way, return ONE unit. A single unit is a correct
   and common answer for a small step. Do not invent parallelism that isn't there.
4. Each description must be precise enough to implement without asking follow-up questions.

Do not include test files in units if tests are being written separately — they are handled in
their own phase.`,
  { label: 'adjudicate', phase: 'Adjudicate', schema: BREAKDOWN_SCHEMA },
)

if (!breakdown || !breakdown.units || !breakdown.units.length) {
  return { status: 'error', reason: 'adjudication produced no work units' }
}

// --- Deterministic safety check: file ownership must be disjoint. -----------
// An LLM asked for non-overlapping sets will sometimes overlap anyway. Verify
// in code rather than trusting it, because the failure is silent corruption.
const owner = new Map()
const collisions = []
for (const u of breakdown.units) {
  for (const f of u.files || []) {
    const norm = f.replace(/\\/g, '/').replace(/^\.\//, '')
    if (owner.has(norm)) collisions.push(`${norm} claimed by both ${owner.get(norm)} and ${u.id}`)
    else owner.set(norm, u.id)
  }
}

let units = breakdown.units
let serialised = false
if (collisions.length) {
  log(`⚠ overlapping file ownership — collapsing to a single sequential unit`)
  collisions.forEach((c) => log(`   ${c}`))
  serialised = true
  units = [{
    id: 'merged',
    title: 'All work (merged after file-ownership collision)',
    files: Array.from(owner.keys()),
    description: breakdown.units.map((u) => `### ${u.title}\n${u.description}`).join('\n\n'),
    success_criteria: 'Every merged unit satisfied and the test suite passes.',
  }]
}

log(`${units.length} work unit(s)${serialised ? ' (serialised)' : ''}${units.length === 1 ? ' — no fan-out needed' : ''}`)

// ---------------------------------------------------------------------------
// 3. Contract — tests first
// ---------------------------------------------------------------------------

let contract = null
if (testFirst) {
  phase('Contract')
  contract = await agent(
    `Write the tests for this work BEFORE the implementation exists. They are expected to fail now —
that is the point (CLAUDE.md Principle 4).

Deliverable: ${survey.deliverable}
Chosen approach: ${breakdown.chosen}
Units:
${units.map((u) => `- ${u.title}: ${u.description}`).join('\n')}

Layer test conventions (${survey.layer}) — follow the layer CLAUDE.md exactly:
- backend: pytest; TestClient for endpoints; **Claude API always mocked**, never live-called.
- edge: vitest over the pure classification logic, independent of the Workers runtime.
- web: component/interaction tests; WebLLM inference itself is verified manually.
- mobile: widget tests for loading/result/error states; unit tests for the API client.
- infra: shellcheck, plus an idempotency check (run twice, no errors, no duplicate config).

Write tests that assert BEHAVIOUR, not implementation detail. A test that would still pass with
the feature deleted is worthless. Cover the failure paths, not just the happy path.

Then run: ${cmd}
Report the real output. Failures are the expected result at this stage — report them plainly.`,
    { label: 'contract:tests', phase: 'Contract', schema: RUN_SCHEMA },
  )
  if (contract) log(`contract tests written | ran=${contract.tests_ran} passed=${contract.tests_passed} (failing is expected here)`)
}

// ---------------------------------------------------------------------------
// 4. Implement — one worker per unit, over disjoint files
// ---------------------------------------------------------------------------

phase('Implement')
const results = (await parallel(
  units.map((u) => () =>
    agent(
      `Implement this work unit. Write real, working code.

UNIT: ${u.title}
${u.description}

Success criteria: ${u.success_criteria || 'the unit works and its tests pass'}

FILES YOU OWN — do not create or edit anything outside this list:
${(u.files || []).map((f) => `  ${f}`).join('\n')}

${units.length > 1 ? `Other workers are editing other files concurrently. Touching a file outside your list
will corrupt their work. If you believe you need one, STOP, set blocked=true, and explain.` : ''}

Context:
- Deliverable: ${survey.deliverable}
- Approach: ${breakdown.chosen}
- Constraints:
${survey.constraints.map((c) => `  - ${c}`).join('\n')}
${testFirst ? '- Tests already exist for this work. Make them pass. Do not weaken or delete a test to get green.' : ''}

Rules from CLAUDE.md — binding:
- Principle 2: minimum code that solves it. No speculative features, no abstraction over one call
  site, no unrequested configurability, no handling for impossible cases.
- Principle 3: touch only what you must. No drive-by refactors or reformatting.
- Read the CLAUDE.md of the directory you are writing into and follow its rules.
- Never hardcode a secret. Configuration comes from the environment.

If the brief is wrong or impossible, set blocked=true and say why rather than improvising
something that was not asked for.`,
      { label: `impl:${u.id}`, phase: 'Implement', schema: UNIT_SCHEMA },
    ),
  ),
)).filter(Boolean)

const blocked = results.filter((r) => r.blocked)
const built = results.filter((r) => !r.blocked)
log(`implemented ${built.length}/${units.length} unit(s)${blocked.length ? `, ${blocked.length} BLOCKED` : ''}`)

if (blocked.length) {
  blocked.forEach((b) => log(`   blocked: ${b.unit_id} — ${b.blocker_reason || 'no reason given'}`))
}

// ---------------------------------------------------------------------------
// 5. Integrate
// ---------------------------------------------------------------------------

phase('Integrate')
const integration = await agent(
  `Integrate the work units and get the test suite green.

Units implemented:
${built.map((r) => `- ${r.unit_id}: ${r.summary}\n  files: ${r.files_written.join(', ')}${r.deviations ? `\n  deviations: ${r.deviations}` : ''}`).join('\n')}
${blocked.length ? `\nBLOCKED (not implemented):\n${blocked.map((b) => `- ${b.unit_id}: ${b.blocker_reason}`).join('\n')}` : ''}

Do:
1. Review the combined result for seams — units were written independently and may not fit
   together cleanly. Mismatched signatures, missing wiring, duplicated helpers.
2. Remove orphans the implementation created (unused imports, dead helpers). Do NOT remove
   pre-existing code that was already there.
3. Run: ${cmd}
4. Fix genuine failures. Do NOT weaken, skip, or delete tests to get green — if a test is wrong,
   say so explicitly instead of quietly changing it.
5. Report the real output.

Keep changes minimal. You are joining pieces, not redesigning them.`,
  { label: 'integrate', phase: 'Integrate', schema: RUN_SCHEMA },
)

const green = integration ? integration.tests_ran && integration.tests_passed : false
log(`integration: tests_ran=${integration ? integration.tests_ran : 'n/a'} passed=${integration ? integration.tests_passed : 'n/a'}`)

// ---------------------------------------------------------------------------
// 6. Gate — hand off to the review orchestrator
// ---------------------------------------------------------------------------

let gate = null
if (!skipGate) {
  phase('Gate')
  try {
    gate = await workflow('quality-gate', {
      step: step || 'ad-hoc',
      scope: 'the working diff produced by build-step',
      testCommand: cmd,
      maxRounds: 2,
    })
  } catch (e) {
    log(`quality-gate could not run: ${e && e.message ? e.message : e}`)
    gate = { status: 'error', reason: String(e && e.message ? e.message : e) }
  }
}

return {
  status: blocked.length ? 'partial' : green ? 'built' : 'built-tests-failing',
  subject,
  deliverable: survey.deliverable,
  approach: breakdown.chosen,
  approachRationale: breakdown.rationale,
  units: units.map((u) => ({ id: u.id, title: u.title, files: u.files })),
  serialised,
  blocked: blocked.map((b) => ({ unit: b.unit_id, reason: b.blocker_reason })),
  testsPassing: green,
  testOutput: integration ? integration.output : null,
  gate,
  note: blocked.length
    ? 'Some units were blocked. Report exactly which, and why, before presenting for VERIFY.'
    : green
      ? 'Built with a passing suite. Still requires LJ\'s ✅ VERIFY — this is not a substitute.'
      : 'Implementation landed but the suite is NOT green. Say so plainly; do not present for VERIFY.',
}

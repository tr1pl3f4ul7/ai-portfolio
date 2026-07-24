# Design System

One visual contract, two consumers: the web one-pager and the Flutter app. The same shape as the
API contract with its three clients — and the same failure mode if it drifts, except design drift
is **silent**. Nothing errors; the two clients just quietly stop looking like one product.

So both platform files are **generated**, and neither is ever hand-edited.

```
design/tokens.json        <- edit this, and only this
        |
        +--> web/src/styles/tokens.css      CSS custom properties
        +--> mobile/lib/theme/tokens.dart   Flutter (emitted from Phase 6)
```

```bash
python design/generate.py           # write the outputs
python design/generate.py --check   # fail if they are stale (CI, Phase 7)
```

Changing a colour means editing `tokens.json`, regenerating, and committing both files together.
A generated file edited by hand is reverted the next time anyone runs the script.

---

## The direction: terminal-native

The architecture is the content, so the architecture is the hero. Not a page that *describes*
four inference layers — a page that shows them running, each annotated with where it happened and
what it cost. A visitor gets the differentiator in about four seconds without reading a paragraph
about it.

The register comes from **Claude Code** — a terminal — not the Claude desktop app. That distinction
is deliberate: see decision 39.

---

## Colour

The palette encodes something true instead of decorating. **Cool runs near the visitor, warm runs
on LJ's infrastructure.**

| Token | Layer | Why this pole |
|---|---|---|
| `--color-layer-browser` | WebLLM, on-device | Cool. Nothing leaves the visitor's machine. |
| `--color-layer-edge` | Cloudflare Workers AI | Cool. Near the visitor, not near LJ. |
| `--color-layer-server` | Oracle VM, Brisbane | Warm. LJ's own hardware. |
| `--color-layer-cloud` | Anthropic API | Warm. LJ's account, LJ's bill. |

Four layers stay distinguishable without becoming a rainbow, and the logic survives a second look.

**`--color-signal` is the only accent.** Spend boldness there and keep everything around it quiet.
`ok` / `warn` / `danger` are semantic state, not accents — never use them decoratively.

Two looks were rejected on purpose: **acid-green-on-black** (terminal costume, and the default
skin of every other engineer's portfolio) and **warm cream with a terracotta accent** (Anthropic's
own identity — see decision 39).

---

## Typography

Three roles, no webfont. A font CDN that fails silently is worse than a system face that always
loads, and the page already has a multi-hundred-megabyte model download to budget for.

| Role | Face | Treatment |
|---|---|---|
| Display | `--font-mono` | **lowercase**, `--tracking-display` (tight). The terminal signature. |
| Body | `--font-sans` | Running text only. Keep near 65 characters wide. |
| Data | `--font-mono` | **UPPERCASE**, `--tracking-label` (open), small. Labels, timings, metadata. |

Lowercase mono headings instead of the usual big-bold-sans hero — it is the texture of the tool LJ
actually works in, and it reads as considered rather than templated.

Use `font-variant-numeric: tabular-nums` anywhere digits line up: latencies, token counts, the
inference trace.

---

## Motion

One orchestrated moment beats scattered effects.

- **`--motion-base` (200ms) is a ceiling.** Nothing on this site eases longer.
- **`--motion-easing` is decelerating** — precise, never bouncy. No overshoot, no spring.
- The inference trace runs **once** on load, top to bottom: a request moving through four layers.
- Answers stream token by token. Retrieved sources disclose the way a tool call does.

Every animation sits behind `prefers-reduced-motion`. Non-negotiable — it is already a rule in
`web/CLAUDE.md`.

---

## Dark only

Deliberate, not an omission. The terminal register commits to one visual world; a light variant
would be a different design rather than a translation of this one. If that ever changes it is a new
decision entry, not a quiet addition of light tokens.

---

## Rules

- **Never hardcode a hex value, size, or duration** in `web/` or `mobile/`. If a value is missing,
  add it to `tokens.json` — that is the whole point of the file.
- `--radius-sharp` is 3px everywhere. Instrument panel, not a rounded card.
- Semantic colour is separate from the accent and does not count as one.
- Interactive things must look interactive, and keyboard focus must be visible — use
  `--color-signal` for focus rings.
- The four layer colours mean four specific places. Do not reuse them as a general palette.

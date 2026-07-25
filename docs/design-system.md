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

Two kinds, with different rules.

**Time-based** — anything triggered by an event: a hover, a focus ring, an answer arriving.

- **`--motion-base` (200ms) is a ceiling.** Nothing on this site eases longer.
- **`--motion-easing` is decelerating** — precise, never bouncy. No overshoot, no spring.

**Entrances** — an element arriving on screen, on scroll or on load. These use
`--motion-entrance` (760ms), not the interaction ceiling: travel across a screen needs time to
read as movement rather than as a flicker.

- **Distance is what makes motion visible.** `--travel-rise` is 3.5rem (56px) and
  `--travel-slide` 2.5rem (40px). An earlier version used 1.25rem and was, correctly, reported as
  "no animation at all" — it was running perfectly and simply too small to see.
- **Vary the axis.** Cards slide in from alternating sides, trace rows and labels come in from
  the left, heading words slide up from behind a mask. One repeated gesture down a long page
  reads as a template.
- **Stagger with `--motion-stagger` (70ms)** multiplied by an index `motion.ts` sets on siblings.
- Headings are split per word and masked; the words carry the movement, so the heading itself only
  fades — two transforms on one element fight.

**Driven by class toggles, not scroll timelines.** `motion.ts` toggles `is-revealed` from an
IntersectionObserver and CSS transitions the result. The first implementation used
`animation-timeline: view()` on whole `<section>` elements; a section taller than the viewport has
a degenerate `entry` range, so those animations finished before the section was ever on screen and
nothing appeared to move. Class toggles work at any element height — and, unlike compositor-driven
timelines, can be asserted on in tests.

**Continuous parallax** stays in CSS `animation-timeline`, where it belongs: it genuinely wants a
scroll timeline and runs off the main thread. Apply it only to elements that do *not* also have an
entrance transition on `transform`, or the animation and the transition will fight. Elements on
the same screen should move at *different* rates — that differential is the effect; moving
everything together is just scrolling.

**Reference a named view-timeline by its name alone** — `animation-timeline: --hero`, never
`view(--hero)`. `view()` takes an axis and insets, not a name, so the named form is invalid, gets
dropped, and `animation-timeline` silently falls back to the document timeline with a `0s`
duration. The keyframe's *end* state then applies permanently: the hero sat at `opacity: 0.15`,
translated up 80px, looking broken rather than unanimated. A dropped declaration is invisible
until you read the computed style, so read it — that is what caught this.

`web/src/styles/motion.css` holds all of it; `main.css` holds none.

**The hidden state must never outlive its reveal.** It lives behind `.js-motion`, a class
`motion.ts` adds *only* once an observer is guaranteed to run. No JavaScript, no
IntersectionObserver, or reduced motion — the page renders complete and static rather than blank.

**Never make an entrance depend on `requestAnimationFrame`.** The hero has nothing to scroll it
into view, so it reveals on load; doing that in a rAF callback left the headline permanently
invisible in a background tab and in any non-compositing embedder. Force a style flush
(`void document.body.offsetHeight`) and reveal synchronously instead.

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

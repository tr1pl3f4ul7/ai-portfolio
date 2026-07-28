"""Generate web token files from design/tokens.json.

    python design/generate.py            # write the output
    python design/generate.py --check    # verify it is current (CI)

`tokens.json` is the single source; `tokens.css` is generated from it and
never hand-edited, so a value only ever needs to be decided once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.json"
CSS_OUT = ROOT / "web" / "src" / "styles" / "tokens.css"

BANNER = "GENERATED FROM design/tokens.json — DO NOT EDIT. Run: python design/generate.py"

# Token groups rendered as CSS custom properties, in order, with their prefix.
GROUPS = [
    ("color", "color"),
    ("font", "font"),
    ("size", "size"),
    ("space", "space"),
    ("motion", "motion"),
    ("travel", "travel"),
    ("radius", "radius"),
    ("tracking", "tracking"),
]

# Keys in tokens.json that are documentation, not tokens.
NON_TOKEN_KEYS = {"$schema-note"}


def kebab(name: str) -> str:
    """layerBrowser -> layer-browser;  s-1 -> s-1 (already kebab)."""
    out = []
    for char in name:
        if char.isupper():
            out.append("-")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out)


def load() -> dict:
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))

    # A group added to tokens.json but not to GROUPS would be silently dropped
    # from every output — the token would simply not exist, and the first sign
    # would be a broken layout. Fail loudly instead.
    known = {name for name, _ in GROUPS} | NON_TOKEN_KEYS
    unknown = sorted(set(tokens) - known)
    if unknown:
        raise SystemExit(
            f"tokens.json has group(s) the generator does not emit: {', '.join(unknown)}\n"
            f"Add them to GROUPS in design/generate.py, or remove them from the JSON."
        )
    return tokens


def render_css(tokens: dict) -> str:
    lines = [
        f"/* {BANNER} */",
        "",
        "/* Dark only, deliberately. The terminal register commits to one visual",
        "   world; a light variant would be a different design, not a translation. */",
        ":root {",
    ]
    for group, prefix in GROUPS:
        entries = tokens.get(group, {})
        if not entries:
            continue
        lines.append(f"  /* --- {group} --- */")
        for name, spec in entries.items():
            lines.append(f"  --{prefix}-{kebab(name)}: {spec['value']};")
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines += ["}", ""]
    return "\n".join(lines)


def targets(tokens: dict) -> list[tuple[Path, str]]:
    return [(CSS_OUT, render_css(tokens))]


def main() -> int:
    check = "--check" in sys.argv
    tokens = load()
    stale = []

    for path, content in targets(tokens):
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            print(f"  ok      {path.relative_to(ROOT)}")
            continue
        if check:
            stale.append(path.relative_to(ROOT))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  written {path.relative_to(ROOT)}")

    if stale:
        print("\nOut of date with design/tokens.json:", file=sys.stderr)
        for path in stale:
            print(f"  {path}", file=sys.stderr)
        print("\nRun: python design/generate.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

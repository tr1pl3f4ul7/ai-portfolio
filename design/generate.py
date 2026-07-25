"""Generate platform token files from design/tokens.json.

    python design/generate.py            # write the outputs
    python design/generate.py --check    # verify they are current (CI)

The web page and the Flutter app are two consumers of one visual contract —
the same shape as the API contract with its three clients. Hand-maintaining
both would drift, and design drift is silent: nothing fails, the two clients
just stop looking like one product. So both outputs are generated and neither
is ever hand-edited.

Dart is emitted only once mobile/lib/ exists (Phase 6). Until then this writes
CSS alone, so nothing is pre-created for a phase we have not reached.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.json"
CSS_OUT = ROOT / "web" / "src" / "styles" / "tokens.css"
DART_OUT = ROOT / "mobile" / "lib" / "theme" / "tokens.dart"

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


def _dart_color(hex_value: str) -> str:
    return f"Color(0xFF{hex_value.lstrip('#').upper()})"


def render_dart(tokens: dict) -> str:
    """Flutter side of the same contract. Colours, sizes, spacing and motion.

    Font stacks are intentionally omitted — Flutter resolves families by name,
    not by a CSS fallback list, so the mobile app picks its own equivalents in
    Phase 6 rather than inheriting a stack that means nothing to it.
    """
    lines = [
        f"// {BANNER}",
        "",
        "import 'package:flutter/material.dart';",
        "",
        "/// Design tokens shared with the web client. See docs/design-system.md.",
        "abstract final class Tokens {",
    ]

    lines.append("  // --- color ---")
    for name, spec in tokens["color"].items():
        lines.append(f"  static const {name} = {_dart_color(spec['value'])};")

    lines.append("")
    lines.append("  // --- size (logical pixels; 1rem = 16) ---")
    for name, spec in tokens["size"].items():
        rem = float(spec["value"].replace("rem", ""))
        ident = "s" + name.lstrip("s").replace("-", "Neg")
        lines.append(f"  static const {ident} = {rem * 16:.1f};")

    lines.append("")
    lines.append("  // --- space (logical pixels) ---")
    for name, spec in tokens["space"].items():
        rem = float(spec["value"].replace("rem", ""))
        lines.append(f"  static const space{name} = {rem * 16:.1f};")

    lines.append("")
    lines.append("  // --- motion ---")
    for name, spec in tokens["motion"].items():
        if spec["value"].endswith("ms"):
            ms = int(spec["value"].replace("ms", ""))
            lines.append(f"  static const {name} = Duration(milliseconds: {ms});")

    radius = float(tokens["radius"]["sharp"]["value"].replace("px", ""))
    lines += ["", "  // --- radius ---", f"  static const sharp = {radius:.1f};", "}", ""]
    return "\n".join(lines)


def targets(tokens: dict) -> list[tuple[Path, str]]:
    out = [(CSS_OUT, render_css(tokens))]
    # Only once the mobile app exists. Phase 6 owns that directory.
    if DART_OUT.parent.parent.exists():
        out.append((DART_OUT, render_dart(tokens)))
    return out


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

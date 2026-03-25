#!/usr/bin/env python3
"""
Bundle all TypeScript and related stylesheet sources for the Oleo landing page into
one Markdown document and copy it to the system clipboard (macOS: pbcopy; Linux:
xclip or wl-copy).

Includes:
  - src/routes/LandingPage.tsx
  - every *.ts / *.tsx under src/routes/landing/
  - transitive closure of relative imports (./ and ../) from those files into the UI tree
  - *.css / *.scss / *.sass / *.less reached via TS/TSX imports or @import in those sheets

Stdlib only — no pip dependencies.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Match `from "..."` / `from '...'` where the path is relative.
_FROM_REL = re.compile(r"""from\s+["'](\.[^"']+)["']""")
# Side-effect: `import "./x"` (including `./file.css`)
_IMPORT_REL = re.compile(r"""^\s*import\s+["'](\.[^"']+)["']""", re.MULTILINE)
# `@import "./a.css"` / `@import url("./a.css")` (relative paths only)
_CSS_IMPORT_REL = re.compile(
    r"""@import\s+(?:url\s*\(\s*)?["'](\.[^"']+)["']""",
    re.MULTILINE,
)

_STYLESHEET_SUFFIXES = (".css", ".scss", ".sass", ".less")


def _default_ui_root() -> Path:
    """notion_pipeliner_ui next to the notion_place_inserter repo root."""
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    return repo_root.parent / "notion_pipeliner_ui"


def _resolve_import(from_file: Path, spec: str) -> Path | None:
    """Resolve a relative import to an existing .ts / .tsx or stylesheet file."""
    lower = spec.lower()
    base = (from_file.parent / spec).resolve()
    if lower.endswith(_STYLESHEET_SUFFIXES):
        return base if base.is_file() else None

    candidates: list[Path] = [base]
    if base.suffix.lower() not in (".ts", ".tsx"):
        candidates.extend(
            [
                base.with_suffix(".ts"),
                base.with_suffix(".tsx"),
                base / "index.ts",
                base / "index.tsx",
            ]
        )
    for c in candidates:
        if c.is_file():
            return c
    return None


def _extract_relative_specs(source: str) -> list[str]:
    specs: list[str] = []
    specs.extend(_FROM_REL.findall(source))
    for m in _IMPORT_REL.finditer(source):
        specs.append(m.group(1))
    return specs


def _extract_css_relative_imports(source: str) -> list[str]:
    return _CSS_IMPORT_REL.findall(source)


def _collect_landing_sources(ui_root: Path) -> list[Path]:
    landing_page = ui_root / "src" / "routes" / "LandingPage.tsx"
    if not landing_page.is_file():
        raise FileNotFoundError(f"Missing entry file: {landing_page}")

    landing_dir = ui_root / "src" / "routes" / "landing"
    seeds: set[Path] = {landing_page}
    if landing_dir.is_dir():
        for p in landing_dir.rglob("*"):
            if p.suffix in (".ts", ".tsx") and p.is_file():
                seeds.add(p.resolve())

    seen: set[Path] = set()
    stack = list(seeds)

    while stack:
        path = stack.pop()
        rp = path.resolve()
        if rp in seen:
            continue
        if not str(rp).startswith(str(ui_root.resolve())):
            continue
        suf = rp.suffix.lower()
        if suf not in (".ts", ".tsx") and suf not in _STYLESHEET_SUFFIXES:
            continue
        seen.add(rp)

        try:
            text = rp.read_text(encoding="utf-8")
        except OSError:
            continue

        if suf in (".ts", ".tsx"):
            rel_specs = _extract_relative_specs(text)
        else:
            rel_specs = _extract_css_relative_imports(text)

        for spec in rel_specs:
            resolved = _resolve_import(rp, spec)
            if resolved is None:
                continue
            try:
                resolved.relative_to(ui_root.resolve())
            except ValueError:
                continue
            if not resolved.is_file():
                continue
            rsuf = resolved.suffix.lower()
            if rsuf in (".ts", ".tsx") or rsuf in _STYLESHEET_SUFFIXES:
                stack.append(resolved)

    return list(seen)


def _sort_bundle_paths(ui_root: Path, files: list[Path]) -> list[Path]:
    root = ui_root.resolve()

    def key(p: Path) -> tuple[int, str]:
        rel = p.resolve().relative_to(root).as_posix()
        if p.suffix.lower() in _STYLESHEET_SUFFIXES:
            return (4, rel)
        if rel == "src/routes/LandingPage.tsx":
            return (0, rel)
        if rel.startswith("src/routes/landing/"):
            return (1, rel)
        return (2, rel)

    return sorted(files, key=key)


def _fence_lang(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".tsx":
        return "tsx"
    if suf == ".ts":
        return "typescript"
    if suf == ".scss":
        return "scss"
    if suf == ".sass":
        return "sass"
    if suf == ".less":
        return "less"
    if suf == ".css":
        return "css"
    return "text"


def _build_markdown(ui_root: Path, files: list[Path]) -> str:
    lines: list[str] = [
        "# Landing page — bundled TypeScript and stylesheet sources",
        "",
        f"_Generated from `{ui_root}`._",
        "",
        f"_Files: {len(files)}_",
        "",
    ]
    ui_resolved = ui_root.resolve()
    for f in files:
        try:
            rel = f.resolve().relative_to(ui_resolved)
        except ValueError:
            rel = f
        rel_posix = rel.as_posix()
        lines.append(f"## `{rel_posix}`")
        lines.append("")
        lines.append(f"```{_fence_lang(f)}")
        lines.append(f.read_text(encoding="utf-8").rstrip("\n"))
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _copy_clipboard(text: str) -> None:
    data = text.encode("utf-8")
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=data, check=True)
        return
    if sys.platform.startswith("linux"):
        for cmd in (["xclip", "-selection", "clipboard"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=data, check=True)
                return
            except FileNotFoundError:
                continue
        raise RuntimeError("Install xclip or wl-copy, or use --stdout")
    raise RuntimeError(f"Clipboard not supported on {sys.platform!r}; use --stdout")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bundle landing page TS/TSX and related stylesheets into Markdown "
            "and copy to clipboard."
        ),
    )
    parser.add_argument(
        "--ui-root",
        type=Path,
        default=None,
        help=f"Path to notion_pipeliner_ui (default: {_default_ui_root()})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print Markdown to stdout instead of copying to clipboard",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Also write the Markdown to this file",
    )
    args = parser.parse_args()
    ui_root = (args.ui_root or _default_ui_root()).resolve()
    if not ui_root.is_dir():
        print(f"error: UI root is not a directory: {ui_root}", file=sys.stderr)
        return 1

    try:
        files = _sort_bundle_paths(ui_root, _collect_landing_sources(ui_root))
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    md = _build_markdown(ui_root, files)

    if args.output is not None:
        args.output.write_text(md, encoding="utf-8")

    if args.stdout:
        sys.stdout.write(md)
    else:
        try:
            _copy_clipboard(md)
        except (RuntimeError, subprocess.CalledProcessError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        dest = "clipboard"
        if args.output is not None:
            dest += f" and {args.output}"
        print(f"Wrote {len(files)} files ({len(md)} chars) to {dest}.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

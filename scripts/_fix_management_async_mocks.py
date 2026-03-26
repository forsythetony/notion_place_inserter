"""One-off: convert mock.method.return_value = X to mock.method = AsyncMock(return_value=X) in test_management_routes.py."""
from __future__ import annotations

import re
from pathlib import Path


def _balance(s: str) -> int:
    """Net depth of ()[]{} in string."""
    d = 0
    for ch in s:
        if ch in "([{":
            d += 1
        elif ch in ")]}":
            d -= 1
    return d


def convert(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    pat = re.compile(r"^(\s*)([\w.]+)\.return_value = (.*)$")
    while i < len(lines):
        line = lines[i]
        raw = line.rstrip("\n")
        m = pat.match(raw)
        if m and "mock_" in m.group(2) and m.group(2).startswith("mock"):
            indent, target, first = m.group(1), m.group(2), m.group(3)
            buf = first
            depth = _balance(buf)
            j = i + 1
            while depth > 0 and j < len(lines):
                nxt = lines[j].rstrip("\n")
                buf += "\n" + nxt
                depth += _balance(nxt)
                j += 1
            expr = buf.strip()
            out.append(f"{indent}{target} = AsyncMock(return_value={expr})\n")
            i = j
            continue
        out.append(line)
        i += 1
    return "".join(out)


def main() -> None:
    p = Path("tests/test_management_routes.py")
    orig = p.read_text()
    new = convert(orig)
    p.write_text(new)
    print("wrote", p)


if __name__ == "__main__":
    main()

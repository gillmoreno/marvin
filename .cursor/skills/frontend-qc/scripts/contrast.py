#!/usr/bin/env python3
"""WCAG contrast for two CSS colors. Exit 0 when both AA bars pass, 1 otherwise.

Usage: contrast.py FOREGROUND BACKGROUND
Colors: #rgb, #rrggbb, #rrggbbaa, rgb(), rgba().
"""

from __future__ import annotations

import re
import sys


def parse(raw: str) -> tuple[float, float, float, float]:
    s = raw.strip().lower()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        if len(h) != 8 or any(c not in "0123456789abcdef" for c in h):
            raise ValueError(raw)
        r, g, b, a = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4, 6))
        return r, g, b, a
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)", s)
    if not m:
        raise ValueError(raw)
    r, g, b = (float(m.group(i)) / 255 for i in (1, 2, 3))
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return r, g, b, a


def composite(fg: tuple[float, float, float, float], bg: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Flatten fg over an opaque bg. Alpha on bg is ignored (pass the painted canvas)."""
    r, g, b, a = fg
    br, bgc, bb, _ = bg
    return tuple(a * c + (1 - a) * b for c, b in ((r, br), (g, bgc), (b, bb)))  # type: ignore[return-value]


def channel(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    a, b = luminance(fg), luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: contrast.py FOREGROUND BACKGROUND", file=sys.stderr)
        return 2
    try:
        fg = composite(parse(sys.argv[1]), parse(sys.argv[2]))
        bg = composite((parse(sys.argv[2])[0], parse(sys.argv[2])[1], parse(sys.argv[2])[2], 1), (1, 1, 1, 1))
    except ValueError as err:
        print(f"bad color: {err}", file=sys.stderr)
        return 2
    value = ratio(fg, bg)
    text = value >= 4.5
    large = value >= 3
    print(f"{value:.2f}:1  text {'pass' if text else 'FAIL'} (4.5)  large/ui {'pass' if large else 'FAIL'} (3)")
    return 0 if text else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fetch Google Static Maps (styled / clean) from 基準_coords_Grandole.json.

Saves:
  - 基準_下地_Grandole_クリーン.png  (POI off, no markers)
  - 基準_骨格図_Grandole_クリーン.png (POI off, numbered markers)

Uses GOOGLE_MAPS_API_KEY from .env.jarvis_private (never prints the key).
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.jarvis_private"
OUT_DIRS = [
    ROOT
    / "215_kamiooya"
    / "C1_cursor"
    / "1c_神・大家さん倶楽部_AI推進"
    / "AI×周辺MAP"
    / "試走出力",
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/試走出力",
]

# Static Maps style: hide POI / chome / road labels, keep road geometry
STYLE_PARAMS = [
    "feature:poi|visibility:off",
    "feature:poi.business|visibility:off",
    "feature:administrative|element:labels|visibility:off",
    "feature:administrative.neighborhood|element:labels|visibility:off",
    "feature:administrative.land_parcel|element:labels|visibility:off",
    "feature:administrative.locality|element:labels|visibility:off",
    "feature:landscape|element:labels|visibility:off",
    "feature:water|element:labels|visibility:off",
    "feature:road|element:labels|visibility:off",
    "feature:transit|element:labels|visibility:off",
    "feature:transit|element:labels.icon|visibility:off",
    "feature:transit.station|element:labels|visibility:off",
]


def load_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_MAPS_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def load_pins(coords_path: Path) -> list[dict]:
    data = json.loads(coords_path.read_text(encoding="utf-8"))
    pins = data.get("pins") or []
    return [p for p in pins if p.get("ok") and p.get("lat") is not None]


def build_url(pins: list[dict], *, with_markers: bool, size: str = "900x700") -> str:
    key = load_key()
    if not key:
        raise SystemExit("GOOGLE_MAPS_API_KEY not set")
    lats = [p["lat"] for p in pins]
    lngs = [p["lng"] for p in pins]
    # visible box
    pad = 0.002
    visible = f"{min(lats) - pad},{min(lngs) - pad}|{max(lats) + pad},{max(lngs) + pad}"
    params: list[tuple[str, str]] = [
        ("size", size),
        ("scale", "2"),
        ("maptype", "roadmap"),
        ("language", "ja"),
        ("visible", visible),
        ("key", key),
    ]
    for s in STYLE_PARAMS:
        params.append(("style", s))
    if with_markers:
        for p in pins:
            color = "red" if p.get("id") == "P0" or p.get("isProperty") else "blue"
            label = (p.get("id") or "?")[-1]  # Static Maps label is 1 char A-Z/0-9
            # Use full id in label when single digit: P0 -> 0, P1 -> 1 ... P8 -> 8
            lab = p.get("id", "X").replace("P", "")[:1] or "X"
            params.append(
                (
                    "markers",
                    f"color:{color}|label:{lab}|{p['lat']},{p['lng']}",
                )
            )
    return "https://maps.googleapis.com/maps/api/staticmap?" + urllib.parse.urlencode(params)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisShuhenStatic/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
    if b"PNG" not in data[:16] and "image" not in ctype:
        # likely JSON error
        raise RuntimeError(f"Static Maps failed: {data[:300]!r}")
    return data


def main() -> int:
    coords = None
    for d in OUT_DIRS:
        cand = d / "基準_coords_Grandole.json"
        if cand.exists():
            coords = cand
            break
    if not coords:
        print("coords JSON not found")
        return 1
    pins = load_pins(coords)
    if len(pins) < 2:
        print("not enough pins")
        return 1
    print(f"pins={len(pins)} from {coords}")

    outs = [
        ("基準_下地_Grandole_クリーン.png", False),
        ("基準_骨格図_Grandole_クリーン.png", True),
    ]
    for name, with_markers in outs:
        url = build_url(pins, with_markers=with_markers)
        # strip key from any log
        print(f"fetching {name} markers={with_markers}")
        blob = fetch(url)
        for d in OUT_DIRS:
            d.mkdir(parents=True, exist_ok=True)
            path = d / name
            path.write_bytes(blob)
            print(f"wrote {path} ({len(blob)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Recompose numbered pins onto a clean base map using 基準_coords_Grandole.json.

Also builds a light 'tone' wash (desaturate + paper tint) as Phase C stand-in,
then Canva-like edge decoration (Access + bubbles) for PDF-ready PNG.

Never prints API keys.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    ROOT
    / "215_kamiooya"
    / "C1_cursor"
    / "1c_神・大家さん倶楽部_AI推進"
    / "AI×周辺MAP"
    / "試走出力"
)
OD = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP/試走出力"
)

ACCESS = [
    "地下鉄名城線「志賀本通駅」 約7分",
    "名鉄瀬戸線「尼ケ坂駅」 約8分",
    "ナフコトミダ杉栄店 約3分",
    "ドラッグスギヤマ杉栄店 約3分",
    "名古屋市北区役所 約18分",
    "ゲオ辻本通店 約14分",
]
BUBBLES = [
    ("P1", "志賀本通駅", "栄まで地下鉄で直通。通勤に使いやすい駅です"),
    ("P2", "尼ケ坂／SAKUMACHI", "高架下におしゃれな店が並ぶ休日の散策スポットです"),
    ("P3", "ナフコトミダ杉栄店", "徒歩3分で大抵の買い物が済みます"),
    ("P4", "スギヤマ杉栄店", "日用品やコスメがすぐ揃います"),
    ("P5", "つばめパン＆Milk", "ふわもち食パンのモーニングが人気です"),
    ("P6", "Cafe de Lyon Palette", "旬のフルーツを使ったパフェが楽しめます"),
    ("P7", "つけそば 神宮寺", "仕事帰りに寄れる、評判のつけそば店です"),
    ("P8", "コノズコーヒー", "駅前でモーニングやランチが取れます"),
]


def load_pins() -> list[dict]:
    for d in (OUT, OD):
        p = d / "基準_coords_Grandole.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return [x for x in data.get("pins", []) if x.get("ok") and x.get("lat") is not None]
    raise FileNotFoundError("coords not found")


def latlng_to_xy(lat: float, lng: float, pins: list[dict], w: int, h: int, pad: float = 0.002):
    lats = [p["lat"] for p in pins]
    lngs = [p["lng"] for p in pins]
    min_lat, max_lat = min(lats) - pad, max(lats) + pad
    min_lng, max_lng = min(lngs) - pad, max(lngs) + pad
    x = (lng - min_lng) / (max_lng - min_lng) * (w - 40) + 20
    y = (max_lat - lat) / (max_lat - min_lat) * (h - 40) + 20
    return x, y


def draw_pin(draw: ImageDraw.ImageDraw, x: float, y: float, label: str, is_property: bool):
    color = (192, 57, 43) if is_property else (41, 128, 185)
    r = 14
    draw.ellipse((x - r, y - r - 6, x + r, y + r - 6), fill=color, outline=(255, 255, 255), width=2)
    # tip
    draw.polygon([(x - 7, y + 4), (x + 7, y + 4), (x, y + 16)], fill=color)
    draw.text((x - 6, y - 12), label.replace("P", ""), fill=(255, 255, 255))


def font(size: int):
    for path in (
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def write_both(img: Image.Image, name: str):
    for d in (OUT, OD):
        d.mkdir(parents=True, exist_ok=True)
        path = d / name
        img.save(path, "PNG")
        print(f"wrote {path} ({path.stat().st_size})")


def tone_wash(base: Image.Image) -> Image.Image:
    """C0: beige paper + low saturation (illustration-lite, roads preserved)."""
    from PIL import ImageFilter

    img = base.convert("RGB")
    # Drop Google-map saturation; keep structure
    img = ImageEnhance.Color(img).enhance(0.32)
    img = ImageEnhance.Contrast(img).enhance(0.86)
    img = ImageEnhance.Brightness(img).enhance(1.10)
    # Sample-like warm beige / cream paper
    paper = Image.new("RGB", img.size, (232, 218, 192))
    img = Image.blend(img, paper, 0.34)
    # Soften slightly for flyer/illustration feel (not a redraw)
    soft = img.filter(ImageFilter.SMOOTH_MORE)
    return Image.blend(img, soft, 0.40)


def recompose(base: Image.Image, pins: list[dict]) -> Image.Image:
    img = base.convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for p in pins:
        x, y = latlng_to_xy(p["lat"], p["lng"], pins, w, h)
        draw_pin(draw, x, y, p.get("id", "?"), bool(p.get("isProperty") or p.get("id") == "P0"))
    return img.convert("RGB")


def decorate(map_img: Image.Image) -> Image.Image:
    """A4-ish landscape with Access strip + edge bubbles."""
    W, H = 1754, 1240
    canvas = Image.new("RGB", (W, H), (250, 248, 242))
    draw = ImageDraw.Draw(canvas)
    f_title = font(40)
    f_body = font(20)
    f_sm = font(17)

    draw.rectangle([0, 0, 320, H], fill=(45, 62, 80))
    draw.text((24, 36), "Access", fill=(255, 255, 255), font=f_title)
    y = 110
    for a in ACCESS:
        draw.text((24, y), "• " + a, fill=(230, 235, 240), font=f_sm)
        y += 44

    draw.text((360, 28), "Grandole志賀本通 周辺MAP", fill=(40, 40, 40), font=f_title)
    draw.text(
        (360, 82),
        "名城線と瀬戸線に挟まれた生活至便な立地。平日は栄へスマート通勤、休日はSAKUMACHI商店街でカフェ巡り。",
        fill=(80, 80, 80),
        font=f_sm,
    )

    map_box = (340, 120, W - 40, H - 150)
    mw, mh = map_box[2] - map_box[0], map_box[3] - map_box[1]
    fitted = map_img.copy()
    fitted.thumbnail((mw, mh), Image.Resampling.LANCZOS)
    px = map_box[0] + (mw - fitted.width) // 2
    py = map_box[1] + (mh - fitted.height) // 2
    canvas.paste(fitted, (px, py))

    # Edge bubbles (right / bottom) — not over map center
    slots = [
        (W - 300, 140),
        (W - 300, 220),
        (W - 300, 300),
        (W - 300, 380),
        (360, H - 120),
        (700, H - 120),
        (1040, H - 120),
        (W - 300, 460),
    ]
    for (bx, by), (pid, title, text) in zip(slots, BUBBLES):
        draw.rounded_rectangle(
            [bx, by, bx + 260, by + 64],
            radius=12,
            fill=(255, 255, 255),
            outline=(41, 128, 185),
            width=2,
        )
        draw.text((bx + 12, by + 8), f"{pid} {title}", fill=(40, 40, 40), font=f_sm)
        draw.text((bx + 12, by + 34), text[:28], fill=(90, 90, 90), font=f_sm)

    draw.text(
        (360, H - 36),
        "番号ピン付きクリーン下地＋縁スロット下書き。Canvaで清書可。ピン位置は骨格座標を維持。",
        fill=(120, 120, 120),
        font=f_sm,
    )
    return canvas


def main() -> int:
    pins = load_pins()
    clean = OUT / "基準_下地_Grandole_クリーン.png"
    if not clean.exists():
        clean = OD / "基準_下地_Grandole_クリーン.png"
    if not clean.exists():
        print("clean base missing — run jarvis_shuhen_static_clean.py first")
        return 1

    base = Image.open(clean).convert("RGB")
    toned = tone_wash(base)
    write_both(toned, "基準_下地_Grandole_PhaseC.png")

    with_pins = recompose(toned, pins)
    write_both(with_pins, "基準_骨格図_Grandole_PhaseC.png")

    # Also recompose on untoned clean for comparison
    write_both(recompose(base, pins), "基準_骨格図_Grandole_クリーン再合成.png")

    decorated = decorate(with_pins)
    write_both(decorated, "Grandole_番号ピン付き_20260724.png")

    # PDF via PIL
    for d in (OUT, OD):
        pdf = d / "Grandole_番号ピン付き_20260724.pdf"
        decorated.convert("RGB").save(pdf, "PDF", resolution=150.0)
        print(f"wrote {pdf}")

    # Phase C note file
    note = """# Phase C 色味寄せ（実行メモ）

- 日付: 2026-07-24
- 工程: 範囲確定 → ピンなしクリーン下地 → **C0**（ベージュ紙面）→ coords 再合成 → Canva
- 入力: `基準_下地_Grandole_クリーン.png`
- C0: `jarvis_shuhen_recompose_decor.py`（彩度下げ＋ベージュ紙色＋軽いスムース）
  → `基準_下地_Grandole_PhaseC.png` → `基準_骨格図_Grandole_PhaseC.png`
- C1（任意）: `10c` 強化プロンプトで Gemini／ChatGPT にピンなし下地＋見本PDF。
  合否 OK なら PhaseC 下地を差し替え、本スクリプトを再実行。
- 合否: 道路が追える／北＝志賀本通・南＝尼ケ坂／焼き込みピンなし
"""
    for d in (OUT, OD):
        (d / "PhaseC_色味寄せメモ.md").write_text(note, encoding="utf-8")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

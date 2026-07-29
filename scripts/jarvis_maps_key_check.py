#!/usr/bin/env python3
"""Check GOOGLE_MAPS_API_KEY from .env.jarvis_private without printing the key."""
from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.jarvis_private"

def load_key() -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_MAPS_API_KEY=") and not line.strip().startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def main() -> int:
    key = load_key()
    if not key:
        print("📎 Google Maps API Key: 未設定（.env.jarvis_private の GOOGLE_MAPS_API_KEY）")
        return 1
    print(f"📎 Google Maps API Key: 設定あり（長さ {len(key)} / 先頭 {key[:4]}…）")
    q = urllib.parse.urlencode({"address": "名古屋市北区長田町", "key": key, "language": "ja"})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{q}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"Geocoding 呼び出し失敗: {e}")
        return 2
    status = data.get("status")
    print(f"Geocoding status: {status}")
    if status == "OK":
        loc = data["results"][0]["geometry"]["location"]
        print(f"OK — サンプル座標 lat={loc['lat']:.5f} lng={loc['lng']:.5f}")
        return 0
    print(f"エラー詳細: {data.get('error_message', '(なし)')}")
    if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
        print("→ Console で Geocoding API 有効化・キー制限・課金アカウントを確認")
    return 3

if __name__ == "__main__":
    sys.exit(main())

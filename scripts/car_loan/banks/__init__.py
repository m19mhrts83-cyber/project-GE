"""銀行アダプタ。"""
from __future__ import annotations

from . import mufg_jaccs, resona

ADAPTERS = {
    "mufg_jaccs": mufg_jaccs,
    "mufg": mufg_jaccs,
    "resona": resona,
    "resona_mycar": resona,
}

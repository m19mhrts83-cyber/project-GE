#!/Users/matsunomasaharu2/selenium_env/venv/bin/python
"""確定申告PDFから給与の支払金額（前年度税込年収の根拠）を抽出する。

正本は .env.jarvis_private の TAX_RETURN_* のみ。
ANNUAL_INCOME / ANNUAL_INCOME_MANYEN は jarvis_export_annual_income() で都度算出する。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env.jarvis_private"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"')
    return env


def latest_year_dir(root: Path) -> Path | None:
    """*年度 フォルダのうち名前で最新（例: 2026年度 > 2025年度）を返す。"""
    dirs = [p for p in root.iterdir() if p.is_dir() and p.name.endswith("年度")]
    if not dirs:
        return None

    def sort_key(p: Path) -> tuple[int, str]:
        m = re.match(r"^(\d{4})年度$", p.name)
        return (int(m.group(1)) if m else 0, p.name)

    dirs.sort(key=sort_key, reverse=True)
    for d in dirs:
        if list(d.glob("*確定申告書*.pdf")):
            return d
    return dirs[0]


def resolve_pdf(env: dict[str, str]) -> Path:
    root = env.get("TAX_RETURN_ROOT", "").strip()
    year_dir = env.get("TAX_RETURN_YEAR_DIR", "").strip()
    pdf_name = env.get("TAX_RETURN_PDF", "").strip()
    use_latest = env.get("TAX_RETURN_USE_LATEST_YEAR_DIR", "1").strip() not in (
        "0",
        "false",
        "False",
    )
    if not root:
        raise FileNotFoundError("TAX_RETURN_ROOT が .env.jarvis_private に未設定です")
    base = Path(root).expanduser()
    if year_dir:
        base = base / year_dir
    elif use_latest:
        picked = latest_year_dir(base)
        if picked is None:
            raise FileNotFoundError(f"年度フォルダが見つかりません: {base}")
        base = picked
    if pdf_name:
        candidate = base / pdf_name
        if candidate.is_file():
            return candidate
    pdfs = sorted(base.glob("*確定申告書*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdfs:
        raise FileNotFoundError(f"確定申告PDFが見つかりません: {base}")
    return pdfs[0]


def extract_salary_gross_yen(pdf_path: Path) -> int | None:
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError("pypdf が必要です（selenium_env venv 等）") from exc

    text = "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(str(pdf_path)).pages)
    m = re.search(
        r"給与\s*\n[^\n]+\n[^\n]+\n(?:号\s*\n)?(\d{1,3}(?:,\d{3})+)",
        text,
    )
    if m:
        return int(m.group(1).replace(",", ""))
    idx = text.find("給与")
    if idx >= 0:
        window = text[idx : idx + 400]
        amounts = [int(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})+", window)]
        if amounts:
            return max(amounts)
    return None


def manyen_from_yen(yen: int) -> int:
    return yen // 10000


def main() -> int:
    parser = argparse.ArgumentParser(description="確定申告PDFから給与支払金額を抽出")
    parser.add_argument("--pdf", type=Path, help="PDFパス（省略時は .env の TAX_RETURN_*）")
    parser.add_argument("--export-shell", action="store_true", help="source 用に ANNUAL_INCOME_* を出力")
    args = parser.parse_args()

    env = load_env(ENV_FILE)
    pdf = args.pdf or resolve_pdf(env)
    gross = extract_salary_gross_yen(pdf)
    if gross is None:
        print(f"⚠️  給与支払金額を PDF から特定できませんでした: {pdf}", file=sys.stderr)
        return 1

    manyen = manyen_from_yen(gross)
    print(f"TAX_RETURN_PDF_PATH={pdf}")
    print(f"ANNUAL_INCOME_GROSS_YEN={gross}")
    print(f"ANNUAL_INCOME_MANYEN={manyen}")
    print(f"ANNUAL_INCOME={gross}")

    if args.export_shell:
        pdf_escaped = str(pdf).replace("'", "'\\''")
        print(f"export TAX_RETURN_PDF_PATH='{pdf_escaped}'")
        print(f"export ANNUAL_INCOME_GROSS_YEN={gross}")
        print(f"export ANNUAL_INCOME_MANYEN={manyen}")
        print(f"export ANNUAL_INCOME={gross}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

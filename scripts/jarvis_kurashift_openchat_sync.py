#!/usr/bin/env python3
"""神大家 LINEオープンチャット → kamiooya-qa 一本化 ＆ Grok共有

役割:
  1. 815神大家オプチャの 5.やり取り.md をパース（YAMLの title_substring を chat_title 正本に）
  2. kamiooya-qa: line_openchat_logs へ **差分のみ** UPSERT（新規／内容変更 → staging）
  3. 公開は jarvis_openchat_publish.py（staging のみ ready / excluded）
  4. Grok Bot 共有: Drive 【with Grok bot】/30_shared_working/ へ知見MD＋タイトル別カタログ

※ jarvis-dashboard の kurashift_openchat_logs は廃止（二重管理しない）。
※ 見出し日時（YYYY/MM/DD HH:MM）→ post_date + posted_at を UPSERT。
※ 変更なし行は触らない（egress 抑制。embedding を毎回返さない）。

使用例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_kurashift_openchat_sync.py --apply --export-grok
  python scripts/jarvis_kurashift_openchat_sync.py --route 31_shuzen_soudan_g --apply
  python scripts/jarvis_kurashift_openchat_sync.py --apply --full  # 復旧用・全件
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = Any

REPAIR_CATEGORIES = {
    "水回り・給排水": ["漏水", "水漏れ", "水道", "排水", "給湯器", "浴室", "浴槽", "トイレ", "洗面", "キッチン", "水栓"],
    "外壁・屋根・雨漏り": ["雨漏り", "外壁", "屋根", "塗装", "コーキング", "防水", "シーリング", "クラック", "雨樋"],
    "内装・原状回復": ["クロス", "床", "フロアタイル", "CF", "畳", "襖", "障子", "建具", "原状回復", "クリーニング", "パテ"],
    "電気・通信・設備": ["アンテナ", "エアコン", "分電盤", "アース", "単相", "3線", "ブレーカー", "換気扇", "インターホン"],
    "解体・残置物・不用品": ["残置物", "不用品", "片付け", "解体", "ゴミ屋敷", "撤去", "処分"],
    "外構・草刈り・庭木": ["草刈り", "雑草", "除草", "防草シート", "砂利", "剪定", "伐採", "フェンス", "外構", "アスファルト"],
    "ガス・プロパン": ["プロパン", "都市ガス", "ガス給湯器", "無償配管", "配管", "ガス会社"],
    "害虫・害獣": ["シロアリ", "害獣", "ネズミ", "ハチ", "コウモリ", "イタチ", "駆除"],
}

VENDOR_SIGNALS = [
    "業者", "便利屋", "職人", "工務店", "水道屋",
    "塗装屋", "電気屋", "ジモティー", "くらしのマーケット", "ミツモア",
    "見積もり", "見積", "発注", "対応可能", "リビングステージ",
    "散水テスト", "コーキング", "OSB", "ビリビリガード", "ダイノック",
    "紹介頂け", "紹介いただけ", "安い業者", "おすすめ業者", "施工代金",
]

NOISE_MARKERS = [
    "物件紹介になります", "運営です。", "■物件のポイント", "■ポイント■",
    "想定表面利回り", "満室想定利回り", "土地値割合", "土地割合",
]

QA_ENV_CANDIDATES = [
    REPO / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env",
    REPO / "apps/kamiooya-qa-web/.env.local",
]

GROK_SHARED = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ"
    / "【with Grok bot】/30_shared_working"
)


def load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def jarvis_sb() -> Client:
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def qa_sb() -> Client:
    for p in QA_ENV_CANDIDATES:
        load_dotenv_file(p)
    url = os.environ.get("SUPABASE_URL") or os.environ.get("KAMIOOYA_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("KAMIOOYA_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing kamiooya SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (scripts/.env)")
    return create_client(url, key)


def parse_heading_datetime(date_str: str) -> tuple[str | None, str | None]:
    """見出し先頭の日時 → (post_date ISO date, posted_at ISO timestamptz JST)。

    新規: ``YYYY/MM/DD HH:MM``。既存: ``YYYY/MM/DD``（時刻は 00:00 JST）。
    """
    s = (date_str or "").strip()
    if not s or s == "?":
        return None, None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(s, fmt)
            post_date = dt.date().isoformat()
            # 見出し時刻は JST 前提
            posted_at = f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}+09:00"
            return post_date, posted_at
        except ValueError:
            continue
    return None, None


def parse_heading(line: str) -> dict[str, str] | None:
    if not line.startswith("### "):
        return None
    raw = line[4:].strip()
    parts = [p.strip() for p in raw.split("｜")]
    if len(parts) < 3:
        return None

    date_str = parts[0]
    stream_tag = parts[1]
    chat_name = parts[2]

    stream_type = "main"
    if "【スレッド返信】" in stream_tag:
        stream_type = "thread_reply"
    elif "【スレッド】" in stream_tag:
        stream_type = "thread"

    thread_title = ""
    sender = ""
    summary = ""
    idx = 3
    if stream_type in ("thread", "thread_reply") and idx < len(parts):
        thread_title = parts[idx]
        idx += 1
    if idx < len(parts):
        sender = parts[idx]
        idx += 1
    if idx < len(parts):
        summary = "｜".join(parts[idx:])

    return {
        "date_str": date_str,
        "stream_type": stream_type,
        "chat_name": chat_name,
        "thread_title": thread_title,
        "sender": sender,
        "summary": summary,
    }


def parse_messages_from_md(md_path: Path, route_id: str, chat_title: str) -> list[dict[str, Any]]:
    if not md_path.is_file():
        return []

    text = md_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    entries: list[dict[str, Any]] = []
    current_meta: dict[str, str] | None = None
    body_lines: list[str] = []

    def commit_entry() -> None:
        nonlocal current_meta, body_lines
        if not current_meta:
            return
        content = "\n".join(body_lines).strip()
        if not content and current_meta.get("summary"):
            content = current_meta["summary"]

        if content and "[非テキスト contentType=1]" not in content:
            raw_id_src = f"{route_id}_{current_meta['date_str']}_{current_meta['sender']}_{content[:100]}"
            msg_id = hashlib.sha256(raw_id_src.encode("utf-8")).hexdigest()[:24]

            chat = current_meta["chat_name"]
            is_repair_route = (
                "31修繕" in chat
                or "修繕相談" in chat
                or "修繕" in chat_title
                or ("31" in route_id and "shuzen" in route_id)
            )
            matched_cat = None
            for cat, kws in REPAIR_CATEGORIES.items():
                if any(kw in content for kw in kws):
                    matched_cat = cat
                    break
            has_vendor = any(k in content for k in VENDOR_SIGNALS)
            is_repair = is_repair_route or (matched_cat is not None and has_vendor)

            p_date, posted_at = parse_heading_datetime(current_meta.get("date_str") or "")

            entries.append({
                "id": f"oc_{msg_id}",
                "route_id": route_id,
                "chat_title": chat_title,
                "chat_name": current_meta["chat_name"] or chat_title,
                "stream_type": current_meta["stream_type"],
                "thread_title": current_meta["thread_title"] or None,
                "post_date": p_date,
                "posted_at": posted_at,
                "sender_name": current_meta["sender"] or None,
                "content": content,
                "is_repair_related": is_repair,
                "repair_category": matched_cat,
                "source_system": "line_openchat",
                "ingest_status": "staging",
                "metadata": {
                    "summary": current_meta.get("summary"),
                    "source_file": str(md_path),
                    "yaml_title": chat_title,
                    "heading_datetime": current_meta.get("date_str"),
                },
            })

        current_meta = None
        body_lines = []

    for line in lines:
        if line.startswith("### "):
            commit_entry()
            meta = parse_heading(line)
            if meta:
                current_meta = meta
            continue
        if current_meta:
            if "<details>" in line or "<summary>" in line or "</summary>" in line:
                continue
            if "</details>" in line:
                continue
            if line.strip() == "---":
                continue
            body_lines.append(line)

    commit_entry()
    return entries


# DB 照合に使う列（embedding / metadata / updated_at は見ない）
COMPARE_FIELDS = (
    "content",
    "sender_name",
    "posted_at",
    "post_date",
    "chat_title",
    "chat_name",
    "stream_type",
    "thread_title",
    "is_repair_related",
    "repair_category",
)

UPSERT_COLS = [
    "id",
    "route_id",
    "chat_title",
    "chat_name",
    "stream_type",
    "thread_title",
    "post_date",
    "posted_at",
    "sender_name",
    "content",
    "is_repair_related",
    "repair_category",
    "source_system",
    "ingest_status",
    "metadata",
]

EXISTING_SELECT = "id," + ",".join(COMPARE_FIELDS)


def _norm_val(v: Any) -> Any:
    """比較用に空相当を揃える。"""
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    if isinstance(v, bool):
        return bool(v)
    return v


def row_fingerprint(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(_norm_val(row.get(k)) for k in COMPARE_FIELDS)


def partition_diff_rows(
    parsed: list[dict[str, Any]],
    existing_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """新規・変更・変更なしに分ける。

    Returns:
        (to_upsert, unchanged_ids_count_proxy as list unused, unchanged_count)
        to_upsert は ingest_status=staging を付けた行のみ。
    """
    unique: dict[str, dict[str, Any]] = {}
    for e in parsed:
        rid = str(e.get("id") or "")
        if not rid:
            continue
        unique[rid] = e

    to_upsert: list[dict[str, Any]] = []
    unchanged = 0
    for rid, e in unique.items():
        row = {k: e.get(k) for k in UPSERT_COLS}
        row["id"] = rid
        row["ingest_status"] = "staging"
        prev = existing_by_id.get(rid)
        if prev is None:
            to_upsert.append(row)
            continue
        if row_fingerprint(row) != row_fingerprint(prev):
            to_upsert.append(row)
        else:
            unchanged += 1
    return to_upsert, [], unchanged


def fetch_existing_fingerprints(sb: Client, table: str = "line_openchat_logs") -> dict[str, dict[str, Any]]:
    """embedding を除いた照合用マップをページング取得。"""
    out: dict[str, dict[str, Any]] = {}
    page = 1000
    offset = 0
    while True:
        res = (
            sb.table(table)
            .select(EXISTING_SELECT)
            .range(offset, offset + page - 1)
            .execute()
        )
        chunk = list(res.data or [])
        for r in chunk:
            rid = str(r.get("id") or "")
            if rid:
                out[rid] = r
        if len(chunk) < page:
            break
        offset += page
    return out


def _upsert_returning_minimal(sb: Client, table: str, chunk: list[dict[str, Any]]) -> int:
    """PostgREST に return=minimal を付けて upsert（応答ボディを空に近づける）。"""
    try:
        from postgrest.types import ReturnMethod  # type: ignore

        sb.table(table).upsert(
            chunk, on_conflict="id", returning=ReturnMethod.minimal
        ).execute()
        return len(chunk)
    except TypeError:
        # 古いクライアントは returning 未対応 → 件数だけ返す（差分化が本線）
        res = sb.table(table).upsert(chunk, on_conflict="id").execute()
        return len(res.data or chunk)
    except Exception:
        res = sb.table(table).upsert(chunk, on_conflict="id").execute()
        return len(res.data or chunk)


def upsert_batches(sb: Client, table: str, rows: list[dict[str, Any]], cols: list[str] | None = None) -> int:
    use_cols = cols or UPSERT_COLS
    unique: dict[str, dict[str, Any]] = {}
    for e in rows:
        unique[str(e["id"])] = {k: e.get(k) for k in use_cols}
    items = list(unique.values())
    upserted = 0
    batch = 50
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        upserted += _upsert_returning_minimal(sb, table, chunk)
    return upserted


def export_catalog(entries: list[dict[str, Any]], output_path: Path) -> None:
    """タイトル別の全件カタログ（Grok共有・データソース確認用）"""
    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        by_title[e.get("chat_title") or e.get("chat_name") or "不明"].append(e)

    lines = [
        "# 神大家 LINEオープンチャット データソース・カタログ",
        f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 方針",
        "- 1つのDBに集約（**正本: kamiooya-qa `line_openchat_logs`**。jarvis 側テーブルは廃止）",
        "- 各行の `chat_title` でオプチャ名がわかる",
        "- Q&A検索公開は `jarvis_openchat_publish.py` で ready（ノイズのみ excluded）",
        "",
        "## オプチャ別件数",
        "",
        "| chat_title | 件数 | 修繕関連 |",
        "|---|---:|---:|",
    ]
    for title in sorted(by_title.keys()):
        items = by_title[title]
        repair_n = sum(1 for x in items if x.get("is_repair_related"))
        lines.append(f"| {title} | {len(items)} | {repair_n} |")

    lines.extend(["", "---", "", "## サンプル（各タイトル直近3件）", ""])
    for title in sorted(by_title.keys()):
        items = sorted(by_title[title], key=lambda x: str(x.get("post_date") or ""), reverse=True)
        lines.append(f"### {title}")
        lines.append("")
        for it in items[:3]:
            d = it.get("post_date") or ""
            sender = it.get("sender_name") or "匿名"
            c = (it.get("content") or "").replace("\n", " ").strip()
            if len(c) > 160:
                c = c[:160] + "..."
            lines.append(f"- **[{d}] {sender}**: {c}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Grok向けカタログをエクスポート: {output_path}")


def export_for_grok(entries: list[dict[str, Any]], output_path: Path) -> None:
    def is_repair_route(e: dict[str, Any]) -> bool:
        rid = str(e.get("route_id") or "")
        title = str(e.get("chat_title") or "")
        chat = str(e.get("chat_name") or "")
        return ("shuzen" in rid) or ("31修繕" in chat) or ("修繕" in title)

    primary = [e for e in entries if is_repair_route(e)]
    secondary = []
    for e in entries:
        if is_repair_route(e):
            continue
        content = e.get("content") or ""
        if any(m in content for m in NOISE_MARKERS):
            continue
        if not e.get("is_repair_related") or not e.get("repair_category"):
            continue
        if not any(k in content for k in VENDOR_SIGNALS):
            continue
        secondary.append(e)

    def grok_rank(e: dict[str, Any]) -> tuple:
        content = e.get("content") or ""
        has_v = any(k in content for k in VENDOR_SIGNALS)
        is_thread = (e.get("stream_type") or "") == "thread"
        return (0 if is_repair_route(e) else 1, 0 if has_v else 1, 0 if is_thread else 1)

    display_pool = [
        e for e in (primary + secondary)
        if e.get("repair_category") or any(k in (e.get("content") or "") for k in VENDOR_SIGNALS)
    ]
    buckets: dict[tuple, list] = defaultdict(list)
    for e in display_pool:
        buckets[grok_rank(e)].append(e)
    repair_entries: list[dict[str, Any]] = []
    for k in sorted(buckets.keys()):
        items = buckets[k]
        items.sort(key=lambda x: str(x.get("post_date") or ""), reverse=True)
        repair_entries.extend(items)

    lines: list[str] = [
        "# 神大家さん倶楽部 LINEオープンチャット 修繕業者・相談知見リスト",
        f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "情報源: 815神大家オプチャ（chat_title 付き）",
        "",
        "## 概要と使い方（Grok S4修繕職人・統括向け）",
        "先輩大家・サポート担当の修繕業者・単価・工法知見。見積妥当性チェック時に参照。",
        f"- 31修繕相談G由来: {len(primary)} 件",
        f"- 他ルート（業者・工法シグナルあり）: {len(secondary)} 件",
        "",
        "---",
        "",
        "## カテゴリ別 修繕知見・おすすめ業者ピックアップ",
        "",
    ]

    by_category: dict[str, list[dict[str, Any]]] = {}
    for e in repair_entries:
        cat = e.get("repair_category") or "総合・その他"
        by_category.setdefault(cat, []).append(e)

    for cat, items in by_category.items():
        lines.append(f"### ■ {cat} ({len(items)}件)")
        lines.append("")
        for it in items[:20]:
            d = it.get("post_date") or ""
            sender = it.get("sender_name") or "匿名"
            stype = it.get("stream_type") or "main"
            title = it.get("chat_title") or it.get("chat_name") or ""
            c = (it.get("content") or "").replace("\n", " ").strip()
            if len(c) > 200:
                c = c[:200] + "..."
            lines.append(f"- **[{d}] {sender} ({stype} · {title})**:")
            lines.append(f"  > {c}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Grok Bot向け修繕知見をエクスポート: {output_path}")
    print(f"   primary={len(primary)} secondary={len(secondary)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE OpenChat → kamiooya-qa (一本化) & Grok")
    parser.add_argument("--route", help="特定 route_id / title_substring")
    parser.add_argument("--apply", action="store_true", help="kamiooya-qa line_openchat_logs へ投入（正本）")
    parser.add_argument(
        "--also-qa",
        action="store_true",
        help="互換フラグ（--apply と同じ。旧運用向け）",
    )
    parser.add_argument("--export-grok", action="store_true", help="Grok共有MDを出力")
    parser.add_argument("--limit", type=int, default=0, help="各ルート上限（0=全件）")
    parser.add_argument(
        "--full",
        action="store_true",
        help="差分を無視して全件 staging upsert（復旧・再取込用）",
    )
    parser.add_argument(
        "--dry-run-diff",
        action="store_true",
        help="DB照合して新規/変更/変更なし件数だけ表示（書込なし）",
    )
    args = parser.parse_args()
    do_apply = bool(args.apply or args.also_qa)

    routes_yaml = REPO / "line_unofficial_poc" / "open_chat_routes.yaml"
    if not routes_yaml.exists():
        print(f"Error: {routes_yaml} not found")
        return 1

    routes = yaml.safe_load(routes_yaml.read_text(encoding="utf-8")).get("routes", [])
    if args.route:
        routes = [
            r for r in routes
            if r.get("id") == args.route or args.route in str(r.get("title_substring") or "")
        ]

    all_entries: list[dict[str, Any]] = []
    print(f"🔍 対象ルート数: {len(routes)} 件")
    for r in routes:
        rid = r.get("id") or ""
        title = str(r.get("title_substring") or rid)
        out_md = Path(r.get("output_md") or "")
        if not out_md.exists():
            print(f"  · MISS {title}: {out_md}")
            continue
        entries = parse_messages_from_md(out_md, rid, title)
        if args.limit and args.limit > 0:
            entries.sort(key=lambda x: str(x.get("post_date") or ""), reverse=True)
            entries = entries[: args.limit]
        all_entries.extend(entries)
        print(f"  · {title}: {len(entries)} 件")

    repair_n = sum(1 for e in all_entries if e.get("is_repair_related"))
    print(f"📊 合計: {len(all_entries)} 件 (修繕関連: {repair_n})")

    if do_apply or args.dry_run_diff:
        sb = qa_sb()
        if args.full:
            to_upsert = []
            for e in all_entries:
                row = {k: e.get(k) for k in UPSERT_COLS}
                row["id"] = e.get("id")
                row["ingest_status"] = "staging"
                to_upsert.append(row)
            unchanged = 0
            existing_n = -1
            new_n = len(to_upsert)
            changed_n = 0
            mode = "FULL"
        else:
            existing = fetch_existing_fingerprints(sb)
            existing_n = len(existing)
            to_upsert, _, unchanged = partition_diff_rows(all_entries, existing)
            existing_ids = set(existing.keys())
            new_n = sum(1 for r in to_upsert if r["id"] not in existing_ids)
            changed_n = len(to_upsert) - new_n
            mode = "DIFF"
        print(
            f"📎 openchat sync — mode={mode}"
            f" existing={existing_n if existing_n >= 0 else 'n/a'}"
            f" new={new_n} changed={changed_n if mode == 'DIFF' else 'n/a(full)'}"
            f" unchanged={unchanged} upsert={len(to_upsert)}"
        )
        if args.dry_run_diff and not do_apply:
            print("ℹ️ --dry-run-diff のみ（DB未書込）")
        elif do_apply:
            n = upsert_batches(sb, "line_openchat_logs", to_upsert)
            print(f"✅ kamiooya-qa line_openchat_logs UPSERT (staging・差分): {n}")

    if args.export_grok or do_apply:
        # Google Drive(CloudStorage) は同期中の EDEADLK 等で書けないことがある。
        # DB(正本)反映は済んでいるため、二次投影の失敗で全体を落とさない。
        try:
            export_for_grok(all_entries, GROK_SHARED / "神大家オプチャ_修繕業者・相談知見リスト.md")
            export_catalog(all_entries, GROK_SHARED / "神大家オプチャ_データソースカタログ.md")
        except OSError as e:
            print(
                f"⚠️ Grok共有の書き出しをスキップ（{type(e).__name__}: {e}）",
                file=sys.stderr,
            )

    if not do_apply and not args.export_grok and not args.dry_run_diff:
        print("ℹ️ --apply / --export-grok / --dry-run-diff のいずれかが必要です")

    return 0


if __name__ == "__main__":
    sys.exit(main())

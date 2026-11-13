#!/usr/bin/env python3
"""Pull confirmed daily reviews into monthly notes in the local Obsidian Vault."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from jarvis_obsidian_vault_reader import VaultReadError, process_request

REPO = Path(__file__).resolve().parents[1]
VAULT = Path.home() / "Documents/500_Obsidian_r1"
RELATIVE_DIR = Path("01_Journaling/★Journal")
DEFAULT_API = "https://jarvis-dashboard-amber.vercel.app"
MAX_RESPONSE = 2 * 1024 * 1024


class InboxError(RuntimeError):
    pass


def api_request(
    url: str,
    key: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
            **(extra_headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        raise InboxError(f"handoff API HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", "timeout")
        raise InboxError(f"handoff API unavailable: {reason}") from None
    if len(raw) > MAX_RESPONSE:
        raise InboxError("handoff response too large")
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InboxError("handoff API returned invalid JSON") from None
    if not isinstance(body, dict) or body.get("ok") is False:
        raise InboxError("handoff API returned an error")
    return body


def safe_review(item: dict) -> tuple[str, str, str, str]:
    review_id = str(item.get("review_id") or "")
    if len(review_id) != 36 or any(c not in "0123456789abcdef-" for c in review_id.lower()):
        raise InboxError("invalid review id")
    try:
        review_date = date.fromisoformat(str(item.get("review_date") or ""))
    except ValueError:
        raise InboxError("invalid review date") from None
    raw_log = item.get("raw_log")
    tactical = item.get("tactical_review")
    if not isinstance(raw_log, str) or not raw_log.strip() or not isinstance(tactical, str) or not tactical.strip():
        raise InboxError("review payload is incomplete")
    if len(raw_log) > 180_000 or len(tactical) > 60_000:
        raise InboxError("review payload exceeds local limit")
    return review_id, review_date.isoformat(), raw_log, tactical


def note_contents(review_id: str, review_date: str, kind: str, body: str, peer: str) -> str:
    frontmatter = {
        "date": review_date,
        "type": f"daily_review_{kind}",
        "review_id": review_id,
        "peer_note": peer,
        "source": "ChatGPT daily review confirmation",
    }
    yaml = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in frontmatter.items())
    return f"---\n{yaml}\n---\n\n{body.rstrip()}\n"


def write_no_clobber(target: Path, content: str) -> None:
    if target.is_symlink():
        raise InboxError("refusing symlink target")
    encoded = content.encode("utf-8")
    if target.exists():
        if target.read_bytes() == encoded:
            return
        raise InboxError("a different note already exists at the destination")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(tmp, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != encoded:
                raise InboxError("a different note already exists at the destination") from None
    finally:
        tmp.unlink(missing_ok=True)


def daily_note_contents(review_id: str, review_date: str, raw_log: str, tactical: str) -> str:
    frontmatter = {"date": review_date, "type": "daily_review", "review_id": review_id,
                   "source": "ChatGPT daily review confirmation"}
    yaml = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in frontmatter.items())
    # Preserve each submitted body, including its trailing whitespace.
    return (f"---\n{yaml}\n---\n\n# {review_date}\n\n## 生ログ\n\n"
            + raw_log + "\n\n## 戦術レビュー\n\n" + tactical + "\n")


def write_review(item: dict) -> list[str]:
    review_id, review_date, raw_log, tactical = safe_review(item)
    vault = VAULT.expanduser().resolve()
    if not vault.is_dir():
        raise InboxError("canonical Obsidian Vault is not present")
    relative = RELATIVE_DIR / review_date[:7] / f"{review_date}.md"
    directory = vault
    # Do not follow symlinks, even during directory creation.
    for part in relative.parent.parts:
        directory = directory / part
        if directory.is_symlink():
            raise InboxError("refusing symlink directory")
        directory.mkdir(exist_ok=True)
        if not directory.resolve().is_relative_to(vault):
            raise InboxError("review directory resolves outside the Vault")
    target = directory / relative.name
    content = daily_note_contents(review_id, review_date, raw_log, tactical)
    write_no_clobber(target, content)
    if target.is_symlink() or target.read_bytes() != content.encode("utf-8"):
        raise InboxError("local note verification failed")
    return [relative.as_posix()]


def process_vault_read_requests(api: str, key: str, items: list) -> bool:
    """Serve only bounded read requests from the local Vault; never log query or excerpts."""
    if not isinstance(items, list):
        print("Vault read poll returned invalid item list", file=sys.stderr)
        return False
    ok = True
    for item in items:
        request_id = str(item.get("id") or "") if isinstance(item, dict) else "unknown"
        if not isinstance(item, dict):
            ok = False
            continue
        try:
            output = process_request(item)
            response_payload = {"request_id": request_id, "result": output}
        except VaultReadError as exc:
            response_payload = {"request_id": request_id, "error_code": str(exc)}
        except (OSError, ValueError):
            response_payload = {"request_id": request_id, "error_code": "read_failed"}
        try:
            api_request(
                f"{api}/api/obsidian-vault/inbox",
                key,
                method="POST",
                payload=response_payload,
            )
            print(f"Vault read {'completed' if 'result' in response_payload else 'failed'} {request_id[:8]}")
        except InboxError as exc:
            print(f"Vault read response failed {request_id[:8]}: {exc}", file=sys.stderr)
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list pending review IDs without saving")
    args = parser.parse_args()
    api = (os.environ.get("OBSIDIAN_REVIEW_INBOX_URL") or DEFAULT_API).rstrip("/")
    key = (os.environ.get("OBSIDIAN_REVIEW_POLL_KEY") or "").strip()
    read_key = (os.environ.get("OBSIDIAN_VAULT_POLL_KEY") or "").strip()
    if not key:
        print("OBSIDIAN_REVIEW_POLL_KEY is not configured", file=sys.stderr)
        return 2
    try:
        dry_query = "&dryRun=1" if args.dry_run else ""
        extra_headers = {"X-Obsidian-Vault-Poll-Key": read_key} if read_key else None
        result = api_request(
            f"{api}/api/obsidian-review/inbox?limit=5{dry_query}",
            key,
            extra_headers=extra_headers,
        )
    except InboxError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    items = result.get("items")
    if not isinstance(items, list):
        print("handoff API returned invalid item list", file=sys.stderr)
        return 1
    expired_count = result.get("expired_count")
    if isinstance(expired_count, int) and expired_count > 0:
        print(f"warning: {expired_count} pending review(s) expired before Mac delivery", file=sys.stderr)
    failed = False
    for item in items:
        review_id = str(item.get("review_id") or "") if isinstance(item, dict) else "unknown"
        try:
            if not isinstance(item, dict):
                raise InboxError("invalid inbox item")
            if args.dry_run:
                safe_review(item)
                print(f"pending {review_id[:8]} {item.get('review_date')}")
                continue
            paths = write_review(item)
            api_request(
                f"{api}/api/obsidian-review/inbox",
                key,
                method="POST",
                payload={"review_id": review_id, "saved_paths": paths},
            )
            print(f"saved locally {review_id[:8]} {item.get('review_date')}; existing Obsidian sync pending verification")
        except (InboxError, OSError, ValueError) as exc:
            failed = True
            print(f"review {review_id[:8]}: {exc}", file=sys.stderr)
    read_items = result.get("vault_read_items") or []
    if read_key and not args.dry_run and not process_vault_read_requests(api, read_key, read_items):
        failed = True
    if isinstance(expired_count, int) and expired_count > 0:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

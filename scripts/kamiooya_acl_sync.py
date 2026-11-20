#!/usr/bin/env python3
"""旧（ムンバイ）の public の権限（GRANT）を、東京の新プロジェクトへそのまま写す SQL を作る（2026-11-20）。

新しいプロジェクトは public の既定権限が広く（anon / authenticated に全権）、構造を写すと
旧では閉じていた表まで anon から触れる形になる。旧の権限一覧（ACL）を正本にして、
anon / authenticated / service_role / PUBLIC の分を一度外してから旧と同じに付け直す。postgres の分は触らない。

標準入力: SOURCE_QUERY の結果（1行1オブジェクト「種類 名前 ACL」）。標準出力: 写し先で流す SQL。
"""
from __future__ import annotations

import re
import sys

ROLES = ["anon", "authenticated", "service_role"]

# 旧で流して、1行1オブジェクトの一覧を出す問い合わせ（-tA で使う）
SOURCE_QUERY = """
select c.relkind::text||' '||quote_ident(c.relname)||' '||coalesce(c.relacl::text,'NULL')
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='public' and c.relkind in ('r','v','m','p','S')
union all
select 'f '||p.oid::regprocedure::text||' '||coalesce(p.proacl::text,'NULL')
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public'
union all
select 'd'||defaclobjtype::text||' - '||defaclacl::text from pg_default_acl
 where defaclrole='postgres'::regrole and defaclnamespace='public'::regnamespace
order by 1
""".strip()

PRIVS = {
    "r": {"a": "INSERT", "r": "SELECT", "w": "UPDATE", "d": "DELETE", "D": "TRUNCATE",
          "x": "REFERENCES", "t": "TRIGGER", "m": "MAINTAIN"},
    "S": {"r": "SELECT", "w": "UPDATE", "U": "USAGE"},
    "f": {"X": "EXECUTE"},
}
KIND = {"r": "TABLE", "v": "TABLE", "m": "TABLE", "p": "TABLE", "S": "SEQUENCE", "f": "FUNCTION"}
DEF_KIND = {"r": "TABLES", "S": "SEQUENCES", "f": "FUNCTIONS"}


def parse_acl(acl: str, kind: str) -> dict[str, list[str]]:
    """'{postgres=arw/postgres,anon=w/postgres,=X/postgres}' → {'anon': ['UPDATE'], 'PUBLIC': ['EXECUTE']}"""
    if acl == "NULL":  # 既定: 関数は PUBLIC に EXECUTE、表・連番は持ち主だけ
        return {"PUBLIC": ["EXECUTE"]} if kind == "f" else {}
    table = PRIVS["r" if kind in "rvmp" else kind]
    out: dict[str, list[str]] = {}
    for item in acl.strip("{}").split(","):
        m = re.fullmatch(r'"?([^=]*)=([A-Za-z*]*)/.*', item)
        if not m:
            raise ValueError(f"読めない ACL: {item}")
        who = m.group(1) or "PUBLIC"
        if who not in ROLES + ["PUBLIC"]:
            continue
        privs = [table[ch] for ch in m.group(2).replace("*", "") if ch in table]
        if privs:
            out[who] = privs
    return out


def to_sql(lines: list[str]) -> str:
    sql = ["SET ROLE postgres;"]
    everyone = ", ".join(ROLES + ["PUBLIC"])
    for line in lines:
        line = line.strip()
        if not line:
            continue
        head, acl = line.rsplit(" ", 1)
        kind, name = head.split(" ", 1)
        if kind.startswith("d"):
            k = kind[1]
            what = DEF_KIND[k]
            sql.append(f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON {what} FROM {everyone};")
            for who, privs in parse_acl(acl, k).items():
                sql.append(f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT {', '.join(privs)} ON {what} TO {who};")
            continue
        obj = f"{KIND[kind]} public.{name}"
        sql.append(f"REVOKE ALL ON {obj} FROM {everyone};")
        for who, privs in parse_acl(acl, kind).items():
            sql.append(f"GRANT {', '.join(privs)} ON {obj} TO {who};")
    return "\n".join(sql) + "\n"


if __name__ == "__main__":
    if sys.argv[1:] == ["--query"]:
        print(SOURCE_QUERY)
    else:
        sys.stdout.write(to_sql(sys.stdin.read().splitlines()))

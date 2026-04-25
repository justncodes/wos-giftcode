#!/usr/bin/env python3
"""ID <=> nickname manager for Whiteout gift-code API.

Features:
- Add or update mapping: ID <=> current nickname + optional remark.
- Query mapping: show current nickname and historical remarks.
- Query one ID raw login_resp.json() data field.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

BASE_URL = "https://wjdr-giftcode-api.campfiregames.cn"
LOGIN_URL = BASE_URL + "/api/player"
WOS_ENCRYPT_KEY = "Uiv#87#SPan.ECsp"

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "id_name_map.json")
REQUEST_TIMEOUT = 15
MAX_RETRIES = 4
RETRY_DELAY = 3


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message):
    print(f"[{now_str()}] {message}")


def encode_data(data):
    serialized_items = []
    for key in sorted(data.keys()):
        value = data[key]
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            value = str(value)
        serialized_items.append((key, value))

    encoded_data = urlencode(serialized_items, encoding="utf-8")
    sign = hashlib.md5(f"{encoded_data}{WOS_ENCRYPT_KEY}".encode("utf-8")).hexdigest()
    return f"{encoded_data}&sign={sign}"


def make_request(url, payload):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://wjdr-giftcode.centurygames.cn",
        "Referer": "https://wjdr-giftcode.centurygames.cn/",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp
            log(f"Request attempt {attempt}/{MAX_RETRIES} failed: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            log(f"Request attempt {attempt}/{MAX_RETRIES} error: {exc}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)

    return None


def fetch_login_data(fid):
    payload = encode_data({"fid": str(fid).strip(), "time": int(time.time() * 1000)})
    resp = make_request(LOGIN_URL, payload)
    if not resp:
        return None, "request_failed"

    try:
        login_resp_json = resp.json()
    except json.JSONDecodeError:
        return None, "invalid_json"

    if login_resp_json.get("code") != 0:
        return None, login_resp_json.get("msg", "login_failed")

    return login_resp_json.get("data", {}), None


def fetch_current_nickname(fid):
    data, err = fetch_login_data(fid)
    if err:
        return None, err

    nickname = data.get("nickname")
    if not nickname:
        return None, "nickname_missing"
    return nickname, None


def load_db(db_path):
    if not os.path.exists(db_path):
        return {"records": {}}

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "records" not in data:
                return {"records": {}}
            return data
    except (OSError, json.JSONDecodeError):
        return {"records": {}}


def save_db(db_path, data):
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_record(db, fid):
    records = db.setdefault("records", {})
    if fid not in records:
        records[fid] = {
            "current_name": None,
            "remarks": [],
            "last_checked_at": None,
            "updated_at": None,
        }
    return records[fid]


def migrate_record_schema(record):
    # Backward compatibility for early version that stored aliases.
    if "remarks" not in record:
        aliases = record.get("aliases", [])
        remarks = []
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                remarks.append({"remark": alias.strip(), "created_at": None})
        record["remarks"] = remarks

    if "aliases" in record:
        record.pop("aliases", None)


def append_remark_if_needed(record, remark, only_check_latest=False):
    if remark is None:
        return False

    remark = remark.strip()
    if not remark:
        return False

    remarks = record.setdefault("remarks", [])

    if only_check_latest:
        if remarks:
            latest = remarks[-1]
            latest_text = latest.get("remark") if isinstance(latest, dict) else latest
            if latest_text == remark:
                return False
    else:
        for item in remarks:
            text = item.get("remark") if isinstance(item, dict) else item
            if text == remark:
                return False

    remarks.append(
        {
            "remark": remark,
            "created_at": now_str(),
        }
    )
    return True


def build_auto_remark(nickname, alliance=None):
    name = (nickname or "").strip()
    if not name:
        return ""

    alliance_name = (alliance or "").strip()
    if alliance_name:
        return f"{alliance_name} {name}"

    return name


def validate_ids(raw_ids):
    valid = []
    for raw_fid in raw_ids:
        fid = str(raw_fid).strip()
        if not fid.isdigit():
            log(f"Skip invalid ID: {raw_fid}")
            continue
        valid.append(fid)
    return valid


def cmd_add(args):
    db = load_db(args.db)
    updated = 0

    for fid in validate_ids(args.ids):
        current_name, err = fetch_current_nickname(fid)
        if err:
            log(f"ID {fid}: failed to fetch current nickname ({err})")
            continue

        record = ensure_record(db, fid)
        migrate_record_schema(record)

        manual_remark = args.remark.strip() if isinstance(args.remark, str) else ""
        if manual_remark:
            added_remark = append_remark_if_needed(record, manual_remark)
        else:
            auto_remark = build_auto_remark(current_name, args.alliance)
            # If no manual remark is provided, keep the latest remark synced with current nickname.
            added_remark = append_remark_if_needed(
                record,
                auto_remark,
                only_check_latest=True,
            )

        record["current_name"] = current_name
        record["last_checked_at"] = now_str()
        record["updated_at"] = now_str()

        message = f"ID {fid}: current='{current_name}'"
        if manual_remark:
            message += f", remark='{manual_remark}'"
        elif added_remark:
            message += f", auto_remark='{auto_remark}'"
        if added_remark:
            message += " (new remark)"
        log(message)

        updated += 1

    save_db(args.db, db)
    log(f"Done. Updated {updated} record(s). DB: {args.db}")


def print_record_details(fid, record, old_cache_name=None):
    migrate_record_schema(record)
    current = record.get("current_name") or "<unknown>"
    remarks = record.get("remarks") or []
    checked = record.get("last_checked_at") or "-"

    print(f"ID: {fid}")
    if old_cache_name is not None:
        old_name = old_cache_name.strip() if isinstance(old_cache_name, str) else ""
        print(f"  old_cache_name: {old_name if old_name else '-'}")
    print(f"  current_name: {current}")
    if remarks:
        print(f"  remarks({len(remarks)}):")
        for idx, item in enumerate(remarks, 1):
            remark_text = item.get("remark", "")
            created_at = item.get("created_at") or "-"
            print(f"    {idx}. {remark_text} (created_at: {created_at})")
    else:
        print("  remarks(0): -")
    print(f"  last_checked_at: {checked}")


def render_record(fid, record):
    print_record_details(fid, record)


def cmd_query(args):
    if (args.refresh_dry_run or args.refresh_changes_only) and not args.refresh:
        args.refresh = True

    db = load_db(args.db)
    records = db.get("records", {})
    changed_items = []

    if args.ids:
        ids = [str(x).strip() for x in args.ids]
    else:
        ids = sorted(records.keys(), key=lambda x: int(x) if x.isdigit() else x)

    if not ids:
        log("No records found.")
        return

    for fid in ids:
        if not fid.isdigit():
            log(f"Skip invalid ID: {fid}")
            continue

        record = records.get(fid)
        if not record:
            print(f"ID: {fid}")
            print("  <no local record>")
            if args.refresh:
                current_name, err = fetch_current_nickname(fid)
                if err:
                    print(f"  refresh failed: {err}")
                else:
                    print(f"  current_name(refresh): {current_name}")
            continue

        migrate_record_schema(record)

        display_record = record
        name_changed = False

        if args.refresh:
            current_name, err = fetch_current_nickname(fid)
            if err:
                log(f"ID {fid}: refresh failed ({err})")
            else:
                old_name = (record.get("current_name") or "").strip()
                new_name = (current_name or "").strip()
                name_changed = new_name != old_name

                if name_changed:
                    changed_items.append(
                        {
                            "fid": fid,
                            "old_name": old_name,
                            "new_name": new_name,
                        }
                    )

                if args.refresh_dry_run:
                    display_record = {
                        "current_name": current_name,
                        "remarks": [
                            dict(item) if isinstance(item, dict) else item for item in (record.get("remarks") or [])
                        ],
                        "last_checked_at": now_str(),
                        "updated_at": now_str(),
                    }
                else:
                    display_record = record

                # During refresh, only update auto remark when nickname changed.
                if new_name and new_name != old_name:
                    append_remark_if_needed(display_record, new_name, only_check_latest=True)

                display_record["current_name"] = current_name
                display_record["last_checked_at"] = now_str()
                display_record["updated_at"] = now_str()

        if args.refresh and args.refresh_changes_only and not name_changed:
            continue

        render_record(fid, display_record)

    if args.refresh:
        if args.refresh_dry_run:
            log("Refresh dry-run completed. No DB changes were saved.")
        else:
            save_db(args.db, db)
            log("Refresh completed and saved.")

        print("refresh_change_summary:")
        if changed_items:
            print(f"  changed_ids({len(changed_items)}): {', '.join(item['fid'] for item in changed_items)}")
            print("  details:")
            for item in changed_items:
                old_name = item["old_name"] if item["old_name"] else "-"
                new_name = item["new_name"] if item["new_name"] else "-"
                print(f"    {item['fid']}: '{old_name}' -> '{new_name}'")
        else:
            print("  changed_ids(0): -")


def cmd_data(args):
    fid = str(args.id).strip()
    if not fid.isdigit():
        log(f"Invalid ID: {args.id}")
        return

    data, err = fetch_login_data(fid)
    if err:
        log(f"ID {fid}: failed to fetch data ({err})")
        return

    print(json.dumps(data, ensure_ascii=False, indent=2))


def nickname_matches(current_name, target_nickname, exact=False):
    current = (current_name or "").strip().lower()
    target = (target_nickname or "").strip().lower()
    if not current or not target:
        return False
    if exact:
        return current == target
    return target in current


def find_ids_by_nickname_in_cache(records, nickname, exact=False):
    matched_ids = []
    target = nickname.strip()
    if not target:
        return matched_ids

    for fid, record in records.items():
        migrate_record_schema(record)
        current = (record.get("current_name") or "").strip()
        if nickname_matches(current, target, exact=exact):
            matched_ids.append(fid)

    return sorted(matched_ids, key=lambda x: int(x) if x.isdigit() else x)


def cmd_nickname(args):
    target_nickname = args.nickname.strip()
    if not target_nickname:
        log("Nickname cannot be empty.")
        return

    db = load_db(args.db)
    records = db.get("records", {})

    cache_ids = find_ids_by_nickname_in_cache(records, target_nickname, exact=args.exact)
    if cache_ids and not args.force_api:
        print(f"nickname: {target_nickname}")
        print(f"source: cache")
        print(f"matched_ids({len(cache_ids)}): {', '.join(cache_ids)}")
        print("details:")
        for fid in cache_ids:
            record = records.get(fid, {})
            print_record_details(fid, record)
        return

    if not records:
        log("No local ID records available to scan via API. Please add IDs first.")
        return

    log(
        f"Scanning {len(records)} local IDs via API for nickname='{target_nickname}'"
        + (" (force_api enabled)" if args.force_api else "")
    )

    matched_ids = []
    scanned = 0
    for fid in sorted(records.keys(), key=lambda x: int(x) if x.isdigit() else x):
        if not fid.isdigit():
            continue

        old_cache_name = (records.get(fid, {}).get("current_name") or "").strip()

        current_name, err = fetch_current_nickname(fid)
        scanned += 1
        if err:
            log(f"ID {fid}: API check failed ({err})")
            continue

        record = ensure_record(db, fid)
        migrate_record_schema(record)
        record["current_name"] = current_name
        record["last_checked_at"] = now_str()
        record["updated_at"] = now_str()

        if nickname_matches(current_name, target_nickname, exact=args.exact):
            matched_ids.append({"fid": fid, "old_cache_name": old_cache_name})

        if args.api_sleep > 0:
            time.sleep(args.api_sleep)

    save_db(args.db, db)

    print(f"nickname: {target_nickname}")
    print("source: api-scan")
    print(f"scanned_ids: {scanned}")
    if matched_ids:
        print(f"matched_ids({len(matched_ids)}): {', '.join(item['fid'] for item in matched_ids)}")
        print("details:")
        for item in matched_ids:
            fid = item["fid"]
            record = records.get(fid, {})
            print_record_details(fid, record, old_cache_name=item.get("old_cache_name"))
    else:
        print("matched_ids(0): -")


def build_parser():
    parser = argparse.ArgumentParser(description="Manage ID <=> current nickname and optional remarks")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help=f"Path to local mapping DB (default: {DEFAULT_DB_PATH})")

    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add/update ID mapping using current nickname, with optional remark")
    p_add.add_argument("--ids", nargs="+", required=True, help="One or more numeric IDs")
    p_add.add_argument("--remark", default=None, help="Optional note for this ID")
    p_add.add_argument(
        "--alliance",
        "--ally",
        "-A",
        dest="alliance",
        default=None,
        help="Optional alliance name for auto remark; combined as '<alliance> <nickname>' when --remark is not set",
    )
    p_add.set_defaults(func=cmd_add)

    p_query = sub.add_parser("query", help="Query ID mapping: current nickname + historical remarks")
    p_query.add_argument("--ids", nargs="*", help="IDs to query. Omit to query all local records")
    p_query.add_argument("--refresh", action="store_true", help="Refresh current nickname from API before printing")
    p_query.add_argument(
        "--refresh-dry-run",
        action="store_true",
        help="Preview refresh changes from API without saving DB",
    )
    p_query.add_argument(
        "--refresh-changes-only",
        action="store_true",
        help="When refreshing, only print records whose nickname changed",
    )
    p_query.set_defaults(func=cmd_query)

    p_data = sub.add_parser("data", help="Query one ID raw login_resp.json() data field")
    p_data.add_argument("--id", required=True, help="One numeric ID")
    p_data.set_defaults(func=cmd_data)

    p_nickname = sub.add_parser("nickname", help="Reverse lookup nickname => ID (default: contains match)")
    p_nickname.add_argument("--nickname", required=True, help="Target current nickname")
    p_nickname.add_argument("--force-api", action="store_true", help="Force API scan and ignore cache hit")
    p_nickname.add_argument("--exact", action="store_true", help="Use exact match instead of default contains match")
    p_nickname.add_argument(
        "--api-sleep",
        type=float,
        default=0.35,
        help="Sleep seconds between API checks during scan (default: 0.35)",
    )
    p_nickname.set_defaults(func=cmd_nickname)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except KeyboardInterrupt:
        log("Interrupted by user.")
        return 130
    except Exception as exc:
        log(f"Fatal error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

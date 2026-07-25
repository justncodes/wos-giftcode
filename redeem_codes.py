#!/usr/bin/env python3
# Whiteout Survival Gift Code Redeemer Script Version 5.0.0
# See https://github.com/justncodes/wos-giftcode

import argparse
import csv
import hashlib
import os
import random
import sys
import time
from datetime import datetime, timedelta
from glob import glob
import requests

try:
    import colorama
    colorama.init(autoreset=True)
    C_RESET = colorama.Style.RESET_ALL
    C_INFO = colorama.Fore.CYAN
    C_SUCCESS = colorama.Fore.GREEN
    C_ERROR = colorama.Fore.RED
    C_WARN = colorama.Fore.YELLOW
    C_DIM = colorama.Style.DIM
except ImportError:
    print("Warning: colorama library not found. Log output will not be colored.")
    C_RESET = C_INFO = C_SUCCESS = C_ERROR = C_WARN = C_DIM = ""

BASE_URL = "https://wos-giftcode-api.centurygame.com"
REDEEM_URL = BASE_URL + "/api/gift_code"
ORIGIN = "https://wos-giftcode.centurygame.com"
WOS_ENCRYPT_KEY = "tB87#kPtkxqOS2"

DELAY = 1.0                 # seconds between player IDs
RETRY_DELAY = 2             # seconds between transport retries
MAX_RETRIES = 3             # transport retries per request
MAX_FID_ATTEMPTS = 3        # redemption attempts per player before giving up
TOO_FREQUENT_SLEEP = 60     # per-FID cooldown after a TOO FREQUENT (40019)
MAX_COOLDOWNS = 3           # cooldowns a single player may take before being given up on
MAX_CONSECUTIVE_FAILURES = 10   # players in a row unable to reach the API before aborting the run
MAX_STATE_ID = 999999       # a CSV field this small is a state, never a player ID

TRANSPORT_FAILURE = "Redemption request failed"

script_dir = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(script_dir, "redeemed_codes.txt")

RESULT_MESSAGES = {
    "SUCCESS": "Successfully redeemed",
    "RECEIVED": "Already redeemed",
    "SAME TYPE EXCHANGE": "Successfully redeemed (same type)",
    "TIME ERROR": "Code has expired",
    "CDK NOT FOUND": "Code not found or incorrect",
    "USED": "Claim limit reached, unable to claim",
    "TIMEOUT RETRY": "Server requested retry",
    "TOO FREQUENT": "Rate limited on this player ID",
    "USER INFO ERROR": "Wrong state for this player ID",
    "ROLE NOT EXIST": "No such player",
    "STOVE_LV ERROR": "Furnace level too low for this code",
    "RECHARGE_MONEY ERROR": "Not enough spending for this code",
    "RECHARGE_MONEY_VIP ERROR": "VIP level too low for this code",
    "SIGN ERROR": "Sign error (request encoding issue)",
    "NOT LOGIN": "Session rejected by the server",
}

# Codes that are bad for everyone, not just this player - stop the whole run.
FATAL_STATUSES = ("TIME ERROR", "CDK NOT FOUND", "USED")
SUCCESS_STATUSES = ("SUCCESS", "SAME TYPE EXCHANGE")

counters = {
    "success": 0,
    "already_redeemed": 0,
    "wrong_state": 0,
    "errors": 0,
    "rate_limited": 0,
    "requests": 0,
}

error_details = {}      # fid -> last error message
wrong_state_fids = {}   # fid -> the state that was rejected
cooldowns = {}          # fid -> how many rate limit cooldowns it has taken

script_start_time = time.time()

BROWSER_PROFILES = [
    ('Chrome', list(range(124, 136))),
    ('Brave', list(range(132, 146))),
    ('Edge', list(range(124, 136))),
]

PLATFORMS = [
    ('Windows NT 10.0; Win64; x64', '"Windows"'),
    ('Windows NT 11.0; Win64; x64', '"Windows"'),
    ('Macintosh; Intel Mac OS X 10_15_7', '"macOS"'),
    ('X11; Linux x86_64', '"Linux"'),
]


def log(message, level='info', to_file=True):
    """Log to console with color and, optionally, append to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = {'success': C_SUCCESS, 'error': C_ERROR, 'warn': C_WARN,
             'info': C_INFO, 'dim': C_DIM}.get(level, "")

    console_entry = f"{C_DIM}{timestamp}{C_RESET} - {color}{message}{C_RESET}"
    try:
        print(console_entry)
    except UnicodeEncodeError:
        print(console_entry.encode('utf-8', errors='replace').decode('ascii', errors='replace'))

    if to_file:
        try:
            with open(LOG_FILE, "a", encoding="utf-8-sig", newline='') as f:
                f.write(f"{timestamp} - {message}\n")
        except Exception as e:
            print(f"{C_ERROR}LOGGING ERROR to file {LOG_FILE}: {e}{C_RESET}")


def get_headers():
    """Randomized browser-like headers, rotated per request to avoid bot detection."""
    browser, versions = random.choice(BROWSER_PROFILES)
    version = random.choice(versions)
    platform, sec_platform = random.choice(PLATFORMS)

    if browser == 'Edge':
        sec_ch_ua = f'"Not A(B)rand";v="8", "Chromium";v="{version}", "Microsoft Edge";v="{version}"'
    else:
        sec_ch_ua = f'"Not:A-Brand";v="99", "{browser}";v="{version}", "Chromium";v="{version}"'

    return {
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
        'user-agent': (f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
                       f"Chrome/{version}.0.0.0 Safari/537.36"),
        'origin': ORIGIN,
        'referer': ORIGIN + '/',
        'sec-ch-ua': sec_ch_ua,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': sec_platform,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
    }


def encode_data(data):
    """Sign the payload with the MD5 hash the API expects."""
    sorted_keys = sorted(data.keys())
    encoded = "&".join(f"{key}={data[key]}" for key in sorted_keys)
    return {"sign": hashlib.md5(f"{encoded}{WOS_ENCRYPT_KEY}".encode()).hexdigest(), **data}


SESSION = requests.Session()


def make_request(url, payload):
    """POST with transport-level retries; returns the response or None."""
    endpoint = url.split('/')[-1]
    for attempt in range(MAX_RETRIES):
        try:
            counters["requests"] += 1
            response = SESSION.post(url, data=payload, timeout=(10, 30))

            if response.status_code == 200:
                return response
            if response.status_code == 429:
                log(f"Attempt {attempt+1} to {endpoint}: HTTP 429 (rate limited). Backing off...", level='warn')
                time.sleep(RETRY_DELAY * (attempt + 1) * 2)
                continue
            if response.status_code in (502, 503, 504):
                log(f"Attempt {attempt+1} to {endpoint}: HTTP {response.status_code} (server busy). Retrying...", level='warn')
                time.sleep(RETRY_DELAY * (attempt + 1) * 1.5)
                continue
            log(f"Attempt {attempt+1} to {endpoint}: HTTP {response.status_code}, {response.text[:150]}", level='warn')

        except requests.exceptions.Timeout:
            log(f"Attempt {attempt+1} to {endpoint} timed out. Retrying...", level='warn')
        except requests.exceptions.RequestException as e:
            log(f"Attempt {attempt+1} to {endpoint} failed: {e.__class__.__name__} - {e}", level='warn')

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))

    return None


def classify(data):
    """Map an API response to one of the RESULT_MESSAGES keys."""
    msg = str(data.get("msg", "Unknown error")).strip('.')
    err_code = data.get("err_code")

    if msg == "SUCCESS":
        return "SUCCESS"
    if msg == "RECEIVED" and err_code == 40008:
        return "RECEIVED"
    if msg == "SAME TYPE EXCHANGE" and err_code == 40011:
        return "SAME TYPE EXCHANGE"
    if msg == "TIME ERROR" and err_code == 40007:
        return "TIME ERROR"
    if msg == "CDK NOT FOUND" and err_code == 40014:
        return "CDK NOT FOUND"
    if msg == "USED" and err_code == 40005:
        return "USED"
    if msg == "TIMEOUT RETRY" and err_code == 40004:
        return "TIMEOUT RETRY"
    if msg == "TOO FREQUENT" and err_code == 40019:
        return "TOO FREQUENT"
    if msg == "USER INFO ERROR" and err_code == 40020:
        return "USER INFO ERROR"
    if err_code == 40001 and "not exist" in msg.lower():
        return "ROLE NOT EXIST"
    if msg == "STOVE_LV ERROR" and err_code == 40006:
        return "STOVE_LV ERROR"
    if msg == "RECHARGE_MONEY ERROR" and err_code == 40017:
        return "RECHARGE_MONEY ERROR"
    if msg == "RECHARGE_MONEY_VIP ERROR" and err_code == 40018:
        return "RECHARGE_MONEY_VIP ERROR"
    if "sign error" in msg.lower():
        return "SIGN ERROR"
    if msg == "NOT LOGIN":
        return "NOT LOGIN"
    return msg


def redeem_once(fid, kid, cdk):
    """One signed redemption POST for `fid` in state `kid`; returns a status key."""
    payload = encode_data({
        "fid": fid,
        "cdk": cdk,
        "kid": str(kid),
        "time": str(int(time.time())),
    })
    response = make_request(REDEEM_URL, payload)
    if response is None:
        return TRANSPORT_FAILURE

    try:
        return classify(response.json())
    except ValueError:
        log(f"{fid} - Redemption response was not valid JSON: {response.text[:200]}", level='error')
        return "Redemption response invalid JSON"


def redeem_gift_code(fid, kid, cdk, position, total, retry_queue):
    """Redeem for one player, retrying on transient statuses. Returns (status, retry_queue)."""
    SESSION.headers.update(get_headers())   # one consistent browser identity per player
    log(f"Processing S{kid}-{fid} [{position}/{total}] for code: {cdk}")

    status = "Processing error"
    for attempt in range(MAX_FID_ATTEMPTS):
        status = redeem_once(fid, kid, cdk)

        if status == "TOO FREQUENT":
            counters["rate_limited"] += 1
            cooldowns[fid] = cooldowns.get(fid, 0) + 1
            if cooldowns[fid] <= MAX_COOLDOWNS:
                # Per-FID rate limit: never rapid-retry, park the player and come back later.
                retry_queue[fid] = time.time() + TOO_FREQUENT_SLEEP
                log(f"{fid} - Rate limited, retrying in ~{TOO_FREQUENT_SLEEP}s", level='warn')
                return status, retry_queue
            log(f"{fid} - Still rate limited after {MAX_COOLDOWNS} cooldowns. Giving up on this player.",
                level='error')

        if status == "TIMEOUT RETRY":
            if attempt < MAX_FID_ATTEMPTS - 1:
                log(f"{fid} - [Attempt {attempt+1}/{MAX_FID_ATTEMPTS}] {status}. Retrying...", level='warn')
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            log(f"{fid} - Max attempts reached after {status}.", level='error')
        break

    friendly = RESULT_MESSAGES.get(status, status)
    if status in SUCCESS_STATUSES:
        level = 'success'
    elif status == "RECEIVED":
        level = 'dim'
    elif status in FATAL_STATUSES:
        level = 'warn'
    else:
        level = 'error'
    log(f"{fid} - Result: {friendly}", level=level)

    return status, retry_queue


def parse_csv_row(row):
    """One CSV row -> [(fid, kid or None), ...].

    A two-field row whose second field is small enough to be a state is a
    `fid,kid` pair; anything else is a plain list of player IDs.
    """
    fields = [item.strip() for item in row if item.strip()]
    if not fields or fields[0].startswith("#"):
        return []

    if len(fields) == 2 and all(f.isdigit() for f in fields) and int(fields[1]) <= MAX_STATE_ID:
        return [(fields[0], fields[1])]

    return [(f, None) for f in fields if f.isdigit()]


def read_players_from_csv(file_path):
    """Read (fid, kid) pairs from a CSV; kid is None when the row carries only an ID."""
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin-1', 'gbk']

    for encoding in encodings_to_try:
        try:
            with open(file_path, mode="r", newline="", encoding=encoding) as file:
                content = file.read()
        except FileNotFoundError:
            raise
        except UnicodeDecodeError:
            continue
        except Exception as e:
            log(f"Error reading {os.path.basename(file_path)} with encoding {encoding}: {e}", level='error')
            return []

        if not content.strip():
            log(f"Warning: '{os.path.basename(file_path)}' appears to be empty.", level='warn')
            return []

        players = []
        ignored = 0
        for row in csv.reader(content.splitlines()):
            parsed = parse_csv_row(row)
            players.extend(parsed)
            if row and not parsed and row[0].strip() and not row[0].strip().startswith("#"):
                ignored += 1

        with_state = sum(1 for _, kid in players if kid)
        log(f"Read {len(players)} player IDs from {os.path.basename(file_path)} "
            f"(encoding: {encoding}, {with_state} with a state)")
        if ignored:
            log(f"Ignored {ignored} non-numeric or malformed rows in {os.path.basename(file_path)}.", level='warn')
        return players

    log(f"Error: could not decode {os.path.basename(file_path)} with any of: {encodings_to_try}", level='error')
    return []


def collect_csv_files(csv_input_spec):
    """Resolve the --csv argument into a sorted list of CSV paths.

    An explicit --csv that does not resolve is a hard error - falling back to
    whatever else is lying around would redeem for a list you never asked for.
    """
    if csv_input_spec is None:
        log("No --csv given. Using every *.csv in the current directory.")
        return sorted(glob(os.path.join(".", "*.csv")))

    if os.path.isdir(csv_input_spec):
        log(f"Searching for CSV files in directory: {csv_input_spec}")
        return sorted(glob(os.path.join(csv_input_spec, "*.csv")))
    if "*" in os.path.basename(csv_input_spec) or "?" in os.path.basename(csv_input_spec):
        log(f"Searching for CSV files matching pattern: {csv_input_spec}")
        return sorted(glob(csv_input_spec))
    if os.path.isfile(csv_input_spec):
        log(f"Using specified CSV file: {csv_input_spec}")
        return [csv_input_spec]

    log(f"Error: '{csv_input_spec}' does not exist. Check the path - the script will not "
        f"fall back to other CSV files.", level='error')
    sys.exit(1)


def load_players(csv_files, default_state):
    """Merge every CSV into a deduplicated, state-resolved [(fid, kid), ...]."""
    raw = []
    for csv_file in csv_files:
        try:
            raw.extend(read_players_from_csv(csv_file))
        except FileNotFoundError:
            log(f"Error: CSV file '{os.path.basename(csv_file)}' not found.", level='error')
        except Exception as e:
            log(f"Error processing {os.path.basename(csv_file)}: {e}", level='error')

    # Last state wins, so a per-row state in a later file overrides an earlier bare ID.
    states = {}
    for fid, kid in raw:
        if kid or fid not in states:
            states[fid] = kid or states.get(fid)

    missing_state = [fid for fid, kid in states.items() if not kid]
    if missing_state and not default_state:
        log(f"Error: {len(missing_state)} player ID(s) have no state and --state was not given. "
            f"The API rejects any redemption without the player's correct state.", level='error')
        log("Fix this by passing --state <id>, or by writing the CSV as 'fid,kid' per line.", level='error')
        sys.exit(1)

    players = [(fid, states[fid] or default_state) for fid in sorted(states, key=int)]
    duplicates = len(raw) - len(players)
    if duplicates > 0:
        log(f"Removed {duplicates} duplicate entries.")
    if missing_state:
        log(f"{len(missing_state)} player ID(s) had no state in the CSV; using --state {default_state}.")
    return players


def print_summary(code, players, processed_fids):
    execution_time = str(timedelta(seconds=int(time.time() - script_start_time)))

    log("\n" + "=" * 25 + " Redemption Summary " + "=" * 25)
    log(f"Code Redeemed: {code}")
    log(f"Total Unique Player IDs Found: {len(players)}")
    log(f"Total Player IDs Processed: {len(processed_fids)}")

    remaining = len(players) - len(processed_fids)
    if remaining > 0:
        log(f"Player IDs Not Processed (in queue or script stopped early): {remaining}")

    log("\n--- Redemption Results ---")
    log(f"Successfully redeemed: {counters['success']}")
    log(f"Already redeemed: {counters['already_redeemed']}")
    log(f"Wrong state: {counters['wrong_state']}")
    log(f"Other Errors/Failures: {counters['errors']}")
    log(f"Rate Limit Events: {counters['rate_limited']}")
    log(f"Total API Requests: {counters['requests']}")

    if wrong_state_fids:
        log("\n--- Wrong State (fix the state in your CSV) ---")
        for fid, kid in sorted(wrong_state_fids.items(), key=lambda item: int(item[0])):
            log(f"  {fid}: state {kid} was rejected")

    if error_details:
        log("\n--- Error Details (Player ID: Last Error) ---")
        sorted_errors = sorted(error_details.items(), key=lambda item: int(item[0]))
        for i, (fid, msg) in enumerate(sorted_errors):
            if i >= 20:
                log(f"  ... (and {len(sorted_errors) - 20} more errors)")
                break
            log(f"  {fid}: {msg}")

    log(f"\nTotal execution time: {execution_time}")
    log("=" * 70)


def record_result(fid, kid, status):
    """Update the counters and error tables for one final (non-retried) result."""
    if status in SUCCESS_STATUSES:
        counters["success"] += 1
    elif status == "RECEIVED":
        counters["already_redeemed"] += 1
    elif status == "USER INFO ERROR":
        counters["wrong_state"] += 1
        wrong_state_fids[fid] = kid
    elif status not in FATAL_STATUSES:
        counters["errors"] += 1
        error_details[fid] = RESULT_MESSAGES.get(status, status)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Redeem a Whiteout Survival gift code for player IDs listed in CSV file(s).")
    parser.add_argument('--code', type=str, required=True, help='The gift code to redeem (REQUIRED)')
    parser.add_argument('--csv', type=str, help='Path to a CSV file, a directory, or a *.csv pattern')
    parser.add_argument('--state', '--kid', dest='state', type=int,
                        help='State (kingdom) ID for players whose CSV row does not carry one')
    parser.add_argument('--delay', type=float, default=DELAY,
                        help=f'Seconds to wait between players (default: {DELAY})')
    return parser.parse_args()


def main():
    args = parse_args()
    args.delay = max(0.0, args.delay)

    log(f"\n=== Starting redemption script at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    log(f"Gift Code: {args.code}")
    if args.state is not None:
        log(f"Default State: {args.state}")

    csv_files = collect_csv_files(args.csv)
    if not csv_files:
        log("Error: No CSV files found. Specify a valid CSV file, directory, or pattern with --csv.", level='error')
        sys.exit(1)
    log(f"Found {len(csv_files)} CSV file(s): {', '.join(os.path.basename(f) for f in csv_files)}")

    players = load_players(csv_files, str(args.state) if args.state is not None else None)
    if not players:
        log("Error: No valid player IDs loaded from any CSV file. Exiting.", level='error')
        sys.exit(1)
    log(f"Total unique player IDs to process: {len(players)}")

    states = {kid for _, kid in players}
    positions = {fid: i + 1 for i, (fid, _) in enumerate(players)}
    retry_queue = {}
    processed_fids = set()
    stop_processing = False
    consecutive_failures = 0

    try:
        while len(processed_fids) < len(players) and not stop_processing:
            now = time.time()
            ready = [(fid, kid) for fid, kid in players
                     if fid not in processed_fids and retry_queue.get(fid, 0) <= now]
            cooling = len(players) - len(processed_fids) - len(ready)

            if not ready:
                if not cooling:
                    log("Warning: no players ready and none in cooldown, but not all are processed.", level='warn')
                    break
                next_retry = min(retry_queue[fid] for fid, _ in players
                                 if fid not in processed_fids and fid in retry_queue)
                wait = max(1, min(30, next_retry - now + 1))
                log(f"{cooling} player ID(s) in cooldown. Waiting {int(wait)}s... "
                    f"Progress: {len(processed_fids)}/{len(players)}")
                time.sleep(wait)
                continue

            log(f"\n--- Starting processing cycle. Ready player IDs: {len(ready)} ---")
            for fid, kid in ready:
                status, retry_queue = redeem_gift_code(
                    fid, kid, args.code, positions[fid], len(players), retry_queue)

                if retry_queue.get(fid, 0) > time.time():
                    continue

                processed_fids.add(fid)
                record_result(fid, kid, status)

                if status in FATAL_STATUSES:
                    log(f"\n *** {RESULT_MESSAGES[status]}! Stopping further processing. ***", level='warn')
                    stop_processing = True
                    break

                # A dead connection would otherwise burn the retry budget on every remaining player.
                consecutive_failures = consecutive_failures + 1 if status == TRANSPORT_FAILURE else 0
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log(f"\n *** {MAX_CONSECUTIVE_FAILURES} players in a row could not reach the API. "
                        f"Check your internet connection. Stopping. ***", level='error')
                    stop_processing = True
                    break

                time.sleep(args.delay + random.uniform(0, 0.5))

            log(f"--- Cycle finished. Total processed: {len(processed_fids)}/{len(players)} ---")
    except KeyboardInterrupt:
        log("\nInterrupted. Redemptions already made are done and logged; "
            "re-running is safe and will report them as already redeemed.", level='warn')

    if not stop_processing and len(processed_fids) == len(players):
        log(f"\nAll {len(processed_fids)} player IDs processed.")

    if counters["wrong_state"] and len(states) == 1:
        log(f"Every player was redeemed in state {next(iter(states))}. "
            f"If many were rejected, check that this is the right state.", level='warn')

    print_summary(args.code, players, processed_fids)


if __name__ == "__main__":
    main()
    sys.exit(0)

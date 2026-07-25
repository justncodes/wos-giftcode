# Whiteout Survival Gift Code Redemption Script

Python script that automates the process of redeeming gift codes in the game **Whiteout Survival**. It reads a list of Player IDs and State IDs from one or more `.csv` files and sends signed requests to the game's giftcode redemption API to redeem the specified gift code for each player.

It was built with the goal of providing an alternative to [the Discord Bot](https://github.com/whiteout-project/bot) that I'm also helping develop. Setting up the bot and hosting it can take some effort to do, while this script can be run with one simple command. It can also be seen as providing a kind of backup option when your Discord bot is down and redemption is failing. The bot is awesome though - check it out if you haven't already.

---

## Prerequisites

1.  **Python 3.9+**: Download and install Python from [python.org](https://www.python.org/). Ensure Python is added to your system's PATH during installation.
2.  **Required libraries**:
    ```bash
    pip install requests colorama
    ```
    `colorama` is optional - without it the script runs fine, just without colored console output.

---

## Setup

1.  **Get the script**:
    *   Clone the repository: `git clone https://github.com/justncodes/wos-giftcode.git`
    *   Or download `redeem_codes.py` directly from the repository.
2.  **Install dependencies**: `pip install requests colorama`. Use a [virtual environment](https://docs.python.org/3/library/venv.html) (`venv`) to keep things clean.
3.  **Prepare the CSV file(s)**: see **Supplying the state** under Usage.
4.  **Run the script**: see **Usage**.

---

## Usage

```bash
python redeem_codes.py --code <gift_code> [--csv <path_or_pattern>] [--state <id>] [--delay <seconds>]
```

### Arguments

-   `--code`: **Required**. The gift code you want to redeem (e.g., `WOS2025`).
-   `--csv`: Specifies the player ID source. Defaults to the current directory if not provided. Can be:
    *   A path to a single `.csv` file.
    *   A path to a folder/directory containing `.csv` files.
    *   The pattern `*.csv` (quote it if your shell needs it) or `.` to process every `.csv` file in the current directory.

    A `--csv` path that doesn't exist stops the run. Omit `--csv` entirely to use every `*.csv` in the current directory.
-   `--state` (alias `--kid`): State/kingdom ID used for any player whose CSV row does not carry its own. Required unless every row is a `fid,kid` pair.
-   `--delay`: Seconds to wait between players. Defaults to `1`. Raise it if you see rate limiting.

### Supplying the state

The API checks the player ID *and* their state together, and rejects the pair with `USER INFO ERROR` (err_code `40020`) before it looks at the code. The script reports that as "Wrong state for this player ID". There are two ways to supply it, and they can be mixed.

**One state for everyone (`--state`)** - the normal case for a single alliance. The CSV holds one ID per line, or comma-separated IDs:

```csv
124238609
51730031
83378813
```

```bash
python redeem_codes.py --code ILoveWOS --csv alliance.csv --state 340
```

**A state per player (`fid,kid` in the CSV)** - for a list that spans states, e.g. after members have transferred. Lines starting with `#` are ignored:

```csv
# fid,kid
124238609,340
51730031,340
83378813,1121
```

```bash
python redeem_codes.py --code ILoveWOS --csv alliance.csv
```

Rows carrying only an ID fall back to `--state`, so both forms can live in one file. Given this CSV, `124238609` is redeemed in state 1121 and the other two in state 340:

```csv
124238609,1121
51730031
83378813
```

```bash
python redeem_codes.py --code ILoveWOS --csv mixed.csv --state 340
```

A row of exactly two numbers is read as `fid,kid` when the second number is 6 digits or shorter (states are small, player IDs are not). Every other row is read as a plain list of player IDs. If any player ends up without a state, the script stops before sending anything.

### Examples

*   **Redeem for every `.csv` in the current folder, all players in state 340:**
    ```bash
    python redeem_codes.py --code ILoveWOS --state 340
    ```

*   **Redeem for a specific file:**
    ```bash
    python redeem_codes.py --code ILoveWOS --csv ids.csv --state 340
    ```

*   **Redeem for a CSV that already carries per-player states:**
    ```bash
    python redeem_codes.py --code ILoveWOS --csv alliance_with_states.csv
    ```

*   **Go slower to stay well clear of rate limits:**
    ```bash
    python redeem_codes.py --code ILoveWOS --csv ids.csv --state 340 --delay 3
    ```

---

## Features

-   **Flexible CSV import**: Reads player IDs from `.csv` files, one per line or comma-separated, with an optional per-player state.
-   **Rate limit handling**: `TOO FREQUENT` (err_code `40019`) is a per-player limit. The script parks that player in a retry queue for 60 seconds and carries on with everyone else, coming back to them up to 3 times.
-   **Retry logic**: Automatically retries when the server asks for one (`TIMEOUT RETRY`) or returns a transient HTTP error (429/502/503/504). The run aborts if 10 players in a row can't reach the API at all.
-   **Early exit on a dead code**: Stops the whole run on `TIME ERROR` (expired), `CDK NOT FOUND` (bad code) or `USED` (claim limit), since none of those depend on the player.
-   **Safe to interrupt**: Ctrl+C prints the summary before exiting, and re-running reports anything already redeemed as such.
-   **Wrong-state reporting**: Every player rejected with `USER INFO ERROR` is listed at the end with the state that was rejected, so you know exactly what to fix in your CSV.
-   **Browser header rotation**: Randomizes browser, version and platform headers on every request to avoid bot detection.
-   **Verbose logging**: Timestamped, colored console output (with `colorama`), mirrored to `redeemed_codes.txt`.
-   **Summary report**: Successes, already-redeemed, wrong-state, other errors, rate limit events and total requests.

---

## Output

### Sample Run

```plaintext
(Colorama adds colors in the actual terminal)
2026-03-04 10:30:01 - === Starting redemption script at 2026-03-04 10:30:01 ===
2026-03-04 10:30:01 - Gift Code: WOSNEWYEAR
2026-03-04 10:30:01 - Default State: 340
2026-03-04 10:30:01 - Using specified CSV file: alliance.csv
2026-03-04 10:30:01 - Found 1 CSV file(s): alliance.csv
2026-03-04 10:30:01 - Read 150 player IDs from alliance.csv (encoding: utf-8-sig, 12 with a state)
2026-03-04 10:30:01 - 138 player ID(s) had no state in the CSV; using --state 340.
2026-03-04 10:30:01 - Total unique player IDs to process: 150
2026-03-04 10:30:01 -
--- Starting processing cycle. Ready player IDs: 150 ---
2026-03-04 10:30:01 - Processing S340-12345678 [1/150] for code: WOSNEWYEAR
2026-03-04 10:30:02 - 12345678 - Result: Already redeemed
2026-03-04 10:30:03 - Processing S340-87654321 [2/150] for code: WOSNEWYEAR
2026-03-04 10:30:04 - 87654321 - Result: Successfully redeemed
...
2026-03-04 10:34:58 - --- Cycle finished. Total processed: 150/150 ---
2026-03-04 10:34:58 -
All 150 player IDs processed.
2026-03-04 10:34:58 -
========================= Redemption Summary =========================
2026-03-04 10:34:58 - Code Redeemed: WOSNEWYEAR
2026-03-04 10:34:58 - Total Unique Player IDs Found: 150
2026-03-04 10:34:58 - Total Player IDs Processed: 150
2026-03-04 10:34:58 -
--- Redemption Results ---
2026-03-04 10:34:58 - Successfully redeemed: 95
2026-03-04 10:34:58 - Already redeemed: 52
2026-03-04 10:34:58 - Wrong state: 2
2026-03-04 10:34:58 - Other Errors/Failures: 1
2026-03-04 10:34:58 - Rate Limit Events: 3
2026-03-04 10:34:58 - Total API Requests: 156
2026-03-04 10:34:58 -
--- Wrong State (fix the state in your CSV) ---
2026-03-04 10:34:58 -   11111111: state 340 was rejected
2026-03-04 10:34:58 -   22222222: state 340 was rejected
2026-03-04 10:34:58 -
--- Error Details (Player ID: Last Error) ---
2026-03-04 10:34:58 -   33333333: Furnace level too low for this code
2026-03-04 10:34:58 -
Total execution time: 0:04:57
======================================================================
```

### Logging

All console output (without color codes) is appended to `redeemed_codes.txt` in the script folder.

---

## Troubleshooting

1.  **`pip` command not found**: Ensure Python is installed correctly and in PATH.
2.  **ModuleNotFoundError**: Run `pip install requests colorama` in the environment you're actually using.
3.  **"have no state and --state was not given"**: The API needs a state for every player. Pass `--state <id>`, or write the CSV as `fid,kid`.
4.  **"Wrong state for this player ID" for everyone**: The state you passed is wrong for that list. Check the state number in-game.
5.  **"Wrong state for this player ID" for a few players**: Those members have transferred to another state. Give them their own `fid,kid` rows.
6.  **CSV File Not Found**: Verify the `--csv` path.
7.  **Permission denied (log file)**: Check write permissions in the script folder.
8.  **Code expired / claim limit reached / code not found**: The script stops the run - the code is dead or mistyped, so no player in the list can receive it.
9.  **Lots of "Rate limited"**: The limit is per player ID, not per IP, so this usually means retries piling up on the same members. Raising `--delay` gives the queue more room.

---

## Changelog

### v5.0.0 (Current)

-   The game's API requires the player's state (`kid`) on every redemption. Added `--state` and support for `fid,kid` rows in the CSV.
-   Removed all CAPTCHA solving - the `/api/captcha` endpoint no longer exists. Dropped `--ocr-method`, `--use-gpu` and `--save-images`, the ONNX/ddddocr/EasyOCR/CaptchaCracker dependencies, and the bundled `model/` files.
-   Removed the login step (`/api/player` no longer exists). Player nicknames are unavailable, so output identifies players by state and ID.
-   `TOO FREQUENT` (40019) is handled as the per-player limit it is: the player is parked for 60s while the rest of the list continues.
-   Runs stop early on `CDK NOT FOUND` as well as `TIME ERROR` and `USED`.
-   Wrong-state rejections (40020) are collected and listed separately in the summary.
-   A `--csv` path that doesn't exist stops the run instead of falling back to every other `.csv` in the folder.
-   Ctrl+C stops cleanly and still prints the summary of what was redeemed.
-   The run aborts if 10 players in a row can't reach the API.
-   Dependencies reduced to `requests` (and optionally `colorama`).

### v4.0.0
-   Added custom-trained ONNX captcha model as the new default OCR method (~98% accuracy)
-   New OCR priority: `onnx` > `ddddocr` > `captchacracker` > `easyocr`
-   ONNX method requires only `onnxruntime`, `numpy`, and `pillow` — no `opencv-python` needed
-   Improved browser header spoofing with randomized Chrome versions and proper `sec-*` headers
-   Model files included in `model/` directory (`captcha_model.onnx`, `captcha_model_metadata.json`)

### v3.0.5
-   Uploaded a better Captchacracker model (trained on ~10k validated captchas)
-   Reduced the character set to check for since the Gift API is case-insensitive

### v3.0.0 
-   Refactored, streamlined OCR calling logic, updated summary statistics.
-   Added support for `ddddocr` (default/recommended) and `captchacracker` alongside `easyocr`. Select via `--ocr-method`.
-   Replaced `--all-images` with `--save-images [0|1|2|3]` for more control over saving successful/failed captchas to `captcha_images` folder.
-   Successfully validated codes will be saved as `<code>.png` and unsuccessful ones as `FAIL_<fid>_<timestamp>.png` depending on `--save-images` settings.
-   Added colored console output (requires `colorama`), consistent `Nickname (FID)` prefix, specific log levels.

### v2.4.5
-   Added support for discrete GPUs with device selection via `--use-gpu` parameter
-   Improved GPU error handling with graceful fallback to CPU

### v2.4.0
-   Added improved CAPTCHA preprocessing with multiple image enhancement techniques
-   Added comprehensive captcha statistics in summary output
-   Added progress tracking with current/total indicators
-   Added detailed error reporting by player ID
-   Added execution time tracking and reporting
-   Added final unprocessed ID check to guarantee all IDs are eventually processed
-   Improved retry queue handling for rate-limited IDs
-   Added option to disable captcha image saving to conserve disk space
-   Fixed issues with counting and reporting

### v2.3.0
-   Integrated OCR (EasyOCR) to automatically read and submit CAPTCHA codes required by the redemption API.
-   Added `easyocr`, `opencv-python`, `numpy`, and PyTorch (`torch`, `torchvision`, `torchaudio`) for OCR.
-   Saves attempted CAPTCHA images with OCR results in the filename to a subfolder (`failed_captchas`) for debugging.
-   Enhanced retry logic specifically for CAPTCHA-related errors (`CAPTCHA CHECK ERROR`, `Sign Error`, `CAPTCHA CHECK TOO FREQUENT`).

### v2.2.0
-   Added support for reading comma-separated player IDs within CSV files.
-   Improved CSV file path handling in `--csv` argument (folder path, `*.csv` pattern).
-   Enhanced logging detail and error categorization.

### v2.1.0
-   Added support for processing all .csv files in a folder or the script's directory using `*.csv`.
-   Improved error handling for missing or invalid .csv files.

### v2.0.0
-   Added retry logic for failed requests (e.g., `TIMEOUT RETRY`).
-   Display player nicknames during processing.
-   Added Unicode support for special characters and foreign alphabets.
-   Added a summary report of redemptions at the end.
-   Improved error handling and logging.

### v1.0.0 (Initial Release)
-   Basic functionality: CSV import (newline separated), command-line args, API requests.
-   Initial error handling and rate limiting.

---

## Credits

-   **Author**: justncodes (\[SIR\] Yolo on #340) - [Repository](https://github.com/justncodes/wos-giftcode)

---

## Support

If you encounter any issues or have questions, feel free to open an issue and include relevant logs and the script version.

---

## License

This project is licensed under the GPLv3 License. See the `LICENSE` file for details.

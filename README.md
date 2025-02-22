# Whiteout Survival Gift Code Redemption Script

Python script that automates the process of redeeming gift codes in the game **Whiteout Survival**. It reads a list of Player IDs from a `.csv` file and sends requests to the game's giftcode redemption API to redeem the specified gift code for each player.

---

## Prerequisites

1. **Python 3.x**: Download and install Python from [python.org](https://www.python.org/).
2. **Required Libraries**: Install the required Python libraries using `pip`:
   ```bash
   pip install requests
   ```
   Note the pip command should be available automatically after installing Python.
   
---

## Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/justncodes/wos-giftcode.git
   cd wos-giftcode
   ```
   ...or just download the [redeem_codes.py](https://github.com/justncodes/wos-giftcode/blob/main/redeem_codes.py) file directly.
   
2. **Prepare the CSV File**:
   - Create a `.csv` file (e.g., `player_ids.csv`), ideally in the same folder as the script, with one player ID per row.
   - You can use your favorite notepad and just save the text file with .csv extension.
   - Example `player_ids.csv`:
     ```csv
     57845354
     98765432
     12345678
     ```

---

## Usage

Run the script from the command line with the following arguments:

```bash
python redeem_codes.py --csv <path_to_csv> --code <gift_code>
```

### Arguments

- `--csv`: Name of the `.csv` file containing player IDs. Add the path to it if it isn't in the same folder as the script.
- `--code`: The gift code to redeem.

### Example

```bash
python redeem_codes.py --csv player_ids.csv --code ILoveU
```

---

## Output

### Successful Run

```plaintext
=== Starting redemption for gift code: woshjm25 at 2025-02-21 19:31:04 ===
2025-02-21 19:31:04 - Loaded 95 player IDs from SIR.csv
2025-02-21 19:31:05 - Processing منتظر (52383226)
2025-02-21 19:31:06 - Result: Successfully redeemed
2025-02-21 19:31:07 - Processing a_toofargone (51728185)
2025-02-21 19:31:08 - Result: Successfully redeemed
2025-02-21 19:31:09 - Processing Aarav Rahul (50646449)
2025-02-21 19:31:10 - Result: Already redeemed
```

---

## How It Works

1. **CSV Import**:
   - The script reads player IDs from the specified `.csv` file.

2. **Sign Generation**:
   - Uses a secret key (`WOS_ENCRYPT_KEY`) to generate the `sign` parameter for each request.

3. **API Requests**:
   - Sends a login request to validate the player ID.
   - Sends a redemption request to redeem the gift code.

4. **Verbose Logging**:
   - Logs output and any errors that occur to redeemed_codes.txt log file.
   - Retries up to 3 times if the initial attempt fails, unless the code expired.

5. **Rate Limiting**:
   - Adds a 1-second delay between requests to avoid being blocked.

---

## Troubleshooting

### Common Issues

1. **CSV File Not Found**:
   - Ensure the `.csv` file exists at the specified path.
   - Double-check the file name and extension.

2. **Invalid Gift Code**:
   - Verify that the gift code is correct and has not expired.

3. **API Rate Limiting**:
   - If the script is blocked, increase the delay between requests (eg. `DELAY = 2`).

---

## Future Enhancements

- **GUI**: Create a simple graphical interface for non-technical users.

---

## Changelog

### v2.0.0 (Current)
- Added retry functionality if redemption fails.
- Added logging to a redeemed_codes.txt log file.
- Included player names in the log output.
- Additional error handling.

### v1.0.0 (Initial Release)
- Added support for CSV import and command-line arguments.
- Implemented API request logic with sign generation.
- Added error handling and rate limiting.

---

## Credits

- **Author**: justncodes (\[SIR\] Yolo on #340)
- **Repository**: [wos-giftcode](https://github.com/justncodes/wos-giftcode)

---

## Support

If you encounter any issues or have questions, feel free to open an issue on the [GitHub repository](https://github.com/your-username/gift-code-redemption/issues).

---

## License

This project is licensed under the GPLv3 License. See the [LICENSE](LICENSE) file for details.

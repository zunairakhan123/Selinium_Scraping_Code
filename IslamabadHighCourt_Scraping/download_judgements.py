import json
import os
import requests
import sys
import re
import time

# --- Configuration ---
BASE_URL = "https://ihc.gov.pk"
INPUT_FILE = "filtered_judgements2.json" 
DOWNLOAD_DIR = "downloaded_judgements"
LOG_FILE = "failed_downloads.log"

# [NEW] This header makes the server think we are a real browser
# We are "referring" from the main search/viewer page domain.
REQUEST_HEADERS = {
    'Referer': 'https://mis.ihc.gov.pk/'
}
# ---------------------

def sanitize_filename(filename):
    """
    Sanitizes a string to be a safe filename.
    Removes or replaces characters that are problematic in file systems.
    """
    safe_name = re.sub(r'[^\w\s.-]', '', filename)
    safe_name = re.sub(r'\s+', '_', safe_name)
    return safe_name[:200]

def download_files():
    """
    Reads the filtered JSON file and downloads the PDF for each judgement.
    Logs failed downloads to a separate file.
    """
    if not os.path.exists(DOWNLOAD_DIR):
        try:
            os.makedirs(DOWNLOAD_DIR)
            print(f"Created directory: '{DOWNLOAD_DIR}'")
        except OSError as e:
            print(f"Error: Could not create directory '{DOWNLOAD_DIR}'. {e}")
            return

    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            judgements = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print(f"Please make sure 'format_json.py' ran successfully.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

    if not judgements:
        print("No judgements found in the input file. Nothing to download.")
        return

    print(f"Found {len(judgements)} judgements to download...")

    session = requests.Session() 
    # [NEW] Set the header for all requests in this session
    session.headers.update(REQUEST_HEADERS)

    download_count = 0
    fail_count = 0
    skip_count = 0
    
    with open(LOG_FILE, 'a', encoding='utf-8') as log_f:
        log_f.write(f"\n--- Download Session Started: {time.ctime()} ---\n")

        for i, item in enumerate(judgements):
            attachment_path = item.get('ATTACHMENTS')
            case_no = item.get('CASENO', 'UnknownCase')
            o_id = item.get('O_ID', 'UnknownID')

            if not attachment_path or not attachment_path.startswith('/'):
                print(f"Skipping ({i+1}/{len(judgements)}): Invalid or missing 'ATTACHMENTS' field for ID {o_id}.")
                log_f.write(f"INVALID_PATH_SKIPPED: ID {o_id}, Case: {case_no}, Path: {attachment_path}\n")
                fail_count += 1
                continue

            full_url = BASE_URL + attachment_path
            safe_case_no = sanitize_filename(case_no)
            filename = f"{safe_case_no}_{o_id}.pdf"
            output_filepath = os.path.join(DOWNLOAD_DIR, filename)

            if os.path.exists(output_filepath):
                print(f"Skipping ({i+1}/{len(judgements)}): File already exists: {filename}")
                skip_count += 1
                continue

            print(f"Downloading ({i+1}/{len(judgements)}): {filename}...")
            
            try:
                # [MODIFIED] The session.get() call now automatically includes the headers
                response = session.get(full_url, timeout=30) 
                
                response.raise_for_status() 

                with open(output_filepath, 'wb') as f:
                    f.write(response.content)
                
                download_count += 1
                
                time.sleep(0.25) 

            except requests.exceptions.HTTPError as e:
                # [NEW] Check if it's a 404 error again
                if e.response.status_code == 404:
                     print(f"  -> FAILED (404 Not Found): The URL itself is still bad, even with the header.")
                     log_f.write(f"HTTP_404_ERROR: {full_url}\n")
                else:
                    print(f"  -> FAILED (HTTP Error): {e}")
                    log_f.write(f"HTTP_ERROR: {full_url} (Error: {e})\n")
                fail_count += 1
            except requests.exceptions.ConnectionError as e:
                print(f"  -> FAILED (Connection Error): {e}")
                log_f.write(f"CONNECTION_ERROR: {full_url} (Error: {e})\n")
                fail_count += 1
            except requests.exceptions.Timeout:
                print(f"  -> FAILED (Timeout)")
                log_f.write(f"TIMEOUT_ERROR: {full_url}\n")
                fail_count += 1
            except Exception as e:
                print(f"  -> FAILED (Unexpected Error): {e}")
                log_f.write(f"UNEXPECTED_ERROR: {full_url} (Error: {e})\n")
                fail_count += 1

    print("\n--- Download Complete ---")
    print(f"Successfully downloaded: {download_count}")
    print(f"Already existed (skipped): {skip_count}")
    print(f"Failed or skipped: {fail_count}")
    print(f"Files are located in the '{DOWNLOAD_DIR}' directory.")
    if fail_count > 0:
        print(f"A list of all failed URLs has been saved to '{LOG_FILE}'.")

if __name__ == "__main__":
    download_files()


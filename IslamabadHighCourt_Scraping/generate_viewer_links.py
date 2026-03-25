import json
import os
import urllib.parse

# --- Configuration ---
INPUT_FILE = "filtered_judgements2.json"
OUTPUT_FILE = "links_to_download_manually.txt"
VIEWER_PAGE_URL = "https://mis.ihc.gov.pk/frmRdJgmnt.aspx"
# ---------------------

def create_complete_links():
    """
    Reads the full JSON file and creates a text file of
    direct links to the .aspx viewer page, including all
    required URL parameters (cseNo, cseTle, jgs, jgmnt).
    """
    
    # 1. Find the input JSON file
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            judgements = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print(f"Please make sure 'format_json.py' ran successfully and created this file.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
        return

    if not judgements:
        print("No judgements found in the input file. Nothing to generate.")
        return

    print(f"Reading {len(judgements)} judgements from '{INPUT_FILE}'...")
    links_created = 0

    # 2. Create the new output file
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(f"--- Manual Download Links ({len(judgements)} files) ---\n")
            f.write("--- Generated from {INPUT_FILE} ---\n\n")
            
            for item in judgements:
                # 3. Get all the required data from the JSON
                path = item.get('ATTACHMENTS')
                case_no = item.get('CASENO', 'Unknown Case')
                title = item.get('TITLE', 'Unknown Title')
                # Use AUTHOR_JUDGES first, fall back to BENCHNAME if it's missing
                judge = item.get('AUTHOR_JUDGES') or item.get('BENCHNAME', 'Unknown Judge')

                if not path:
                    print(f"Skipping item with O_ID {item.get('O_ID')}: Missing 'ATTACHMENTS' path.")
                    continue

                # 4. URL-encode the parameters (like replacing spaces with %20)
                # This is critical for the server to read them correctly.
                enc_case_no = urllib.parse.quote_plus(case_no)
                enc_title = urllib.parse.quote_plus(title)
                enc_judge = urllib.parse.quote_plus(judge)
                
                # As we saw from your working example, the 'jgmnt' path itself
                # does not get encoded, so we use it directly.
                jgmnt_path = path

                # 5. Build the complete, correct URL
                final_link = (
                    f"{VIEWER_PAGE_URL}?"
                    f"cseNo={enc_case_no}"
                    f"&cseTle={enc_title}"
                    f"&jgs={enc_judge}"
                    f"&jgmnt={jgmnt_path}\n"
                )
                
                f.write(final_link)
                links_created += 1
                
        print(f"\nSuccess! A new file has been created:")
        print(f"-> {OUTPUT_FILE}")
        print(f"It now contains {links_created} complete links.")
        print(f"\nOpen this file. These links *should* work now.")
        
    except Exception as e:
        print(f"Error writing to output file: {e}")

if __name__ == "__main__":
    create_complete_links()

import json
from datetime import datetime
import sys

# --- Configuration ---
INPUT_FILE = "formatted_response.json"
OUTPUT_FILE = "filtered_judgements2.json"
START_DATE = datetime(2024, 11, 1)
END_DATE = datetime(2025, 10, 31) # Today's date
# ---------------------

def filter_judgements():
    """
    Reads the input JSON file, filters judgements by DDATE,
    and saves them to a new JSON file.
    """
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print("Please make sure the script is in the same directory as your JSON file.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}")
        return

    print(f"Loaded {len(data)} judgements from '{INPUT_FILE}'.")
    
    filtered_judgements = []
    parse_errors = 0

    for item in data:
        date_str = item.get('DDATE')
        if not date_str:
            continue

        try:
            # Parse the date string (e.g., "09-OCT-2025")
            judgement_date = datetime.strptime(date_str, '%d-%b-%Y')

            # Check if the date is within the desired range
            if START_DATE <= judgement_date <= END_DATE:
                filtered_judgements.append(item)

        except ValueError:
            # Handle cases where the date format is unexpected
            parse_errors += 1
            # print(f"Warning: Skipping item with unparseable date: {date_str}")
            pass
        except Exception as e:
            parse_errors += 1
            # print(f"Warning: Skipping item due to error: {e}")
            pass

    if parse_errors > 0:
        print(f"Warning: Skipped {parse_errors} items due to date parsing errors.")

    # Save the filtered list to the output file
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(filtered_judgements, f, indent=4)
        
        print(f"\nSuccessfully filtered {len(filtered_judgements)} judgements.")
        print(f"Results saved to '{OUTPUT_FILE}'.")

    except IOError as e:
        print(f"Error: Could not write to output file '{OUTPUT_FILE}'. {e}")
    except Exception as e:
        print(f"An unexpected error occurred while writing the file: {e}")

if __name__ == "__main__":
    filter_judgements()

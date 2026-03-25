import json
import os
import sys

# --- Configuration ---
INPUT_FILE = "response.json"
OUTPUT_FILE = "formatted_response.json"
# ---------------------

def format_nested_json():
    """
    Reads a JSON file that contains an escaped JSON string within a key,
    parses it, and saves the inner data as a properly formatted JSON file.
    """
    
    # 1. Check if input file exists
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print("Please make sure the file is in the same directory as the script.")
        return

    # 2. Read the outer JSON file
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            outer_data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
        print("The file might be corrupted or not valid JSON.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading '{INPUT_FILE}': {e}")
        return

    # 3. Check if the 'd' key exists
    if 'd' not in outer_data:
        print(f"Error: The key 'd' was not found in '{INPUT_FILE}'.")
        return
        
    inner_json_string = outer_data['d']
    
    if not isinstance(inner_json_string, str):
        print(f"Error: The value of key 'd' is not a string. Cannot parse.")
        return

    # 4. Parse the inner JSON string
    try:
        # The string itself contains a JSON array
        inner_data = json.loads(inner_json_string)
    except json.JSONDecodeError:
        print(f"Error: Could not decode the inner JSON string from the 'd' key.")
        print("The string content may not be valid JSON.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while parsing the inner string: {e}")
        return

    # 5. Save the cleaned, inner data to the output file
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(inner_data, f, indent=4)
        
        print(f"Successfully formatted JSON.")
        print(f"Clean data saved to '{OUTPUT_FILE}'.")
        if isinstance(inner_data, list):
            print(f"The file contains a list of {len(inner_data)} items.")

    except IOError as e:
        print(f"Error: Could not write to output file '{OUTPUT_FILE}'. {e}")
    except Exception as e:
        print(f"An unexpected error occurred while writing the file: {e}")

if __name__ == "__main__":
    format_nested_json()

import os
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.service import Service

# ---------- Helpers ----------
def check_internet(url="http://www.google.com", timeout=5, interval=10):
    """Ensure internet connection before scraping."""
    while True:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                print("Internet is connected.")
                return
        except requests.ConnectionError:
            print(f"Connection failed. Retrying in {interval} seconds...")
            time.sleep(interval)


def initialize_driver(download_directory):
    chrome_options = Options()
    prefs = {
        "download.default_directory": os.path.abspath(download_directory),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,  # Force download PDFs
        "download.directory_upgrade": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless=new")  # run without opening browser

    driver = webdriver.Chrome(service=Service(), options=chrome_options)
    return driver


def verify_pdf_link(url, timeout=10):
    """Check if PDF link is valid and accessible."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type or url.lower().endswith('.pdf'):
                return True, "Valid PDF link"
            else:
                return False, f"Not a PDF file (Content-Type: {content_type})"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {str(e)}"


def download_with_selenium(driver, link_element, download_dir, timeout=120, retries=3):
    """Try to download a file, skip if fails repeatedly."""
    attempt = 0
    while attempt < retries:
        try:
            before_files = set(os.listdir(download_dir))
            link_element.click()

            elapsed = 0
            while elapsed < timeout:
                after_files = set(os.listdir(download_dir))
                new_files = after_files - before_files
                if new_files:
                    new_file = list(new_files)[0]
                    file_path = os.path.join(download_dir, new_file)
                    if not new_file.endswith(".crdownload") and os.path.exists(file_path):
                        print(f"📄 Successfully downloaded: {new_file}")
                        return new_file  # ✅ Success
                time.sleep(3)  # Check every 3 seconds instead of 2
                elapsed += 3

            print(f"⚠️ Attempt {attempt+1}: Download timeout after {timeout}s")
        except Exception as e:
            print(f"⚠️ Selenium download failed (attempt {attempt+1}): {e}")

        attempt += 1
        time.sleep(5)  # Longer pause before retry

    print("❌ Skipping file after multiple failed attempts.")
    return None


def click_on_submit(driver):
    """Click the Submit button to load judgments table."""
    try:
        submit_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "appjudgmentbtn"))
        )
        submit_button.click()
        print("Clicked on Submit button.")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="appjudgment"]/table'))
        )
        print("Judgments table loaded.")
    except Exception as e:
        print(f"Error clicking submit: {e}")


# Define cutoff date
cutoff_date = datetime(2024, 11, 1)  # 1st Nov 2024

def scrape_lahore_high_court(driver, folder):
    driver.get("https://data.lhc.gov.pk/reported_judgments/judgments_approved_for_reporting")
    time.sleep(5)

    click_on_submit(driver)

    rows = driver.find_elements(By.XPATH, '//*[@id="appjudgment"]//tr')
    print(f"Found {len(rows)} judgment rows in Lahore High Court page.")

    downloaded_count = 0
    skipped_count = 0
    broken_links = 0

    for i in range(2, len(rows) + 1):
        try:
            case_title = driver.find_element(By.XPATH, f'//*[@id="appjudgment"]/table[{i}]/tbody/tr[1]/td[3]').text
            case_no = driver.find_element(By.XPATH, f'//*[@id="appjudgment"]/table[{i}]/tbody/tr[1]/td[2]').text
            judgment_date_text = driver.find_element(By.XPATH, f'//*[@id="appjudgment"]/table[{i}]/tbody/tr[1]/td[5]').text

            # Clean "uploaded on:" text
            judgment_date_clean = judgment_date_text.replace("uploaded on:", "").strip()

            # Convert to datetime
            try:
                judgment_date = datetime.strptime(judgment_date_clean, "%d-%m-%Y")
            except:
                print(f"⚠️ Could not parse date for row {i}: {judgment_date_text}, skipping...")
                continue

            # Skip older judgments
            if judgment_date < cutoff_date:
                print(f"⏭️ Skipping row {i}, judgment date {judgment_date_clean} is before cutoff")
                skipped_count += 1
                continue

            # Get download link
            try:
                link_element = driver.find_element(By.XPATH, f'//*[@id="appjudgment"]/table[{i}]/tbody/tr[1]/td[8]/a')
                download_url = link_element.get_attribute("href")
            except NoSuchElementException:
                print(f"❌ No download link found for row {i}")
                broken_links += 1
                continue

            # Check if download URL is valid
            if not download_url or download_url == "":
                print(f"❌ Empty download URL for row {i}")
                broken_links += 1
                continue

            # Verify PDF link before attempting download
            print(f"🔍 Verifying PDF link for: {case_no}...")
            is_valid, reason = verify_pdf_link(download_url)
            
            if not is_valid:
                print(f"❌ Invalid PDF link for {case_no}: {reason}")
                broken_links += 1
                continue

            filename = os.path.basename(download_url)
            file_path = os.path.join(folder, filename)

            # Skip already-downloaded files
            if os.path.exists(file_path):
                print(f"⏭️ Already have {filename}, skipping download")
                continue

            # Download the PDF
            print(f"📥 Downloading: {case_no} ({judgment_date_clean}) - {case_title[:50]}...")
            saved_file = download_with_selenium(driver, link_element, folder)

            if saved_file:
                downloaded_count += 1
                print(f"✅ Downloaded: {saved_file}")
            else:
                print(f"❌ Failed to download: {filename}")

        except NoSuchElementException:
            print(f"Row {i} missing data, skipping...")
        except Exception as e:
            print(f"Error processing row {i}: {e}")

    print(f"\n📊 Summary:")
    print(f"Downloaded: {downloaded_count} PDFs")
    print(f"Skipped (before Nov 2024): {skipped_count}")
    print(f"Broken/Invalid links: {broken_links}")


# ---------- Main ----------
def main():
    check_internet()
    folder = "LahoreHighCourt_PDFs"
    os.makedirs(folder, exist_ok=True)
    
    print(f"Starting PDF download for Lahore High Court judgments from Nov 2024 onwards...")
    print(f"Download folder: {os.path.abspath(folder)}")
    
    driver = initialize_driver(folder)
    try:
        scrape_lahore_high_court(driver, folder)
        print(f"\n🎉 Download process completed!")
        print(f"Check folder: {os.path.abspath(folder)}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
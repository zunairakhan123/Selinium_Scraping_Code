import os
import time
import random
import logging
import json
from datetime import datetime
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class PDFDownloader:
    def __init__(self, download_folder="SupremeCourt_Judgments_Nov2024"):
        self.download_folder = os.path.abspath(download_folder)
        self.setup_logging()
        self.setup_download_folder()
        self.driver = None
        self.downloaded_count = 0
        self.failed_count = 0
        self.failed_downloads = []  # track failed downloads
        self.current_page = None

        # Date range filter
        self.start_date = datetime(2024, 11, 1)  # From Nov 1, 2024
        self.end_date = datetime.today()         # Until today

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("pdf_downloader.log"), logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)

    def setup_download_folder(self):
        os.makedirs(self.download_folder, exist_ok=True)
        self.logger.info(f"Download folder: {self.download_folder}")

    def setup_driver(self):
        chrome_options = Options()
        prefs = {
            "download.default_directory": self.download_folder,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
            "plugins.plugins_disabled": ["Chrome PDF Viewer"],
        }
        chrome_options.add_experimental_option("prefs", prefs)

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
        chrome_options.add_argument("--headless")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.logger.info("Chrome WebDriver initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            return False

    def wait_for_download(self, timeout=30):
        start_time = time.time()
        initial_files = set(os.listdir(self.download_folder))

        while time.time() - start_time < timeout:
            current_files = set(os.listdir(self.download_folder))
            new_files = current_files - initial_files
            completed_files = [f for f in new_files if not f.endswith(".crdownload")]
            if completed_files:
                return completed_files[0]
            time.sleep(1)
        return None

    def download_pdf_from_row(self, row_num, row, retries=3):
        case_no = "Unknown"
        filename = "Unknown"
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            case_no = cells[2].text.strip() if len(cells) >= 3 else "Unknown"

            # Parse Upload Date (6th column, index 5)
            upload_date = None
            if len(cells) >= 6:
                date_text = cells[5].text.strip()
                if date_text:
                    try:
                        upload_date = datetime.strptime(date_text, "%d-%m-%Y")
                    except Exception as e:
                        self.logger.warning(f"Row {row_num}: Invalid date '{date_text}': {e}")
                        return True
                else:
                    self.logger.info(f"Row {row_num}: Skipping {case_no}, empty Upload Date")
                    return True

            # Skip if not in range
            if upload_date and not (self.start_date <= upload_date <= self.end_date):
                self.logger.info(f"Row {row_num}: Skipping {case_no}, date {upload_date.date()} not in range")
                return True

            # Get PDF link
            download_cell = cells[-1]
            try:
                link = download_cell.find_element(By.TAG_NAME, "a")
                pdf_url = link.get_attribute("href")
                filename = os.path.basename(urlparse(pdf_url).path)
            except:
                self.logger.warning(f"Row {row_num}: No valid PDF link found")
                return False

            # Skip if file already exists
            if os.path.exists(os.path.join(self.download_folder, filename)):
                self.logger.info(f"Row {row_num}: Skipping {case_no}, file '{filename}' already exists")
                return True

            # Retry mechanism
            for attempt in range(1, retries + 1):
                try:
                    self.logger.info(f"Row {row_num}: Downloading {case_no} ({filename}), attempt {attempt}")
                    self.driver.execute_script("arguments[0].scrollIntoView();", link)
                    time.sleep(1)
                    try:
                        link.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", link)

                    downloaded_file = self.wait_for_download(timeout=30)
                    if downloaded_file:
                        self.logger.info(f"Row {row_num}: Successfully downloaded {downloaded_file}")
                        self.downloaded_count += 1
                        return True
                except Exception as e:
                    self.logger.error(f"Row {row_num}: Attempt {attempt} failed: {e}")
                    time.sleep(2)

            # After retries, mark as failed
            self.failed_count += 1
            self.failed_downloads.append({
                "page": self.current_page if self.current_page else "Unknown",
                "row": row_num,
                "case_no": case_no,
                "filename": filename
            })
            self.logger.error(f"Row {row_num}: Failed to download after {retries} attempts")
            return False

        except Exception as e:
            self.failed_count += 1
            self.failed_downloads.append({
                "page": self.current_page if self.current_page else "Unknown",
                "row": row_num,
                "case_no": case_no,
                "filename": filename
            })
            self.logger.error(f"Row {row_num}: Error downloading PDF: {e}")
            return False

    def download_pdfs_from_page(self, page_num):
        self.logger.info(f"Processing page {page_num}")
        self.current_page = page_num
        try:
            rows = WebDriverWait(self.driver, 180).until(
                EC.presence_of_all_elements_located((By.XPATH, "//table//tr[position()>1]"))
            )
            self.logger.info(f"Found {len(rows)} judgment rows on page {page_num}")

            for i, row in enumerate(rows, 1):
                try:
                    self.download_pdf_from_row(i, row)
                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    self.logger.error(f"Error processing row {i}: {e}")
                    continue
            return True
        except Exception as e:
            self.logger.error(f"Error processing page {page_num}: {e}")
            return False

    def navigate_to_next_page(self):
        try:
            next_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Next"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", next_button)
            time.sleep(2)
            next_button.click()
            WebDriverWait(self.driver, 180).until(
                EC.presence_of_all_elements_located((By.XPATH, "//table//tr[position()>1]"))
            )
            return True
        except Exception as e:
            self.logger.error(f"Error navigating to next page: {e}")
            return False

    def download_all_pdfs(self, max_pages=None):
        if not self.setup_driver():
            return False
        try:
            self.logger.info("Opening Supreme Court judgment search page")
            self.driver.get("https://www.supremecourt.gov.pk/judgement-search/")

            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            self.logger.info("Initial page loaded, looking for Search Result button")

            # Find and click Search Result button
            search_results_button = None
            button_selectors = [
                "//button[contains(text(), 'Search Result')]",
                "//input[@value='Search Result']",
                "//a[contains(text(), 'Search Result')]",
                "//*[contains(text(), 'Search Result')]",
            ]
            for selector in button_selectors:
                try:
                    search_results_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    break
                except:
                    continue

            if search_results_button:
                self.logger.info("Found Search Result button, clicking...")
                search_results_button.click()
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
                self.logger.info("Search result table loaded successfully")
            else:
                self.logger.warning("Could not find Search Result button, assuming table is already visible")
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )

            page_num = 1
            while True:
                if max_pages and page_num > max_pages:
                    self.logger.info(f"Reached maximum pages limit: {max_pages}")
                    break

                self.download_pdfs_from_page(page_num)

                if not self.navigate_to_next_page():
                    self.logger.info("No more pages to process")
                    break

                page_num += 1
                time.sleep(random.uniform(5, 8))

            self.logger.info("=" * 50)
            self.logger.info("FINAL SUMMARY")
            self.logger.info(f"Pages processed: {page_num}")
            self.logger.info(f"PDFs successfully downloaded: {self.downloaded_count}")
            self.logger.info(f"Failed downloads: {self.failed_count}")
            self.logger.info(f"Download folder: {self.download_folder}")
            self.logger.info("=" * 50)

            # Save failed downloads to JSON file
            if self.failed_downloads:
                failed_file = os.path.join(self.download_folder, "failed_downloads.json")
                with open(failed_file, "w", encoding="utf-8") as f:
                    json.dump(self.failed_downloads, f, indent=4)
                self.logger.info(f"Failed downloads saved to {failed_file}")
            else:
                self.logger.info("No failed downloads to save.")

            return True
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()


def main():
    print("Supreme Court PDF Downloader")
    print("=" * 40)
    download_folder = "SupremeCourt_Judgments_Nov2024"
    max_pages = None # None = all pages

    print(f"Download folder: {download_folder}")
    print(f"Max pages: {max_pages if max_pages else 'All'}")
    response = input("\nStart downloading? (y/n): ").lower().strip()
    if response != "y":
        print("Cancelled.")
        return

    downloader = PDFDownloader(download_folder)
    success = downloader.download_all_pdfs(max_pages)

    if success:
        print("\nDownloading completed!")
        print(f"Check your folder: {downloader.download_folder}")
        print(f"Successfully downloaded: {downloader.downloaded_count} PDFs")
        print(f"Failed downloads: {downloader.failed_count}")
    else:
        print("\nDownloading failed or incomplete.")
        print("Check the log file: pdf_downloader.log")


if __name__ == "__main__":
    main()

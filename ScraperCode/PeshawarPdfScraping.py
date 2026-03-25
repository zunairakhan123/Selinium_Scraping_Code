import os
import time
import random
import logging
import json
from datetime import datetime
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class PHCPDFDownloader:
    def __init__(self, download_folder="PHC_Judgments_Pdfs"):
        self.download_folder = os.path.abspath(download_folder)
        self.setup_logging()
        self.setup_download_folder()
        self.driver = None
        self.downloaded_count = 0
        self.failed_count = 0
        self.failed_downloads = []
        self.current_page = None

        # Date range filter
        self.start_date = datetime(2024, 11, 1)   # From Nov 1, 2024
        self.end_date = datetime.today()          # Until today

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("phc_downloader.log"), logging.StreamHandler()],
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
        chrome_options.add_argument("--headless")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
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

    def download_pdf_from_row(self, row_num, row):
        case_no, filename = "Unknown", "Unknown"
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 9:
                self.logger.warning(f"Row {row_num}: Skipping, not enough cells")
                return True

            case_no = cells[1].text.strip() if cells[1].text else "Unknown"

            # Parse Decision Date (6th column, index 5)
            upload_date = None
            date_text = cells[5].text.strip()
            if date_text:
                try:
                    upload_date = datetime.strptime(date_text, "%d-%m-%Y")
                except Exception as e:
                    self.logger.warning(f"Row {row_num}: Invalid date '{date_text}': {e}")
                    return True

            # Apply date filter (Nov 2024 → today)
            if upload_date:
                if upload_date < self.start_date:
                    self.logger.info(f"Row {row_num}: Skipping {case_no}, date {upload_date.date()} before Nov 2024")
                    return True
                if upload_date > self.end_date:
                    self.logger.info(f"Row {row_num}: Skipping {case_no}, future date {upload_date.date()}")
                    return True

            # Get PDF link (9th column)
            download_cell = cells[8]
            link = download_cell.find_element(By.TAG_NAME, "a")
            pdf_url = link.get_attribute("href")
            filename = os.path.basename(urlparse(pdf_url).path)

            if os.path.exists(os.path.join(self.download_folder, filename)):
                self.logger.info(f"Row {row_num}: Already exists: {filename}")
                return True

            self.driver.execute_script("arguments[0].scrollIntoView();", link)
            time.sleep(1)
            link.click()

            downloaded_file = self.wait_for_download(timeout=30)
            if downloaded_file:
                self.logger.info(f"Row {row_num}: Downloaded {downloaded_file}")
                self.downloaded_count += 1
                return True

            self.failed_count += 1
            self.failed_downloads.append({"row": row_num, "case_no": case_no, "filename": filename})
            return False

        except Exception as e:
            self.failed_count += 1
            self.failed_downloads.append({"row": row_num, "case_no": case_no, "filename": filename})
            self.logger.error(f"Row {row_num}: Error {e}")
            return False

    def download_pdfs_from_page(self, page_num):
        self.logger.info(f"Processing page {page_num}")
        self.current_page = page_num

        # Only pick rows with enough cells (skip headers/short ones)
        rows = WebDriverWait(self.driver, 60).until(
            EC.presence_of_all_elements_located((By.XPATH, "//table//tr[position()>1]"))
        )

        valid_rows = [r for r in rows if len(r.find_elements(By.TAG_NAME, "td")) >= 9]

        for i, row in enumerate(valid_rows, 1):
            self.download_pdf_from_row(i, row)
            time.sleep(random.uniform(2, 4))


    def process_year(self, year):
        self.logger.info(f"Processing year {year}")
        self.driver.get("https://www.peshawarhighcourt.gov.pk/PHCCMS/reportedJudgments.php?action=search")

        time.sleep(3)

        # Select Year
        year_dropdown = WebDriverWait(self.driver, 120).until(
            EC.presence_of_element_located((By.ID, "year"))
        )
        Select(year_dropdown).select_by_visible_text(str(year))
        self.logger.info(f"Year {year} selected successfully")

        # Click search
        search_button = WebDriverWait(self.driver, 120).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='search']"))
        )
        search_button.click()
        self.logger.info("Search button clicked")

        WebDriverWait(self.driver, 120).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )

        page_num = 1
        while True:
            self.logger.info(f"Year {year} - Processing page {page_num}")
            self.download_pdfs_from_page(page_num)

            try:
                # Locate Next li fresh each time
                next_li = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "employee_list_next"))
                )

                # Stop if disabled
                if "disabled" in next_li.get_attribute("class"):
                    self.logger.info(f"Year {year} - Reached last page {page_num}")
                    break

                # Remember current active page
                current_page = self.driver.find_element(By.CSS_SELECTOR, "ul.pagination li.active a").text.strip()

                # Click next
                next_button = next_li.find_element(By.TAG_NAME, "a")
                self.driver.execute_script("arguments[0].scrollIntoView();", next_button)
                time.sleep(1)
                next_button.click()

                # Wait for page number to change
                WebDriverWait(self.driver, 30).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, "ul.pagination li.active a").text.strip() != current_page
                )

                page_num += 1
                time.sleep(2)

            except Exception as e:
                self.logger.info(f"Year {year} - No more pages after page {page_num}: {e}")
                break

    def download_all_pdfs(self):
        if not self.setup_driver():
            return False

        try:
            # First handle 2024 (Nov 2024 → today)
            self.process_year(2024)

            # Then handle 2025 (Jan 2025 → today)
            self.process_year(2025)

            self.logger.info("=" * 50)
            self.logger.info("FINAL SUMMARY")
            self.logger.info(f"PDFs successfully downloaded: {self.downloaded_count}")
            self.logger.info(f"Failed downloads: {self.failed_count}")
            self.logger.info(f"Download folder: {self.download_folder}")
            self.logger.info("=" * 50)

            # Save failed downloads
            if self.failed_downloads:
                failed_file = os.path.join(self.download_folder, "failed_downloads.json")
                with open(failed_file, "w", encoding="utf-8") as f:
                    json.dump(self.failed_downloads, f, indent=4)
                self.logger.info(f"Failed downloads saved to {failed_file}")

            return True
        finally:
            if self.driver:
                self.driver.quit()


def main():
    downloader = PHCPDFDownloader("PHC_Judgments_Pdfs")
    if downloader.download_all_pdfs():
        print(f"Downloaded: {downloader.downloaded_count} PDFs")
        print(f"Failed: {downloader.failed_count}")
    else:
        print("Download failed.")


if __name__ == "__main__":
    main()

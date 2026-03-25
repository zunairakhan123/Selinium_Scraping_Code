import os
import time
import json
import logging
from urllib.parse import urlparse, unquote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class SSTPDFDownloader:
    def __init__(self, json_file, download_folder="SST_Judgments_Pdfs"):
        self.download_folder = os.path.abspath(download_folder)
        self.json_file = json_file
        self.existing_files = set()
        self.driver = None
        self.downloaded_count = 0
        self.failed_downloads = []
        self.skipped_count = 0

        self.setup_logging()
        self.setup_download_folder()
        self.load_existing_files()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("sst_downloader.log", encoding="utf-8"), logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)

    def setup_download_folder(self):
        os.makedirs(self.download_folder, exist_ok=True)
        self.logger.info(f"Download folder: {self.download_folder}")

    def normalize_filename(self, filename):
        """Normalize filename for comparison by replacing spaces with underscores"""
        return filename.replace(" ", "_")

    def load_existing_files(self):
        """Load existing PDF filenames from JSON to avoid re-downloading"""
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for entry in data:
                        if "source_file" in entry:
                            normalized = self.normalize_filename(entry["source_file"])
                            self.existing_files.add(normalized)
                self.logger.info(f"Loaded {len(self.existing_files)} existing files from JSON")
            except Exception as e:
                self.logger.error(f"Failed to load JSON: {e}")

    def setup_driver(self):
        chrome_options = Options()
        prefs = {
            "download.default_directory": self.download_folder,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(10)
        self.logger.info("Chrome WebDriver initialized successfully")

    def wait_for_download(self, timeout=40, before_files=None):
        """Wait for a PDF file to finish downloading"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_files = set(os.listdir(self.download_folder))
            new_files = current_files - before_files if before_files else current_files
            completed = [f for f in new_files if f.endswith(".pdf") and not f.endswith(".crdownload")]

            if completed:
                time.sleep(1)
                return completed[0]

            downloading = [f for f in new_files if f.endswith(".crdownload")]
            if not downloading and new_files:
                time.sleep(1)

            time.sleep(1)
        return None

    def get_current_page_number(self):
        try:
            active_page = self.driver.find_element(By.XPATH, "//div[@id='PagingJ']//li[@class='active']/a")
            return int(active_page.text.strip())
        except:
            return 1

    def download_pdfs_from_page(self, page_num):
        """Download PDFs from the current page"""
        self.logger.info(f"Processing page {page_num}")

        WebDriverWait(self.driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//table"))
        )
        rows = self.driver.find_elements(By.XPATH, "//table//tr[position()>1]")
        self.logger.info(f"Found {len(rows)} judgments on page {page_num}")

        for i in range(1, len(rows) + 1):
            try:
                # Re-fetch row each time to avoid stale element
                row = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, f"//table//tr[position()={i+1}]"))
                )
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 4:
                    self.logger.warning(f"Page {page_num}, Row {i}: Insufficient columns, skipping")
                    continue

                pdf_link_el = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, f"//table//tr[position()={i+1}]//td[4]//a"))
                )
                pdf_url = pdf_link_el.get_attribute("href")

                raw_filename = os.path.basename(urlparse(pdf_url).path)
                filename = unquote(raw_filename)
                normalized_filename = self.normalize_filename(filename)

                if normalized_filename in self.existing_files:
                    self.logger.info(f"Page {page_num}, Row {i}: Skipping existing {filename}")
                    self.skipped_count += 1
                    continue

                if os.path.exists(os.path.join(self.download_folder, filename)):
                    self.logger.info(f"Page {page_num}, Row {i}: File already exists locally {filename}")
                    self.skipped_count += 1
                    continue

                before_files = set(os.listdir(self.download_folder))

                self.logger.info(f"Page {page_num}, Row {i}: Downloading {filename}")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", pdf_link_el)
                time.sleep(0.5)
                pdf_link_el.click()

                downloaded_file = self.wait_for_download(timeout=40, before_files=before_files)

                if downloaded_file:
                    self.logger.info(f"Page {page_num}, Row {i}: Successfully downloaded {downloaded_file}")
                    self.downloaded_count += 1
                    self.existing_files.add(normalized_filename)
                else:
                    self.failed_downloads.append({"page": page_num, "row": i, "filename": filename, "url": pdf_url})
                    self.logger.error(f"Page {page_num}, Row {i}: Download failed for {filename}")

            except Exception as e:
                self.failed_downloads.append({"page": page_num, "row": i, "error": str(e)})
                self.logger.error(f"Page {page_num}, Row {i}: Error - {e}")

    def click_next_page(self):
        try:
            next_button = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='PagingJ']//li/a[contains(text(),'Next')]"))
            )
            next_li = next_button.find_element(By.XPATH, "..")
            li_html = next_li.get_attribute("outerHTML")

            if "onclick" not in li_html:
                self.logger.info("Next button not clickable - reached last page")
                return False

            onclick_attr = next_li.get_attribute("onclick")
            if onclick_attr:
                self.driver.execute_script(onclick_attr)
                self.logger.info("Clicked Next button via JavaScript")
            else:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", next_button)
                self.logger.info("Clicked Next button directly")

            time.sleep(3)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//table//tr[position()>1]"))
            )
            return True
        except Exception as e:
            self.logger.error(f"Error clicking Next: {e}")
            return False

    def process_all_pages(self):
        self.driver.get("https://sstsindh.gov.pk/judgements.php")
        self.logger.info("Loaded main judgments page")
        time.sleep(3)

        page_num = 1
        max_pages = 20

        while page_num <= max_pages:
            self.download_pdfs_from_page(page_num)
            if not self.click_next_page():
                self.logger.info(f"No more pages after page {page_num}")
                break
            page_num += 1
            self.logger.info(f"Moving to page {page_num}")

        if page_num > max_pages:
            self.logger.warning(f"Stopped at safety limit of {max_pages} pages")

    def run(self):
        self.setup_driver()
        try:
            self.process_all_pages()
            self.logger.info("=" * 60)
            self.logger.info("DOWNLOAD SUMMARY")
            self.logger.info("=" * 60)
            self.logger.info(f"Successfully downloaded: {self.downloaded_count} PDFs")
            self.logger.info(f"Skipped (already exist): {self.skipped_count} PDFs")
            self.logger.info(f"Failed downloads: {len(self.failed_downloads)}")
            self.logger.info("=" * 60)

            if self.failed_downloads:
                failed_file = os.path.join(self.download_folder, "failed_downloads.json")
                with open(failed_file, "w", encoding="utf-8") as f:
                    json.dump(self.failed_downloads, f, indent=4, ensure_ascii=False)
                self.logger.info(f"Failed downloads saved to {failed_file}")

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("Browser closed")


def main():
    json_file = "merged_Sindh_Service_Tribunals_data_with_urls.json"
    if not os.path.exists(json_file):
        print(f"WARNING: {json_file} not found. Will download all PDFs.")

    downloader = SSTPDFDownloader(json_file)
    downloader.run()


if __name__ == "__main__":
    main()

import os
import time
import json
import logging
import random
from datetime import datetime
from urllib.parse import urlparse, unquote

from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException


class BHCPDFDownloader:
    def __init__(self, download_folder="BHC_Judgments_PDFs"):
        self.download_folder = os.path.abspath(download_folder)
        self.url = "https://portal.bhc.gov.pk/judgments/"
        self.start_date = datetime(2024, 11, 1)
        self.end_date = datetime.today()
        self.downloaded_pdfs = {}  # {pdf_url: filename} to track unique PDFs
        self.failed_downloads = []
        self.judges = [
            "Hon'ble Justice Muhammad Najamuddin Mengal"
        ]
        self.driver = None
        self.logger = self.setup_logging()
        self.setup_download_folder()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("bhc_downloader.log", encoding='utf-8'), 
                logging.StreamHandler()
            ],
        )
        return logging.getLogger(__name__)

    def setup_download_folder(self):
        os.makedirs(self.download_folder, exist_ok=True)
        self.logger.info(f"Download folder created at: {self.download_folder}")

    def setup_driver(self):
        chrome_options = Options()
        prefs = {
            "download.default_directory": self.download_folder,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_settings.popups": 0,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--log-level=3")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(120)
        self.driver.implicitly_wait(20)
        
        # Maximize window
        self.driver.maximize_window()
        
        self.logger.info("Chrome WebDriver initialized successfully")
        return self.driver

    def wait_for_download_complete(self, timeout=90):
        """Wait until all downloads are complete (no .crdownload files)"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            downloading = False
            for f in os.listdir(self.download_folder):
                if f.endswith(".crdownload") or f.endswith(".tmp"):
                    downloading = True
                    break
            if not downloading:
                time.sleep(2)  # Extra buffer
                return True
            time.sleep(2)
        return False

    def get_latest_pdf(self, previous_files):
        """Get the newly downloaded PDF"""
        current_files = set(os.listdir(self.download_folder))
        new_files = current_files - previous_files
        for f in new_files:
            if f.endswith(".pdf"):
                return f
        return None

    def select_search_by_judge(self):
        """Click on 'Search By Judge' radio button (3rd option)"""
        try:
            # Wait for page to load completely
            time.sleep(4)
            
            # Try multiple approaches to find the radio button
            radio_button = None
            try:
                # Method 1: Look for the third radio button
                radio_buttons = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
                if len(radio_buttons) >= 3:
                    radio_button = radio_buttons[2]  # Third radio button (index 2)
            except:
                pass
            
            if not radio_button:
                # Method 2: Direct value search
                try:
                    radio_button = WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@type='radio' and contains(@value, 'Judge')]"))
                    )
                except:
                    pass
            
            if radio_button:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", radio_button)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", radio_button)
                self.logger.info("Selected 'Search By Judge' option")
                time.sleep(4)
                return True
            else:
                self.logger.error("Could not find 'Search By Judge' radio button")
                return False
                
        except Exception as e:
            self.logger.error(f"Error selecting 'Search By Judge': {e}")
            return False
    

    def set_date_filter(self):
        """Set only the 'From Date' using the calendar picker (clicks input field, not icon)."""
        try:
            self.logger.info("Waiting for 'From Date' input field to appear...")
            time.sleep(4)

            # Step 1: Find and click the 'From Date' input field (this opens the calendar)
            from_input = WebDriverWait(self.driver, 40).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//label[normalize-space(text())='From Date']/following::input[1]")
                )
            )

            # Scroll into view and click safely
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", from_input)
            time.sleep(1)
            try:
                from_input.click()
            except:
                self.driver.execute_script("arguments[0].click();", from_input)
            self.logger.info("Clicked 'From Date' input field to open calendar")
            time.sleep(2)

            # Step 2: Wait for calendar to actually appear (Vuetify popup)
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class,'v-date-picker') or contains(@class,'v-picker__body')]")
                )
            )
            self.logger.info("Calendar popup opened successfully")

            # Step 3: Locate header (month/year display)
            header_selectors = [
                "//div[contains(@class,'v-date-picker-title__date')]",
                "//div[contains(@class,'v-date-picker-header__value')]",
                "//div[contains(@class,'v-picker__title')]",
                "//div[contains(@class,'v-date-picker-title')]/div"
            ]

            header = None
            for sel in header_selectors:
                try:
                    header = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, sel))
                    )
                    if header:
                        break
                except TimeoutException:
                    continue

            if not header:
                raise Exception("Could not find calendar header — structure may differ.")

            # Step 4: Navigate back to November 2024
            target_month = "Nov"
            target_year = "2024"

            while True:
                header_text = header.text.strip()
                if (target_year in header_text) and (target_month in header_text or "November" in header_text):
                    break

                try:
                    prev_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Previous month']"))
                    )
                    prev_btn.click()
                except Exception:
                    prev_btn = self.driver.find_element(By.XPATH, "//button[contains(@class,'mdi-chevron-left')]")
                    prev_btn.click()
                time.sleep(0.7)

            # Step 5: Select day 1 (Nov 1, 2024)
            day_xpath_variants = [
                "//button//div[normalize-space(text())='1']",
                "//button[normalize-space(text())='1']",
                "//div[contains(@class,'v-date-picker-table')]//button[contains(.,'1')]"
            ]

            day_btn = None
            for xpath_day in day_xpath_variants:
                try:
                    day_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_day))
                    )
                    if day_btn:
                        break
                except TimeoutException:
                    continue

            if not day_btn:
                raise Exception("Couldn't find day '1' button inside calendar.")

            # Scroll and click day 1
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", day_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", day_btn)
            self.logger.info("Selected From Date: 01/11/2024")

            # Step 6: Let the date apply (calendar usually closes automatically)
            time.sleep(2)
            self.logger.info("Date filter set successfully (To Date left as default).")
            return True

        except Exception as e:
            self.logger.error(f"Error setting date filter: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            try:
                self.driver.save_screenshot("date_filter_error.png")
            except:
                pass
            return False

    def download_all_pages(self, judge_name):
        """Download all judgments in paginated table with folder-level duplicate check"""
        page = 1

        while True:
            try:
                # Wait for table to load
                time.sleep(10)
                rows = WebDriverWait(self.driver, 60).until(
                    EC.presence_of_all_elements_located((By.XPATH, "//tbody/tr"))
                )

                self.logger.info(f"Judge: {judge_name} | Page {page} | Found {len(rows)} rows")

                for i in range(len(rows)):
                    try:
                        rows = self.driver.find_elements(By.XPATH, "//tbody/tr")
                        if i >= len(rows):
                            break

                        row = rows[i]
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 5:
                            continue

                        # Detect download link
                        try:
                            download_link_element = cols[4].find_element(By.TAG_NAME, "a")
                        except NoSuchElementException:
                            self.logger.debug(f"No download link in row {i+1}")
                            continue

                        # Scroll into view and pause
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                        time.sleep(random.uniform(2, 4))

                        # ✅ Get current files in the folder BEFORE clicking download
                        existing_files = set(f for f in os.listdir(self.download_folder) if f.endswith(".pdf"))

                        # Extract file name directly from the link (UUID-based filename)
                        file_url = download_link_element.get_attribute("href")
                        parsed_name = os.path.basename(urlparse(file_url).path).strip()

                        # Skip if file already exists in folder
                        if parsed_name and parsed_name.endswith(".pdf") and parsed_name in existing_files:
                            self.logger.info(f"🟡 Skipping already downloaded file: {parsed_name}")
                            continue

                        # Click the download link
                        self.driver.execute_script("arguments[0].click();", download_link_element)
                        self.logger.info(f"Clicked download for row {i+1} ({parsed_name or 'Unknown Filename'})")


                        # ✅ Wait for download to complete
                        if self.wait_for_download_complete(timeout=120):
                            # Get the new PDF that was downloaded
                            new_pdf = self.get_latest_pdf(existing_files)

                            if new_pdf:
                                self.logger.info(f"✅ Successfully downloaded new file: {new_pdf}")
                            else:
                                self.logger.warning(f"⚠️ Download completed but no new PDF found for row {i+1}")
                        else:
                            self.logger.warning(f"⏰ Timeout waiting for download (row {i+1})")

                        # Longer wait before next file
                        time.sleep(random.uniform(10, 15))

                    except Exception as e:
                        self.logger.warning(f"Error processing row {i+1}: {e}")
                        continue

                # ✅ Check for Next button
                try:
                    time.sleep(random.uniform(20, 30))
                    next_button = self.driver.find_element(
                        By.XPATH, "//button[@aria-label='Next page' and not(@disabled)]"
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(3)
                    self.driver.execute_script("arguments[0].click();", next_button)
                    self.logger.info(f"➡️ Moving to page {page + 1}")
                    page += 1
                    time.sleep(random.uniform(20, 30))
                except (NoSuchElementException, TimeoutException):
                    self.logger.info(f"✅ No more pages for {judge_name}. Reached last page.")
                    break

            except Exception as e:
                self.logger.error(f"Error on page {page}: {e}")
                break

    def process_judge(self, judge_name):
        """Process one judge"""
        try:
            self.logger.info(f"\n{'='*60}\nProcessing: {judge_name}\n{'='*60}")
            
            # Navigate to URL
            self.logger.info(f"Navigating to {self.url}")
            self.driver.get(self.url)
            time.sleep(8)  # Increased wait for page load
            
            # Select "Search By Judge"
            if not self.select_search_by_judge():
                self.logger.error("Failed to select 'Search By Judge' radio button")
                return False
            
            # Wait for dropdown to appear
            time.sleep(3)
            
            # Click judge dropdown
            try:
                # Find the Judge dropdown field
                judge_dropdown = WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'v-select__slot')]"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", judge_dropdown)
                time.sleep(2)
                self.driver.execute_script("arguments[0].click();", judge_dropdown)
                self.logger.info("Clicked judge dropdown")
                time.sleep(3)
                
                # ✅ Wait for dropdown options to appear and select the judge safely (handles single quotes)
                if "'" in judge_name:
                    xpath_judge = f'//div[contains(@class,"v-list-item__title") and normalize-space(text())="{judge_name}"]'
                else:
                    xpath_judge = f"//div[contains(@class,'v-list-item__title') and normalize-space(text())='{judge_name}']"

                option = WebDriverWait(self.driver, 60).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_judge))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", option)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", option)
                self.logger.info(f"Selected judge: {judge_name}")
                time.sleep(3)

            except Exception as e:
                self.logger.error(f"Error selecting judge {judge_name}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                return False

            # Set date filter
            if not self.set_date_filter():
                self.logger.error("Failed to set date filter")
                return False
            
            # Small pause before clicking submit
            time.sleep(2)
            
            # Click SUBMIT button
            try:
                # Multiple ways to find the SUBMIT button
                submit_btn = None
                
                # Method 1: Look for button with "submit" text (case-insensitive)
                try:
                    submit_btn = WebDriverWait(self.driver, 15).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(., 'SUBMIT', 'submit'), 'submit')]"))
                    )
                except:
                    pass
                
                # Method 2: Look for button with specific class
                if not submit_btn:
                    try:
                        submit_btn = self.driver.find_element(By.XPATH, "//button[contains(@class, 'deep-purple') and contains(@class, 'accent-4')]")
                    except:
                        pass
                
                # Method 3: Look for button with mdi-receipt icon
                if not submit_btn:
                    try:
                        submit_btn = self.driver.find_element(By.XPATH, "//button[.//i[contains(@class, 'mdi-receipt')]]")
                    except:
                        pass
                
                if submit_btn:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
                    time.sleep(2)
                    self.driver.execute_script("arguments[0].click();", submit_btn)
                    self.logger.info(f"Clicked SUBMIT button for judge: {judge_name}")
                    time.sleep(10)  # Wait longer for results to load
                else:
                    self.logger.error("Could not find SUBMIT button")
                    return False
                
            except Exception as e:
                self.logger.error(f"Error clicking SUBMIT button: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                return False
            
            # Check if results table loaded
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, "//tbody/tr"))
                )
                self.logger.info("Results table loaded successfully")
            except:
                self.logger.warning("Could not verify results table - continuing anyway")
            
            # Start downloading from all pages
            self.download_all_pages(judge_name)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing judge {judge_name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False


    def run(self):
        try:
            self.setup_driver()
            
            for idx, judge in enumerate(self.judges, 1):
                try:
                    self.logger.info(f"\n\n>>> Starting Judge {idx}/{len(self.judges)}: {judge}")
                    self.process_judge(judge)
                    self.logger.info(f">>> Completed Judge {idx}/{len(self.judges)}: {judge}")
                    self.logger.info(f">>> Total unique PDFs downloaded so far: {len(self.downloaded_pdfs)}")
                    time.sleep(5)
                    
                except Exception as e:
                    self.logger.error(f"Error processing judge {judge}: {e}")
                    continue
            
            # Save report
            report = {
                "total_unique_pdfs": len(self.downloaded_pdfs),
                "downloaded_pdfs": list(self.downloaded_pdfs.keys()),
                "failed_downloads": self.failed_downloads,
                "date_range": f"{self.start_date.strftime('%d/%m/%Y')} to {self.end_date.strftime('%d/%m/%Y')}"
            }
            
            report_path = os.path.join(self.download_folder, "download_report.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"All downloads completed!")
            self.logger.info(f"Total unique PDFs downloaded: {len(self.downloaded_pdfs)}")
            self.logger.info(f"Failed downloads: {len(self.failed_downloads)}")
            self.logger.info(f"Report saved to: {report_path}")
            self.logger.info(f"{'='*60}\n")
            
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            if self.driver:
                self.driver.quit()


if __name__ == "__main__":
    scraper = BHCPDFDownloader()
    scraper.run()
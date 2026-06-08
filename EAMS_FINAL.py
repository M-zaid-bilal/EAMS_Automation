from playwright.sync_api import sync_playwright
import os
import re
import time
import csv
import sys
from dataclasses import dataclass
from typing import List, Set, Optional, Callable, Any
from abc import ABC, abstractmethod
import gc
import psutil


# ------------------------------------------------------------------
# MEMORY MONITOR
# ------------------------------------------------------------------
class MemoryMonitor:
    """Monitors and logs memory usage"""
    
    def __init__(self, warn_mb: int = 1024, critical_mb: int = 2048):
        self.warn_mb = warn_mb
        self.critical_mb = critical_mb
        self.process = psutil.Process()
        self.peak_mb = 0
    
    def get_mb(self) -> float:
        """Get current memory usage in MB"""
        return self.process.memory_info().rss / 1024 / 1024
    
    def log(self, tag: str = "") -> float:
        """Log current memory usage and track peak"""
        current = self.get_mb()
        self.peak_mb = max(self.peak_mb, current)
        
        status = ""
        if current >= self.critical_mb:
            status = "CRITICAL"
        elif current >= self.warn_mb:
            status = "WARN"
        
        print(f"[MEMORY] {tag:35} {current:6.1f} MB  | Peak: {self.peak_mb:6.1f} MB  {status}")
        
        if current >= self.critical_mb:
            print("[MEMORY] Critical memory threshold reached - forcing garbage collection")
            gc.collect()
        
        return current
    
    def force_cleanup(self):
        """Force garbage collection and log result"""
        before = self.get_mb()
        gc.collect()
        after = self.get_mb()
        print(f"[MEMORY] GC: {before:.1f} MB -> {after:.1f} MB (freed {before - after:.1f} MB)")


# ------------------------------------------------------------------
# WORKER PROFILE
# ------------------------------------------------------------------
@dataclass
class WorkerProfile:
    """Data class for injured worker profile"""
    first_name: str
    last_name: str
    dob: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
    
    @property
    def normalized_dob(self) -> Optional[str]:
        """Normalize DOB to MM/DD/YYYY format"""
        if not self.dob:
            return None
        try:
            parts = self.dob.strip().split('/')
            if len(parts) == 3:
                return f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
            return self.dob
        except Exception:
            return self.dob


# ------------------------------------------------------------------
# SESSION MANAGER
# ------------------------------------------------------------------
class SessionManager:
    """Manages browser session and authentication"""
    
    GATEWAY_URL = "https://eams.dwc.ca.gov/WebEnhancement/RequesterInformationCaptureScreen.jsp?logout=out"
    MAX_RETRIES = 3
    BASE_DELAY = 5
    
    def __init__(self, page, memory_monitor: Optional[MemoryMonitor] = None):
        self.page = page
        self.memory_monitor = memory_monitor
    
    def is_on_gateway_page(self) -> bool:
        """Check if current page is the login gateway"""
        try:
            current_url = self.page.url
            if "RequesterInformationCaptureScreen" in current_url:
                return True
            if self.page.locator("#fnam").count() > 0 and self.page.locator("#fnam").is_visible():
                return True
        except Exception:
            pass
        return False
    
    def safe_wait_for_selector(self, selector: str, timeout: int = 15000, retries: int = 3) -> bool:
        """Wait for selector with retry and recovery"""
        for attempt in range(retries):
            try:
                self.page.wait_for_selector(selector, timeout=timeout)
                return True
            except Exception as e:
                print(f"[WARNING] Selector '{selector}' not found (attempt {attempt + 1}/{retries}): {str(e)[:50]}")
                
                if attempt < retries - 1:
                    if self.is_on_gateway_page():
                        print("[RECOVERY] On gateway page, but selector missing - reloading gateway...")
                        self.page.reload()
                        time.sleep(2)
                    else:
                        self.page.evaluate("window.location.reload()")
                        time.sleep(3)
        
        return False
    
    def handle_rate_limit(self, action_callback: Optional[Callable] = None) -> bool | str:
        """Handle HTTP 429 rate limits with retry logic"""
        if action_callback:
            try:
                action_callback()
            except Exception as nav_err:
                print(f"[WARNING] Navigation raised an exception: {str(nav_err)}")
        
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        
        try:
            body_text = self.page.locator("body").inner_text()
            reload_button = self.page.locator("#reload-button")
        except Exception:
            return True
        
        if "HTTP ERROR 429" not in body_text and reload_button.count() == 0:
            return True
        
        for attempt in range(self.MAX_RETRIES):
            wait_time = self.BASE_DELAY * (2 ** attempt)
            print(f"\n[ALERT] HTTP 429 Rate Limit hit! Waiting {wait_time} seconds...")
            time.sleep(wait_time)
            
            print("Attempting session recovery reload sequence...")
            try:
                if reload_button.count() > 0:
                    reload_button.first.click(timeout=3000)
                else:
                    self.page.evaluate("window.location.reload()")
            except Exception:
                print("Injecting hard script recovery refresh...")
                self.page.evaluate("window.location.reload()")
            
            try:
                self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            self.page.wait_for_timeout(3000)
            
            try:
                body_text_check = self.page.locator("body").inner_text()
                if "HTTP ERROR 429" not in body_text_check:
                    print("[SUCCESS] Rate limit cleared.")
                    return "RELOADED"
            except Exception:
                pass
        
        print("[FATAL] Exceeded retry limit. Portal access is heavily throttled.")
        return False
    
    def authenticate(self, requester_name: str = "MesaCare", 
                     requester_last: str = "Automation", 
                     email: str = "reports@mesacare.com") -> bool:
        """Authenticate through the gateway"""
        print("\nAuthenticating through gateway...")
        
        self.handle_rate_limit(
            lambda: self.page.goto(self.GATEWAY_URL, wait_until="domcontentloaded")
        )
        
        if not self.safe_wait_for_selector("#fnam", timeout=10000):
            print("[ERROR] Gateway form not loading. Retrying...")
            self.page.reload()
            time.sleep(2)
            self.safe_wait_for_selector("#fnam", timeout=10000)
        
        self.page.locator("#fnam").fill(requester_name)
        self.page.locator("#lname").fill(requester_last)
        self.page.locator("#em").fill(email)
        self.page.select_option("#reasonForReq", value="CASEPARTICIPANTSEARCH")
        self.page.wait_for_timeout(500)
        
        self.handle_rate_limit(lambda: self.page.locator("input[value='Next']").click())
        self.page.wait_for_timeout(2000)
        
        return True
    
    def restore_search(self, profile: WorkerProfile) -> int:
        """Re-authenticate and restore search results after session expiry"""
        print("\n[SESSION RECOVERY] Portal session expired - re-authenticating...")
        
        self.authenticate()
        return self.perform_search(profile)
    
    def perform_search(self, profile: WorkerProfile) -> int:
        """Perform worker search with given profile"""
        if not self.safe_wait_for_selector("#firstname", timeout=15000, retries=3):
            print("[ERROR] Search form not loading. Attempting recovery...")
            self.page.evaluate("window.location.reload()")
            time.sleep(3)
            if not self.safe_wait_for_selector("#firstname", timeout=10000):
                print("[FATAL] Cannot load search form.")
                return 0
        
        self.page.fill("#firstname", profile.first_name)
        self.page.fill("#lastname", profile.last_name)
        
        if profile.dob and profile.normalized_dob:
            print(f"Using DOB: {profile.normalized_dob}")
            self.page.fill("#dob", profile.normalized_dob)
        
        self.page.wait_for_timeout(500)
        self.handle_rate_limit(lambda: self.page.click("#searchBtn"))
        self.page.wait_for_timeout(2000)
        
        try:
            return self.page.locator("text=View cases").count()
        except Exception:
            return 0
    
    def perform_search_without_dob(self, profile: WorkerProfile) -> int:
        """Perform search WITHOUT using DOB as fallback with retry"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                if not self.safe_wait_for_selector("#firstname", timeout=10000, retries=2):
                    print("[ERROR] Search form not loading. Reloading...")
                    self.page.reload()
                    time.sleep(2)
                    continue
                
                self.page.fill("#firstname", profile.first_name)
                self.page.fill("#lastname", profile.last_name)
                
                self.page.wait_for_timeout(500)
                nav_result = self.handle_rate_limit(lambda: self.page.click("#searchBtn"))
                self.page.wait_for_timeout(2000)
                
                if nav_result == "RELOADED":
                    print("[RETRY] Rate limit during search, retrying...")
                    time.sleep(5)
                    continue
                
                try:
                    return self.page.locator("text=View cases").count()
                except Exception:
                    return 0
                    
            except Exception as e:
                print(f"[ERROR] Search without DOB failed (attempt {attempt + 1}): {str(e)[:100]}")
                if attempt < max_attempts - 1:
                    time.sleep(5)
                    continue
        
        return 0
    
    def navigate_back_to_grid(self) -> str | bool:
        """Navigate back to search results grid"""
        previous_btn = self.page.locator("input[value='Previous']")
        if previous_btn.count() > 0:
            return self.handle_rate_limit(lambda: previous_btn.click())
        return self.handle_rate_limit(lambda: self.page.go_back())


# ------------------------------------------------------------------
# CASE EXTRACTOR
# ------------------------------------------------------------------
class CaseExtractor:
    """Extracts case numbers from EAMS pages"""
    
    ADJ_PATTERN = re.compile(r'ADJ\d+')
    
    @classmethod
    def extract_from_html(cls, html_content: str) -> Set[str]:
        """Extract ADJ case numbers from HTML content"""
        return set(cls.ADJ_PATTERN.findall(html_content))
    
    @classmethod
    def extract_from_page(cls, page) -> Set[str]:
        """Extract ADJ case numbers from current page"""
        return cls.extract_from_html(page.content())


# ------------------------------------------------------------------
# PROGRESS TRACKER
# ------------------------------------------------------------------
class ProgressTracker:
    """Tracks and saves extraction progress"""
    
    def __init__(self, iteration_num: str = "it_15"):
        self.iteration_num = iteration_num
        self.case_numbers: Set[str] = set()
        self.profile: Optional[WorkerProfile] = None
    
    def set_profile(self, profile: WorkerProfile):
        """Set the current worker profile"""
        self.profile = profile
        self.case_numbers.clear()
    
    def add_cases(self, new_cases: Set[str]):
        """Add new case numbers to tracked set"""
        self.case_numbers.update(new_cases)
    
    def save(self):
        """Save current progress to text file"""
        if not self.profile:
            return
        
        filename = f"extracted_cases_{self.profile.last_name}_{self.profile.first_name}_{self.iteration_num}.txt"
        
        try:
            with open(filename, "w", encoding="utf-8") as text_file:
                text_file.write("EAMS CASE RETRIEVAL REPORT (LIVE PROGRESS SAVE)\n")
                text_file.write(f"Target profile: {self.profile.full_name}\n")
                text_file.write(f"DOB context: {self.profile.dob if self.profile.dob else 'Not Provided'}\n")
                text_file.write("-" * 40 + "\n")
                
                if self.case_numbers:
                    text_file.write(f"Discovered Case Identifiers ({len(self.case_numbers)} total):\n")
                    for rank, case_id in enumerate(sorted(self.case_numbers), start=1):
                        text_file.write(f"[{rank}] {case_id}\n")
                else:
                    text_file.write("No matching ADJ case numbers captured yet.\n")
        except Exception as e:
            print(f"[WARNING] Save failed: {str(e)}")
    
    def display_summary(self):
        """Display extraction summary to console"""
        print("\n" + "=" * 52)
        print("            EXTRACTION SUMMARY")
        print("=" * 52)
        print(f" Profile    : {self.profile.full_name if self.profile else 'N/A'}")
        print(f" Cases Found: {len(self.case_numbers)}")
        if self.case_numbers:
            print(f" Case IDs   : {', '.join(sorted(self.case_numbers)[:5])}")
            if len(self.case_numbers) > 5:
                print(f"              ... and {len(self.case_numbers) - 5} more")
        print("=" * 52)


# ------------------------------------------------------------------
# EAMS SCRAPER
# ------------------------------------------------------------------
class EAMSScraper:
    """Main EAMS automation scraper"""
    
    def __init__(self, iteration_num: str = "it_15"):
        self.iteration_num = iteration_num
        self.browser = None
        self.context = None
        self.page = None
        self.session_manager = None
        self.progress_tracker = ProgressTracker(iteration_num)
        self.playwright = None
        self.memory_monitor = MemoryMonitor(warn_mb=1024, critical_mb=2048)
    
    def start(self, headless: bool = False):
        """Launch browser and initialize components"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.context.new_page()
        self.session_manager = SessionManager(self.page, self.memory_monitor)
        return self
    
    def stop(self):
        """Close browser and cleanup"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def _handle_detail_page_extraction(self, index: int, total: int) -> bool:
        """Extract case numbers from detail page"""
        if self.session_manager.is_on_gateway_page():
            return False
        
        found_cases = CaseExtractor.extract_from_page(self.page)
        
        if found_cases:
            self.progress_tracker.add_cases(found_cases)
            self.progress_tracker.save()
            print(f"  Found {len(found_cases)} case(s): {', '.join(found_cases)}")
        
        return True
    
    def _process_single_result(self, profile: WorkerProfile, 
                                index: int, total: int) -> Optional[int]:
        """Process a single search result entry"""
        print(f"\nProcessing match [{index + 1}/{total}]...")
        
        if self.session_manager.is_on_gateway_page():
            print("Gateway detected, re-authenticating...")
            new_count = self.session_manager.restore_search(profile)
            return new_count if new_count > 0 else None
        
        try:
            current_link = self.page.locator("text=View cases").nth(index)
            nav_status = self.session_manager.handle_rate_limit(lambda: current_link.click())
        except Exception as e:
            print(f"[ERROR] Could not click view cases link: {str(e)[:100]}")
            return None
            
        self.page.wait_for_timeout(2000)
        
        if self.session_manager.is_on_gateway_page():
            print("Gateway detected after click, re-authenticating...")
            new_count = self.session_manager.restore_search(profile)
            return new_count if new_count > 0 else None
        
        if nav_status == "RELOADED":
            print("Rate limit reloaded to grid, retrying entry...")
            self.page.wait_for_timeout(2000)
            return total
        
        if not self._handle_detail_page_extraction(index, total):
            return None
        
        print("  Returning to grid...")
        back_status = self.session_manager.navigate_back_to_grid()
        
        if back_status == "RELOADED":
            self.page.wait_for_timeout(1000)
        else:
            self.page.wait_for_timeout(1500)
        
        if self.session_manager.is_on_gateway_page():
            print("Gateway detected after return, re-authenticating...")
            new_count = self.session_manager.restore_search(profile)
            if new_count == 0:
                return None
            return new_count
        
        self.memory_monitor.log(f"After match {index + 1}")
        return total
    
    def scrape_worker(self, profile: WorkerProfile):
        """Main scraping orchestration for a single worker with retry logic"""
        self.memory_monitor.log(f"START: {profile.full_name}")
        
        print("\n" + "=" * 52)
        print("            TARGET PATIENT METADATA")
        print("=" * 52)
        print(f" First Name : {profile.first_name}")
        print(f" Last Name  : {profile.last_name}")
        print(f" D.O.B      : {profile.dob if profile.dob else '[NOT PROVIDED]'}")
        print("=" * 52)
        
        self.progress_tracker.set_profile(profile)
        self.progress_tracker.save()
        
        # Authenticate and search
        self.session_manager.authenticate()
        results_count = self.session_manager.perform_search(profile)
        print(f"Initial search returned {results_count} result(s).")
        
        # RETRY LOGIC WITH LOOP: If search failed (0 results) and DOB was provided, retry without DOB
        search_failed = (results_count == 0 and profile.dob is not None)
        retry_attempts = 0
        max_retries = 3
        
        while search_failed and retry_attempts < max_retries:
            retry_attempts += 1
            print(f"\n[RETRY {retry_attempts}/{max_retries}] No results found with DOB. Retrying search without DOB for {profile.full_name}...")
            
            # Click New Search to reset form
            try:
                new_search_btn = self.page.locator("input[value='New Search']")
                if new_search_btn.count() > 0:
                    self.session_manager.handle_rate_limit(lambda: new_search_btn.click())
                    self.page.wait_for_timeout(3000)
            except Exception as e:
                print(f"[WARNING] Could not click New Search: {str(e)[:100]}")
                # Hard reload as fallback
                self.page.evaluate("window.location.reload()")
                time.sleep(3)
                self.session_manager.authenticate()
            
            # Retry without DOB
            results_count = self.session_manager.perform_search_without_dob(profile)
            print(f"Search without DOB returned {results_count} result(s).")
            
            if results_count > 0:
                print(f"[RETRY SUCCESS] Found {results_count} result(s) without DOB.")
                profile.dob = None
                search_failed = False
                break
            else:
                print(f"[RETRY FAILED] Still no results. Attempt {retry_attempts}/{max_retries}")
                if retry_attempts < max_retries:
                    print("Waiting 10 seconds before next retry...")
                    time.sleep(10)
                    # Re-authenticate before next attempt
                    self.session_manager.authenticate()
        
        if results_count == 0 and retry_attempts == max_retries:
            print(f"[WARNING] All {max_retries} retry attempts failed for {profile.full_name}. Moving to next record.")
        
        # Handle multiple results without DOB
        if results_count > 1 and not profile.dob:
            print("\n[ATTENTION] Multiple records detected. Refinement recommended.")
            user_dob = input("Enter DOB (MM/DD/YYYY) to refine search [Or ENTER to scrape all]: ").strip()
            
            if user_dob:
                profile.dob = user_dob
                print(f"Refining search with DOB: {profile.dob}...")
                
                try:
                    if not self.page.locator("#dob").is_visible():
                        new_search_btn = self.page.locator("input[value='New Search']")
                        if new_search_btn.count() > 0:
                            self.session_manager.handle_rate_limit(lambda: new_search_btn.click())
                except Exception:
                    pass
                
                results_count = self.session_manager.perform_search(profile)
        
        # Process results
        if results_count > 0:
            print(f"\nProcessing {results_count} match(es)...")
            
            i = 0
            while i < results_count:
                result = self._process_single_result(profile, i, results_count)
                
                if result is None:
                    print("Search lost, stopping loop.")
                    break
                elif result != results_count:
                    results_count = result
                    continue
                else:
                    i += 1
        
        else:
            print("No 'View cases' links found. Checking current page...")
            found_cases = CaseExtractor.extract_from_page(self.page)
            if found_cases:
                self.progress_tracker.add_cases(found_cases)
                self.progress_tracker.save()
        
        self.progress_tracker.display_summary()
        
        # Memory cleanup between records
        try:
            self.page.evaluate("window.location.reload()")
            self.page.wait_for_timeout(1000)
        except Exception:
            pass
        
        self.memory_monitor.force_cleanup()
        self.memory_monitor.log(f"END: {profile.full_name}")
        
        print(f"\n[SUCCESS] Completed for {profile.full_name}")


# ------------------------------------------------------------------
# DATA SOURCES
# ------------------------------------------------------------------
class DataSource(ABC):
    """Abstract base class for data sources"""
    
    @abstractmethod
    def get_profiles(self) -> List[WorkerProfile]:
        pass


class ManualDataSource(DataSource):
    """Manual input data source"""
    
    def get_profiles(self) -> List[WorkerProfile]:
        print("\n--- Manual Entry Mode ---")
        first_name = input("Enter Injured Worker First Name: ").strip()
        last_name = input("Enter Injured Worker Last Name: ").strip()
        dob = input("Enter DOB (MM/DD/YYYY) [ENTER to skip]: ").strip()
        
        if not first_name or not last_name:
            print("[FATAL] Name fields are required.")
            return []
        
        return [WorkerProfile(first_name=first_name, last_name=last_name, dob=dob or None)]


class CSVDataSource(DataSource):
    """CSV file data source"""
    
    def __init__(self, filename: str):
        self.filename = filename
    
    def get_profiles(self) -> List[WorkerProfile]:
        if not os.path.exists(self.filename):
            raise FileNotFoundError(f"CSV file '{self.filename}' not found.")
        
        profiles = []
        
        with open(self.filename, mode='r', encoding='utf-8-sig') as csv_file:
            reader = csv.DictReader(csv_file)
            
            header_map = {re.sub(r'[\s_\-]', '', str(col)).lower(): col 
                         for col in reader.fieldnames}
            
            required_keys = ['firstname', 'lastname', 'dob']
            missing = [k for k in required_keys if k not in header_map]
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            
            for row in reader:
                f_name = row[header_map['firstname']].strip()
                l_name = row[header_map['lastname']].strip()
                d_obj = row[header_map['dob']].strip()
                
                if f_name and l_name:
                    profiles.append(WorkerProfile(
                        first_name=f_name,
                        last_name=l_name,
                        dob=d_obj or None
                    ))
        
        print(f"[OK] Loaded {len(profiles)} profiles from CSV.")
        return profiles


# ------------------------------------------------------------------
# APPLICATION
# ------------------------------------------------------------------
class Application:
    """Main application orchestrator"""
    
    def __init__(self, iteration_num: str = "it_15"):
        self.iteration_num = iteration_num
        self.scraper = None
    
    def _select_data_source(self) -> Optional[DataSource]:
        """Prompt user for data source selection"""
        print("\n" + "=" * 52)
        print("       EAMS AUTOMATION PIPELINE ENGINE")
        print("=" * 52)
        print("1. Manual Entry (Single Injured Worker)")
        print("2. Batch CSV Import (Bulk Processing)")
        print("-" * 52)
        
        choice = input("Select mode (1 or 2): ").strip()
        
        if choice == "1":
            return ManualDataSource()
        elif choice == "2":
            filename = input("Enter CSV filename (e.g., workers.csv): ").strip()
            return CSVDataSource(filename)
        else:
            print("[ERROR] Invalid selection.")
            return None
    
    def run(self):
        """Run the application"""
        data_source = self._select_data_source()
        if not data_source:
            sys.exit(1)
        
        try:
            profiles = data_source.get_profiles()
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL] {str(e)}")
            sys.exit(1)
        
        if not profiles:
            print("[FATAL] No profiles to process.")
            sys.exit(1)
        
        input("\nPress [ENTER] to launch browser and begin scraping...")
        
        self.scraper = EAMSScraper(self.iteration_num)
        
        try:
            self.scraper.start(headless=False)
            
            for idx, profile in enumerate(profiles, 1):
                print(f"\n{'='*64}")
                print(f"[PROGRESS] Processing {idx}/{len(profiles)}: {profile.full_name}")
                print(f"{'='*64}")
                self.scraper.scrape_worker(profile)
            
            print("\n" + "=" * 64)
            print("                    BATCH COMPLETE")
            print("=" * 64)
            print("Review browser window. Press [ENTER] in this terminal to exit.")
            input()
            
        finally:
            self.scraper.stop()


def main():
    """Entry point"""
    app = Application(iteration_num="it_15")
    app.run()


if __name__ == "__main__":
    main()
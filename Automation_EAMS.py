
from playwright.sync_api import sync_playwright
import os
import re
import time
import csv
import sys

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
ITERATION_NUM = "it_13"

# ------------------------------------------------------------------
# PROGRESSIVE FILE WRITER MECHANISM
# ------------------------------------------------------------------
def save_progress_to_txt(first_name, last_name, dob, adj_set):
    filename_txt = f"extracted_cases_{last_name}_{first_name}_{ITERATION_NUM}.txt"
    sorted_adjs = sorted(list(adj_set))
    try:
        with open(filename_txt, "w", encoding="utf-8") as text_file:
            text_file.write(f"EAMS CASE RETRIEVAL REPORT (LIVE PROGRESS SAVE)\n")
            text_file.write(f"Target profile: {first_name} {last_name}\n")
            text_file.write(f"DOB context: {dob if dob else 'Not Provided'}\n")
            text_file.write(f"----------------------------------------\n")
            if sorted_adjs:
                text_file.write(f"Discovered Case Identifiers ({len(sorted_adjs)} total):\n")
                for rank, case_id in enumerate(sorted_adjs, start=1):
                    text_file.write(f"[{rank}] {case_id}\n")
            else:
                text_file.write("No matching ADJ case numbers captured yet.\n")
    except Exception as file_error:
        print(f"[WARNING] Live progress save to file failed: {str(file_error)}")

# ------------------------------------------------------------------
# HELPER: DETECT IF SESSION HAS BEEN KICKED BACK TO LOGIN GATEWAY
# ------------------------------------------------------------------
def is_on_gateway_page(page):
    try:
        current_url = page.url
        if "RequesterInformationCaptureScreen" in current_url:
            return True
        if page.locator("#fnam").count() > 0 and page.locator("#fnam").is_visible():
            return True
    except Exception:
        pass
    return False

# ------------------------------------------------------------------
# HELPER: RE-AUTHENTICATE THROUGH GATEWAY AND RESTORE SEARCH RESULTS
# ------------------------------------------------------------------
def reauthenticate_and_restore_search(page, first_name, last_name, dob):
    print("\n[SESSION RECOVERY] Portal session expired — re-authenticating through gateway...")

    handle_navigation_and_429(
        page,
        lambda: page.goto(
            "https://eams.dwc.ca.gov/WebEnhancement/RequesterInformationCaptureScreen.jsp?logout=out",
            wait_until="domcontentloaded"
        )
    )

    page.locator("#fnam").fill("MesaCare")
    page.locator("#lname").fill("Automation")
    page.locator("#em").fill("reports@mesacare.com")
    page.select_option("#reasonForReq", value="CASEPARTICIPANTSEARCH")
    page.wait_for_timeout(500)

    handle_navigation_and_429(page, lambda: page.locator("input[value='Next']").click())
    page.wait_for_timeout(2000)

    page.wait_for_selector("#firstname", timeout=10000)
    page.fill("#firstname", first_name)
    page.fill("#lastname", last_name)

    if dob:
        try:
            parts = dob.strip().split('/')
            normalized_dob = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}" if len(parts) == 3 else dob
        except Exception:
            normalized_dob = dob
        page.fill("#dob", normalized_dob)

    page.wait_for_timeout(500)
    handle_navigation_and_429(page, lambda: page.click("#searchBtn"))
    page.wait_for_timeout(2000)

    count = page.locator("text=View cases").count()
    print(f"[SESSION RECOVERY] Search restored. {count} result(s) visible again.")
    return count

# ------------------------------------------------------------------
# HELPER: INTERCEPT HTTP 429 RATE LIMITS AND RELOAD
# ------------------------------------------------------------------
def handle_navigation_and_429(page, action_callback=None):
    max_retries = 3
    base_delay = 5

    if action_callback:
        try:
            action_callback()
        except Exception as nav_err:
            print(f"[WARNING] Navigation raised an exception (likely 429 at transport level): {str(nav_err)}")
            print("[RECOVERY] Falling through to 429 detection check...")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    body_text = page.locator("body").inner_text()
    reload_button = page.locator("#reload-button")
    if "HTTP ERROR 429" not in body_text and reload_button.count() == 0:
        return True

    for attempt in range(max_retries):
        wait_time = base_delay * (2 ** attempt)
        print(f"\n[ALERT] HTTP 429 Rate Limit hit! Triggering fallback cool-down.")
        print(f"Waiting {wait_time} seconds before executing structural reload (Attempt {attempt + 1}/{max_retries})...")
        time.sleep(wait_time)

        print("Attempting session recovery reload sequence...")
        try:
            reload_button.first.click(timeout=3000)
        except Exception:
            print("[TIMEOUT] UI button unresponsive. Injecting hard script recovery refresh alternative...")
            page.evaluate("window.location.reload()")

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        body_text_check = page.locator("body").inner_text()
        if "HTTP ERROR 429" not in body_text_check:
            print("[SUCCESS] Rate limit cleared. Session recovered back to portal environment.")
            return "RELOADED"

    print("\n[FATAL] Exceeded maximum cooldown retry allocations. Portal access is heavily throttled.")
    return False

# ------------------------------------------------------------------
# AUTOMATION SCRAPE CORE FOR A SINGLE WORKER
# ------------------------------------------------------------------
def scrape_worker_profile(page, first_name, last_name, dob):
    print("\n====================================================")
    print("            TARGET PATIENT METADATA LOG              ")
    print("====================================================")
    print(f" First Name : {first_name}")
    print(f" Last Name  : {last_name}")
    print(f" D.O.B      : {dob if dob else '[NOT PROVIDED]'}")
    print("====================================================")

    all_discovered_adjs = set()
    save_progress_to_txt(first_name, last_name, dob, all_discovered_adjs)

    # --- GATEWAY ENTRY ---
    print("\nNavigating to gateway entry...")
    handle_navigation_and_429(
        page,
        lambda: page.goto(
            "https://eams.dwc.ca.gov/WebEnhancement/RequesterInformationCaptureScreen.jsp?logout=out",
            wait_until="domcontentloaded"
        )
    )

    page.locator("#fnam").fill("MesaCare")
    page.locator("#lname").fill("Automation")
    page.locator("#em").fill("reports@mesacare.com")
    page.select_option("#reasonForReq", value="CASEPARTICIPANTSEARCH")
    page.wait_for_timeout(500)

    handle_navigation_and_429(page, lambda: page.locator("input[value='Next']").click())
    page.wait_for_timeout(2000)

    # --- CRITERIA SEARCH INITIALIZATION ---
    try:
        search_page_status = handle_navigation_and_429(page)
        if search_page_status == "RELOADED":
            page.wait_for_timeout(2000)

        page.wait_for_selector("#firstname", timeout=10000)
        page.fill("#firstname", first_name)
        page.fill("#lastname", last_name)

        if dob:
            try:
                clean_dob = dob.strip()
                parts = clean_dob.split('/')
                normalized_dob = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}" if len(parts) == 3 else clean_dob
            except Exception:
                normalized_dob = dob
            print(f"Normalized DOB for form entry: {normalized_dob}")
            page.fill("#dob", normalized_dob)

        page.wait_for_timeout(500)
        handle_navigation_and_429(page, lambda: page.click("#searchBtn"))
        page.wait_for_timeout(2000)

    except Exception as e:
        print(f"\n[WARNING] Dynamic auto-fill error or field timeout: {str(e)}")
        print("[RECOVERY] Moving to intercept next operational payload stack item...")
        return

    # --- RESULTS COUNT & OPTIONAL DOB RE-RUN CHECK ---
    try:
        view_cases_links = page.locator("text=View cases")
        results_count = view_cases_links.count()
        print(f"Initial search returned {results_count} unique row result(s).")

        if results_count > 1 and not dob:
            print("\n[ATTENTION] Multiple records detected. Refinement recommended.")
            user_dob_input = input("Enter DOB (MM/DD/YYYY) to refine search [Or press ENTER to scrape all matches]: ").strip()

            if user_dob_input:
                dob = user_dob_input
                try:
                    parts = dob.split('/')
                    if len(parts) == 3:
                        dob = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
                except Exception:
                    pass

                print(f"Refilling search parameters with provided DOB: {dob}...")

                if not page.locator("#dob").is_visible():
                    new_search_btn = page.locator("input[value='New Search']")
                    if new_search_btn.count() > 0:
                        handle_navigation_and_429(page, lambda: new_search_btn.click())

                page.wait_for_selector("#firstname", timeout=5000)
                page.fill("#firstname", first_name)
                page.fill("#lastname", last_name)
                page.fill("#dob", dob)

                page.wait_for_timeout(500)
                handle_navigation_and_429(page, lambda: page.click("#searchBtn"))

                view_cases_links = page.locator("text=View cases")
                results_count = view_cases_links.count()

        # --- LOOPER CORE: FULL RESULT SET TRAVERSAL ---
        if results_count > 0:
            print(f"\nProceeding to loop and capture case numbers across all {results_count} match(es)...")

            i = 0
            while i < results_count:
                print(f"Extracting data from match [{i + 1}/{results_count}]...")

                # PRE-CLICK GATE: session kicked to gateway before we even click
                if is_on_gateway_page(page):
                    print(f"[SESSION RECOVERY] Gateway page detected at match {i + 1}. Re-authenticating...")
                    results_count = reauthenticate_and_restore_search(page, first_name, last_name, dob)
                    if results_count == 0:
                        print("[WARNING] Search returned no results after session recovery. Stopping loop.")
                        break
                    # Retry same index — do NOT increment i
                    continue

                current_link = page.locator("text=View cases").nth(i)
                nav_status = handle_navigation_and_429(page, lambda: current_link.click())
                page.wait_for_timeout(2000)

                # POST-CLICK GATE: click triggered a session drop to gateway
                if is_on_gateway_page(page):
                    print(f"[SESSION RECOVERY] Gateway detected after clicking match {i + 1}. Re-authenticating...")
                    results_count = reauthenticate_and_restore_search(page, first_name, last_name, dob)
                    if results_count == 0:
                        print("[WARNING] Search returned no results after session recovery. Stopping loop.")
                        break
                    # Retry same index — do NOT increment i
                    continue

                # -------------------------------------------------------
                # FIX: nav_status == "RELOADED" means the 429 fired
                # during the forward click and the page reloaded back to
                # the grid — we never reached the detail page.
                # Do NOT skip this entry. Retry the same index so the
                # detail for match [i+1] is still captured.
                # -------------------------------------------------------
                if nav_status == "RELOADED":
                    print(f"[RECOVERY] Hard reload landed back on grid. Retrying match [{i + 1}/{results_count}] — entry not skipped.")
                    page.wait_for_timeout(2000)
                    # Do NOT increment i — fall back to top of while loop
                    continue

                # --- DETAIL PAGE: extract ADJ case numbers ---
                sub_html = page.content()
                found_adjs = re.findall(r'ADJ\d+', sub_html)

                if found_adjs:
                    all_discovered_adjs.update(found_adjs)
                    save_progress_to_txt(first_name, last_name, dob, all_discovered_adjs)

                print("Returning to grid...")
                previous_btn = page.locator("input[value='Previous']")
                if previous_btn.count() > 0:
                    back_status = handle_navigation_and_429(page, lambda: previous_btn.click())
                else:
                    back_status = handle_navigation_and_429(page, lambda: page.go_back())

                if back_status == "RELOADED":
                    page.wait_for_timeout(1000)
                else:
                    page.wait_for_timeout(1500)

                # POST-BACK GATE: going back landed on gateway
                if is_on_gateway_page(page):
                    print(f"[SESSION RECOVERY] Gateway detected after returning to grid at match {i + 1}. Re-authenticating...")
                    results_count = reauthenticate_and_restore_search(page, first_name, last_name, dob)
                    if results_count == 0:
                        print("[WARNING] Search returned no results after session recovery. Stopping loop.")
                        break
                    # This match was already extracted successfully — advance
                    i += 1
                    continue

                i += 1

        else:
            print("[WARNING] Zero 'View cases' endpoints identified. Checking primary text snapshot details...")
            page_html = page.content()
            found_adjs = sorted(list(set(re.findall(r'ADJ\d+', page_html))))
            if found_adjs:
                all_discovered_adjs.update(found_adjs)
                save_progress_to_txt(first_name, last_name, dob, all_discovered_adjs)

        print(f"\n[SUCCESS] Extraction sequence finalized for {first_name} {last_name}.")

    except Exception as capture_error:
        print(f"[ERROR] Advanced auto-loop extraction pipeline dropped process tracking: {str(capture_error)}")

# ------------------------------------------------------------------
# MAIN EXECUTION ORCHESTRATOR INTERFACE
# ------------------------------------------------------------------
def main():
    print("====================================================")
    print("       EAMS AUTOMATION PIPELINE CONSOLE ENGINE      ")
    print("====================================================")
    print("1. Standard Manual Run Mode (Single Injured Worker)")
    print("2. Batch CSV Profiler Mode (Bulk Ingest File)")
    print("----------------------------------------------------")

    mode_selection = input("Select processing layout execution mode (1 or 2): ").strip()
    workers_to_process = []

    if mode_selection == "1":
        first_name = input("\nEnter Injured Worker First Name: ").strip()
        last_name = input("Enter Injured Worker Last Name: ").strip()
        dob = input("Enter DOB (MM/DD/YYYY) [Or press ENTER to skip]: ").strip()

        if not first_name or not last_name:
            print("[FATAL] Insufficient identity parameters provided. Halting execution.")
            sys.exit()

        workers_to_process.append({
            'first_name': first_name,
            'last_name': last_name,
            'dob': dob if dob else None
        })

    elif mode_selection == "2":
        csv_filename = input("\nEnter the target filename of your layout profiles CSV (e.g., records.csv): ").strip()
        if not os.path.exists(csv_filename):
            print(f"[FATAL] Target profile asset path '{csv_filename}' not found in runtime directory.")
            sys.exit()

        try:
            with open(csv_filename, mode='r', encoding='utf-8-sig') as csv_file:
                reader = csv.DictReader(csv_file)
                header_map = {re.sub(r'[\s_\-]', '', str(col)).lower(): col for col in reader.fieldnames}

                required_keys = ['firstname', 'lastname', 'dob']
                if not all(k in header_map for k in required_keys):
                    print("[FATAL] CSV structural layout mismatch. Must explicitly contain 'First Name', 'Last Name', and 'DOB' columns.")
                    sys.exit()

                for row in reader:
                    f_name = row[header_map['firstname']].strip()
                    l_name = row[header_map['lastname']].strip()
                    d_obj = row[header_map['dob']].strip()

                    if f_name and l_name:
                        workers_to_process.append({
                            'first_name': f_name,
                            'last_name': l_name,
                            'dob': d_obj if d_obj else None
                        })

            print(f"[✓] Data verification complete. Queued {len(workers_to_process)} records for pipeline scraping.")

        except Exception as csv_read_err:
            print(f"[FATAL] Error structural parsing of target file data records: {str(csv_read_err)}")
            sys.exit()
    else:
        print("[INVALID] Non-standard assignment parameter specified. Exiting context loop.")
        sys.exit()

    input(f"\nReady to initialize. Press [ENTER] to spin up the automation browser pipeline...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        for rank, worker in enumerate(workers_to_process, start=1):
            print(f"\n[PROGRESS] Processing Profile Execution Stack [{rank}/{len(workers_to_process)}]")
            scrape_worker_profile(page, worker['first_name'], worker['last_name'], worker['dob'])

        print("\n================================================================")
        print("                LOOKUP BATCH COMPLETE: PAUSED                  ")
        print("================================================================")
        print(" Review the open window. Press [ENTER] in this terminal to exit.")
        print("================================================================")
        input()
        browser.close()

if __name__ == "__main__":
    main()

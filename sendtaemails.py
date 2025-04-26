# v3.0
import requests, html, time, re, sys, os, subprocess, threading, argparse
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from queue import Queue
from tqdm import tqdm
import json
import hashlib
from colorama import init, Fore
init(autoreset=True)

hash_set = set()

def parse_args():
    parser = argparse.ArgumentParser(description="Faculty Email Scraper & Sender")
    parser.add_argument("--economics", action="store_true", help="Scrape Economics faculty")
    parser.add_argument("--kelley", action="store_true", help="Scrape Kelley faculty")
    parser.add_argument("--oneill", action="store_true", help="Scrape Oneill faculty")
    parser.add_argument("--luddy", action="store_true", help="Scrape Luddy/Informatics faculty")
    parser.add_argument("--pdf", type=str, help="Path to the resume PDF")
    parser.add_argument("--name", type=str, help="Sender full name")
    parser.add_argument("--test", action="store_true", help="Enable test mode")
    parser.add_argument("--email", type=str, help="Test mode recipient email")
    parser.add_argument("--subject", type=str, help="Email subject line")
    parser.add_argument("--body", type=str, help="Email body (text or path to .txt/.pdf)")
    parser.add_argument("--config", type=str, help="Path to config.json file")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed emails from previous run")
    parser.add_argument("--getinfo", action="store_true", help="Dry run: Display scraped info without sending")
    return parser.parse_args()

def load_config_if_available():
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            with open(sys.argv[idx + 1]) as f:
                return json.load(f)
    return {}

args = parse_args()
config = load_config_if_available()

def get_config_value(key, default=None):
    return getattr(args, key, None) or config.get(key, default)

PDF_PATH = get_config_value("pdf", "/Users/gokulkaarthick/tools/TARA/Gokul_Kaarthick_Shanmugam_Assistantship_3YoE_Resume.pdf")
FROM_NAME = get_config_value("name", "Gokul Kaarthick Shanmugam")
TO_EMAIL_TEST = get_config_value("email", None)
USE_TEST_MODE = get_config_value("test", False)
EMAIL_SUBJECT = get_config_value("subject", "Inquiry Regarding Graduate Teaching Assistantship for the Upcoming Semester")
BODY_INPUT = get_config_value("body", None)

def validate_args():
    if not (args.economics or args.kelley or args.oneill or args.luddy):
        print("Error: At least one scraping flag must be specified.")
        sys.exit(1)
    if args.test and not args.email:
        print("Error: --email is required in test mode.")
        sys.exit(1)

validate_args()

if not Path(PDF_PATH).exists():
    print(f"Error: PDF file '{PDF_PATH}' not found.")
    sys.exit(1)

DEFAULT_BODY = f"""Dear Professor {{name}},\n\nMy name is {FROM_NAME}, a Master's student in the Computer Science Department at the Luddy School, Indiana University Bloomington. With over three years of experience in software development, I have a strong foundation in Cloud and DevOps. I am eager to contribute to your teaching or research efforts and further deepen my expertise through hands-on academic involvement.\n\nSpecialization: Software Development, Virtualization & Cloud (Kubernetes, Kafka), Programming Languages, Systems Fundamentals (Operating Systems, Computer Architecture, Computer Networks)\n\nI have attached my resume for your reference and would appreciate the opportunity to connect if any roles are available.\n\nThank you for your time and consideration.\n\nSincerely,\n{FROM_NAME}"""

LOG_FILE = "email_queue_errors.log"
FAILED_QUEUE_FILE = "failed_emails.txt"
MAX_THREADS = 10
RESTART_AFTER = 150
MAX_RETRIES = 2

HEADERS = {'User-Agent': 'Mozilla/5.0'}
professors_by_school = {}
unique_emails = set()
email_queue = Queue()
email_sent_counter = 0
email_count_lock = threading.Lock()
lock = threading.Lock()

def read_body_content(prof_name):
    if BODY_INPUT:
        path = Path(BODY_INPUT)
        if path.exists():
            if path.suffix == ".pdf":
                from PyPDF2 import PdfReader
                reader = PdfReader(str(path))
                return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
            else:
                return path.read_text()
        else:
            return BODY_INPUT.replace("{name}", prof_name)
    return DEFAULT_BODY.replace("{name}", prof_name)

def ensure_mail_running():
    subprocess.run(['open', '-a', 'Mail'])
    time.sleep(5)

def restart_mail():
    subprocess.run(['osascript', '-e', 'quit app "Mail"'])
    time.sleep(5)
    subprocess.run(['open', '-a', 'Mail'])
    time.sleep(5)

def send_email(professor_name, recipient_email, visible_flag=False):
    body = read_body_content(professor_name)
    if not Path(PDF_PATH).exists():
        raise FileNotFoundError(f"Resume PDF '{PDF_PATH}' is missing.")
    applescript = f'''
      tell application "Mail"
          set newMessage to make new outgoing message with properties {{subject:"{EMAIL_SUBJECT}", content:"{body}", visible:{str(visible_flag).lower()}}}
          tell newMessage
              make new to recipient at end of to recipients with properties {{address:"{recipient_email}"}}
              make new attachment with properties {{file name:"{PDF_PATH}"}} at after the last paragraph of content
              send
          end tell
      end tell
    '''
    for attempt in range(MAX_RETRIES + 1):
        try:
            subprocess.run(["osascript", "-e", applescript], check=True)
            return "Success"
        except subprocess.CalledProcessError:
            time.sleep(1.5)
    return "Failed"

def append_to_emailed_emails(email, filepath="emailed_professors.txt"):
    with open(filepath, "a") as f:
        f.write(email + "\n")

def worker_test(progress):
    global email_sent_counter
    while not email_queue.empty():
        prof = email_queue.get()
        name = prof['name']
        email = prof['email']
        target_email = TO_EMAIL_TEST
        try:
            for attempt in range(MAX_RETRIES + 1):
                status = send_email(name, target_email)
                if status == "Success":
                    print(Fore.GREEN + f"[SENT] {name} -> {email}")
                    break
                time.sleep(1.5)
        except Exception as e:
            print(Fore.RED + f"[ERROR] {name}: {e}")
        finally:
            email_queue.task_done()
            progress.update(1)

def worker_real(progress):
    global email_sent_counter
    while not email_queue.empty():
        prof = email_queue.get()
        name = prof['name']
        email = prof['email']
        if email in already_emailed:
            email_queue.task_done()
            continue
        try:
            for attempt in range(MAX_RETRIES + 1):
                status = send_email(name, email)
                if status == "Success":
                    append_to_emailed_emails(email)
                    break
                time.sleep(1.5)
            with email_count_lock:
                email_sent_counter += 1
                if email_sent_counter % RESTART_AFTER == 0:
                    restart_mail()
            if status == "Success":
                with lock:
                    append_to_emailed_emails(email)
            if status != "Success":
                with open(LOG_FILE, "a") as log:
                    masked = email[:2] + "*****" + email[email.find("@"):]
                    log.write(f"{status} (Attempt {attempt + 1}): {name} -> {masked}\n")
                with open(FAILED_QUEUE_FILE, "a") as failed:
                    failed.write(f"{name}||{email}\n")
        except Exception as e:
            with open(LOG_FILE, "a") as log:
                log.write(f"[ERROR] {name}: {e}")
        finally:
            email_queue.task_done()
            progress.update(1)

def add_profile(school, name, email):
    if email and email.endswith("@iu.edu"):
        unique_key = f"{school.lower()}::{name.lower()}::{email.lower()}"
        hash_digest = hashlib.md5(unique_key.encode()).hexdigest()
        if hash_digest in hash_set:
            return
        hash_set.add(hash_digest)
        if email not in unique_emails:
            unique_emails.add(email)
            professors_by_school.setdefault(school, []).append({'name': name, 'email': email})

def scrape_econ(url, school_name):
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, 'html.parser')
    for profile in tqdm(soup.select('article.profile.item'), desc=f"Scraping {school_name}", ncols=70):
        name_tag = profile.find('h1')
        email_tag = profile.select_one('li.icon-email span')
        if name_tag and email_tag:
            name = name_tag.get_text(strip=True)
            email = html.unescape(email_tag.decode_contents()).strip()
            add_profile(school_name, name, email)

def scrape_kelley():
    url = "https://kelley.iu.edu/faculty-research/faculty-directory/index.html"
    driver = webdriver.Chrome()
    driver.get(url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "searchFaculty")))
    try:
        driver.find_element(By.ID, "status-active").click()
        driver.find_element(By.ID, "campus-bloomington").click()
    except: pass
    for box_id in ["checkbox-FC1", "checkbox-FC3", "checkbox-FC4", "checkbox-FC6", "checkbox-FC7"]:
        try:
            box = driver.find_element(By.ID, box_id)
            if not box.is_selected():
                box.click()
        except: continue
    driver.find_element(By.ID, "searchFaculty").click()
    time.sleep(4)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()
    for entry in soup.select(".faculty-directory"):
        name_tag = entry.select_one("h3 a")
        email_tag = entry.select_one("a[href^='mailto']")
        if name_tag and email_tag:
            name = name_tag.get_text(strip=True)
            email = email_tag.get("href").replace("mailto:", "").strip()
            add_profile("Kelley", name, email)

def scrape_oneill():
    urls = {
        "Full-time": "https://oneill.indiana.edu/faculty-research/directory/index.html?type=Faculty",
        "Part-time": "https://oneill.indiana.edu/faculty-research/directory/index.html?type=Part-time%20Faculty",
        "Affiliate": "https://oneill.indiana.edu/faculty-research/directory/index.html?type=Affiliate%20faculty",
    }
    for label, url in urls.items():
        driver = webdriver.Chrome()
        driver.get(url)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".profile.feed-item")))
            time.sleep(2)
            profiles = driver.find_elements(By.CSS_SELECTOR, ".profile.feed-item")
            for prof in profiles:
                try:
                    name_el = prof.find_element(By.CSS_SELECTOR, "p.no-margin.title a")
                    name = name_el.text.strip()
                    email_el = prof.find_element(By.PARTIAL_LINK_TEXT, "@iu.edu")
                    email = email_el.text.strip()
                    add_profile("Oneill", name, email)
                except: continue
        except: pass
        driver.quit()

def scrape_luddy_and_informatics_profiles():
    base_urls = {
        "Luddy": "https://luddy.indiana.edu/research/faculty-directory.html?type=",
        "Informatics": "https://informatics.indiana.edu/faculty-directory/index.html?type="
    }
    categories = {"2": "Core", "5": "Adjunct", "24": "Affiliate"}
    driver = webdriver.Chrome()
    for school, base_url in base_urls.items():
        for type_code in categories:
            if school == "Luddy" and type_code == "24":
                continue
            url = f"{base_url}{type_code}"
            if school == "Informatics":
                url += "&aca_dept=3"
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/contact/profile/index.html']")))
            soup = BeautifulSoup(driver.page_source, "html.parser")
            for link in soup.select("a[href^='/contact/profile/index.html']"):
                profile_url = ("https://informatics.indiana.edu" if school == "Informatics" else "https://luddy.indiana.edu") + link['href']
                get_professor_details(driver, profile_url, school, link.text.strip())
    driver.quit()

def get_professor_details(driver, profile_url, school, fallback_name):
    driver.get(profile_url)
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    name = soup.find("h1").get_text(strip=True)
    name = re.sub(r"^Profile of\s+", "", name)
    if school == "Informatics":
        name = fallback_name
    email_tag = soup.find("a", href=lambda href: href and "mailto:" in href)
    email = email_tag.get_text(strip=True) if email_tag else None
    if email:
        add_profile(school, name, email)

def load_emailed_emails(filepath="emailed_professors.txt"):
    try:
        with open(filepath, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

if __name__ == "__main__":
    BACKUP_QUEUE_FILE = "email_queue_backup.txt"
    skip_scraping = False

    if "--retry-failed" in sys.argv and os.path.exists(FAILED_QUEUE_FILE):
        with open(FAILED_QUEUE_FILE, "r") as f:
            for line in f:
                name, email = line.strip().split("||")
                if email not in already_emailed:
                    email_queue.put({'name': name, 'email': email})
        os.remove(FAILED_QUEUE_FILE)
        skip_scraping = True

    if os.path.exists(BACKUP_QUEUE_FILE):
        already_emailed = load_emailed_emails()
        with open(BACKUP_QUEUE_FILE, "r") as bkp:
            for line in bkp:
                try:
                    name, email = line.strip().split("||")
                    if email not in already_emailed:
                        email_queue.put({'name': name, 'email': email})
                except: continue
        print("Restored email queue from backup. Skipping scraping.")
        skip_scraping = True

    already_emailed = load_emailed_emails()

    if not skip_scraping:
        try:
            if args.economics:
                econ_urls = {
                    "Economics core": "https://economics.indiana.edu/about/faculty/index.html",
                    "Economics adjunct": "https://economics.indiana.edu/about/adjuncts/index.html",
                    "Economics emeriti": "https://economics.indiana.edu/about/emeriti/index.html"
                }
                for name, url in econ_urls.items():
                    scrape_econ(url, name)

            if args.kelley:
                scrape_kelley()

            if args.oneill:
                scrape_oneill()

            if args.luddy:
                scrape_luddy_and_informatics_profiles()

            with open(BACKUP_QUEUE_FILE, "w") as bkp:
                for school, profs in professors_by_school.items():
                    for prof in profs:
                        if prof['email'] not in already_emailed:
                            email_queue.put(prof)
                            bkp.write(f"{prof['name']}||{prof['email']}\n")

            if args.getinfo:
                print("\n[DRY RUN] Scraped Professors:")
                for school, profs in professors_by_school.items():
                    print(f"\n{school}")
                    for prof in profs:
                        if prof['email'] not in already_emailed:
                            print(f" - {prof['name']} ({prof['email']})")
                sys.exit(0)

            ensure_mail_running()

            progress = tqdm(total=email_queue.qsize(), desc="Sending Emails", ncols=70)
            threads = []
            worker_fn = worker_test if USE_TEST_MODE else worker_real
            for _ in range(min(MAX_THREADS, email_queue.qsize())):
                t = threading.Thread(target=worker_fn, args=(progress,))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
            progress.close()

            print("=" * 40)
            print("Summary:")
            print(f"Total unique emails collected: {len(unique_emails)}")
            print(f"Total emails sent: {email_sent_counter}")
            print(f"Mode: {'Test' if USE_TEST_MODE else 'Real'}")
            print(f"Errors logged to: {LOG_FILE}")
            print("=" * 40)

            if os.path.exists(BACKUP_QUEUE_FILE):
                os.remove(BACKUP_QUEUE_FILE)

        except Exception as e:
            with open(LOG_FILE, "a") as log:
                log.write(f"Fatal crash: {e}\n")
            time.sleep(5)
            python = sys.executable
            os.execl(python, python, *sys.argv)

















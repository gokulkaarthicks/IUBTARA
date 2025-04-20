#v2.0
import requests, html, time, re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import subprocess
import threading
from queue import Queue

USE_TEST_MODE = True  # or False

HEADERS = {'User-Agent': 'Mozilla/5.0'}
professors_by_school = {}
unique_emails = set()

def add_profile(school, name, email):
    if email and email not in unique_emails:
        unique_emails.add(email)
        professors_by_school.setdefault(school, []).append({'name': name, 'email': email})

# 1. Economics
def scrape_econ(url, school_name):
    if "emeriti" in url.lower():
        return
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, 'html.parser')
    for profile in soup.select('article.profile.item'):
        name_tag = profile.find('h1')
        email_tag = profile.select_one('li.icon-email span')
        if name_tag and email_tag:
            name = name_tag.get_text(strip=True)
            email = html.unescape(email_tag.decode_contents()).strip()
            add_profile(school_name, name, email)

# 2. Kelley
def scrape_kelley():
    url = "https://kelley.iu.edu/faculty-research/faculty-directory/index.html"
    driver = webdriver.Chrome()
    driver.get(url)

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "searchFaculty")))

    try:
        active_status = driver.find_element(By.ID, "status-active")
        if not active_status.is_selected():
            active_status.click()
    except: pass

    try:
        bloomington = driver.find_element(By.ID, "campus-bloomington")
        if not bloomington.is_selected():
            bloomington.click()
    except: pass

    for box_id in ["checkbox-FC1", "checkbox-FC3", "checkbox-FC4", "checkbox-FC6", "checkbox-FC7"]:
        try:
            box = driver.find_element(By.ID, box_id)
            if not box.is_selected():
                box.click()
        except: continue

    try:
        driver.find_element(By.ID, "searchFaculty").click()
    except: pass

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

# 3. Oneill
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
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".profile.feed-item"))
            )
            time.sleep(2)

            profiles = driver.find_elements(By.CSS_SELECTOR, ".profile.feed-item")
            for prof in profiles:
                try:
                    name_el = prof.find_element(By.CSS_SELECTOR, "p.no-margin.title a")
                    name = name_el.text.strip()
                    try:
                        email_el = prof.find_element(By.PARTIAL_LINK_TEXT, "@iu.edu")
                        email = email_el.text.strip()
                        add_profile("Oneill", name, email)
                    except:
                        print(f"Email not found for: {name}")
                        continue
                except Exception as inner_e:
                    print(f"Failed to extract name/email: {inner_e}")
                    continue

        except Exception as outer_e:
            print(f"No profiles found at {url} – {outer_e}")

        driver.quit()

# 4. Luddy & Informatics

def get_professor_details(driver, profile_url, school, fallback_name=None):
    driver.get(profile_url)
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    name = soup.find("h1").get_text(strip=True)
    name = re.sub(r"^Profile of\s+", "", name)

    if school == "Informatics" and fallback_name:
        name = fallback_name.strip()

    email_tag = soup.find("a", href=lambda href: href and "mailto:" in href)
    email = email_tag.get_text(strip=True) if email_tag else None

    if email:
        add_profile(school, name, email)
    else:
        print(f"Email not found for: {name}")

def scrape_luddy_and_informatics_profiles():
    base_urls = {
        "Luddy": "https://luddy.indiana.edu/research/faculty-directory.html?type=",
        "Informatics": "https://informatics.indiana.edu/faculty-directory/index.html?type="
    }
    categories = {"2": "Core", "5": "Adjunct", "24": "Affiliate"}

    driver = webdriver.Chrome()

    for school, base_url in base_urls.items():
        for type_code, label in categories.items():
            if school == "Luddy" and type_code == "24":
                continue

            full_url = f"{base_url}{type_code}"
            if school == "Informatics":
                full_url += "&aca_dept=3"

            driver.get(full_url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='/contact/profile/index.html']"))
            )
            soup = BeautifulSoup(driver.page_source, "html.parser")
            profile_links = soup.select("a[href^='/contact/profile/index.html']")

            if not profile_links:
                print("No profiles found.")
                continue

            for profile_link in profile_links:
                profile_url = (
                    f"https://informatics.indiana.edu{profile_link['href']}"
                    if school == "Informatics"
                    else f"https://luddy.indiana.edu{profile_link['href']}"
                )
                fallback_name = profile_link.text  # use visible link text for Informatics
                get_professor_details(driver, profile_url, school, fallback_name)
                time.sleep(0.5)

    driver.quit()

def send_email(professor_name, recipient_email):
    recipient_email = recipient_email
    subject = "Inquiry Regarding Graduate Teaching Assistantship for the Upcoming Semester"
    body = f"""Dear Professor {professor_name},

My name is Gokul Kaarthick Shanmugam, a Master's student in the Computer Science Department at the Luddy School, Indiana University Bloomington. With over three years of experience in software development, I have a strong foundation in Cloud and DevOps. I am eager to contribute to your teaching or research efforts and further deepen my expertise through hands-on academic involvement.

Specialization: Software Development, Virtualization & Cloud (Kubernetes, Kafka), Programming Languages, Systems Fundamentals (Operating Systems, Computer Architecture, Computer Networks)

I have attached my resume for your reference and would appreciate the opportunity to connect if any roles are available.

Thank you for your time and consideration.

Sincerely,
Gokul Kaarthick Shanmugam
""".lstrip().lstrip().lstrip()
    
    attachment_path = "/Users/gokulkaarthick/tools/TARA/Gokul_Kaarthick_Shanmugam_Assistantship_3YoE_Resume.pdf"

    send_email_via_apple_mail(recipient_email, subject, body, attachment_path)


def send_email_via_apple_mail(recipient_email, subject, body, attachment_path):
    applescript = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:true}}
        tell newMessage
            make new to recipient at end of to recipients with properties {{address:"{recipient_email}"}}
            -- Attach the file
            make new attachment with properties {{file name:"{attachment_path}"}} at after the last paragraph of content
            send
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", applescript])
    print(f"Email sent to {recipient_email} with attachment {attachment_path}")

def load_emailed_emails(filepath="emailed_professors.txt"):
    try:
        with open(filepath, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def append_to_emailed_emails(email, filepath="emailed_professors.txt"):
    with open(filepath, "a") as f:
        f.write(email + "\n")

# Run All

econ_urls = {
    "Economics core": "https://economics.indiana.edu/about/faculty/index.html",
    "Economics adjunct": "https://economics.indiana.edu/about/adjuncts/index.html",
    "Economics emeriti": "https://economics.indiana.edu/about/emeriti/index.html"
}

for name, url in econ_urls.items():
    scrape_econ(url, name)

scrape_kelley()
scrape_oneill()
scrape_luddy_and_informatics_profiles()

already_emailed = load_emailed_emails()

q = Queue()
lock = threading.Lock()
MAX_THREADS = 100

def worker_test():
    while not q.empty():
        prof = q.get()
        name = prof['name']
        test_email = "goshan@iu.edu"

        try:
            print(f"[TEST] Sending to: {name} -> {test_email}")
            send_email(name, test_email)
        except Exception as e:
            print(f"[TEST] Error sending to {test_email}: {e}")
        finally:
            q.task_done()

def worker_real():
    while not q.empty():
        prof = q.get()
        name = prof['name']
        email = prof['email']

        with lock:
            if email in already_emailed:
                q.task_done()
                return

        try:
            print(f"Sending to: {name} -> {email}")
            #send_email(name, email)
            with lock:
                append_to_emailed_emails(email)
        except Exception as e:
            print(f"Error sending to {email}: {e}")
        finally:
            q.task_done()

for school, profs in professors_by_school.items():
    for prof in profs:
        q.put(prof)

threads = []
worker_fn = worker_test if USE_TEST_MODE else worker_real

for _ in range(min(MAX_THREADS, q.qsize())):
    t = threading.Thread(target=worker_fn)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print(f"\nTotal unique emails collected: {len(unique_emails)}")
# v1.0

from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
from selenium.webdriver.common.keys import Keys
import re
import openai
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import subprocess
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

base_url = "https://luddy.indiana.edu/research/faculty-directory.html?&type=2&alpha=undefined"
base_url = "https://informatics.indiana.edu/faculty-directory/index.html?&type=2&aca_dept=3"
base_url = "https://informatics.indiana.edu/faculty-directory/index.html?&type=5&aca_dept=3"
base_url = "https://informatics.indiana.edu/faculty-directory/index.html?&type=4&aca_dept=3"
base_url = "https://informatics.indiana.edu/faculty-directory/index.html?&type=24&aca_dept=3"

driver = webdriver.Chrome()

EMAIL_ADDRESS = "YOUR EMAIL"
EMAIL_PASSWORD = "YOUR PASSWORD" 

newly_sent_emails = []
def get_faculty_directory():
    driver.get(base_url)
    time.sleep(5)
    return BeautifulSoup(driver.page_source, "html.parser")

def get_professor_details(profile_url):
    driver.get(profile_url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    name = soup.find("h1").get_text(strip=True)
    name = re.sub(r"^Profile of\s+", "", name)
    email_tag = soup.find("a", href=lambda href: href and "mailto:" in href)
    email = email_tag.get_text(strip=True) if email_tag else None
    
    sent_emails = []

    if email:
        if email in sent_emails:
            print(f"Skipping email to {email}, already sent.")
            pass
        else:
            print (name)
            print (email)
            #send_email(name, email)
            #newly_sent_emails.append(email) 
    else:
        print(f"No email found for Professor {name}")


def scrape_faculty_profiles():
    soup = get_faculty_directory()
    
    profile_links = soup.select("a[href^='/contact/profile/index.html']")
    if not profile_links:
        print("No profile links found. Please verify the page content.")
    
    for profile_link in profile_links:
        profile_url = f"https://luddy.indiana.edu{profile_link['href']}"
        print("Visiting profile:", profile_url)
        get_professor_details(profile_url)
        time.sleep(1)
    
    print("\nNewly sent emails:")
    print(newly_sent_emails)

scrape_faculty_profiles()

driver.quit()

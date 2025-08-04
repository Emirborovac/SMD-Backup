import os
import time
import json
import requests
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import logging

def extract_facebook_metadata(driver):
    """Extract title and description from a Facebook video post"""
    logging.info("Extracting Facebook video metadata")
    
    try:
        # Wait for content to load fully
        time.sleep(3)
        
        # Use BeautifulSoup to parse the page
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Default title and description
        title = "Facebook Video"
        description = "No description available"
        
        # Look for title in various possible elements
        # Try meta tags first (most reliable)
        meta_title = soup.find('meta', property='og:title')
        if meta_title and meta_title.get('content'):
            title = meta_title.get('content')
        
        # Look for description
        # First try meta description
        meta_desc = soup.find('meta', property='og:description')
        if meta_desc and meta_desc.get('content'):
            description = meta_desc.get('content')
        else:
            # Try to find post text - Facebook has many different layouts, so try a few patterns
            # Main content areas where posts might be
            content_divs = soup.find_all('div', attrs={'data-ad-comet-preview': 'message'})
            if content_divs:
                for div in content_divs:
                    text = div.get_text().strip()
                    if text:
                        description = text
                        break
            
            # Another common pattern
            if description == "No description available":
                post_text_divs = soup.find_all('div', {'data-ad-preview': 'message'})
                for div in post_text_divs:
                    text = div.get_text().strip()
                    if text:
                        description = text
                        break
        
        # If we still don't have a description, try XPath for common patterns
        if description == "No description available":
            try:
                # Common XPath for post content
                desc_xpath = "//div[contains(@aria-label, 'Comment')]/preceding-sibling::div[1]"
                desc_element = driver.find_element(By.XPATH, desc_xpath)
                if desc_element:
                    description = desc_element.text.strip()
            except:
                pass
                
        return {
            "title": title,
            "description": description
        }
    except Exception as e:
        logging.error(f"Error extracting Facebook metadata: {e}")
        return {
            "title": "Facebook Video",
            "description": "Error extracting description"
        }

def download_facebook_video(post_url, download_dir):
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--window-size=1920,1080")
    
    # Add these options to avoid the user-data-dir conflict
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Create a unique user data directory for each instance
    import tempfile
    user_data_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    # Additionally, add disable-gpu for better headless performance on some systems
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        # Rest of your function remains the same
        driver.get(post_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "script")))
        
        metadata = extract_facebook_metadata(driver)
        video_url, audio_url = fetch_facebook_video_url(post_url, driver)
        
        if video_url and audio_url:
            output_file = os.path.join(download_dir, f"facebook_video_{int(time.time())}.mp4")
            download_and_merge(video_url, audio_url, output_file)
            
            return {
                "file_path": output_file,
                "title": metadata["title"],
                "description": metadata["description"]
            }
        else:
            return None
    finally:
        driver.quit()
        # Clean up the temporary directory
        import shutil
        try:
            shutil.rmtree(user_data_dir)
        except:
            pass
        
def fetch_facebook_video_url(post_url, driver):
    driver.get(post_url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "script")))
    
    scripts = driver.find_elements(By.TAG_NAME, "script")
    video_urls = []
    audio_url_found = None
    for script in scripts:
        script_content = script.get_attribute("innerHTML")
        if script_content:
            try:
                json_data = json.loads(script_content)
                video_urls, audio_url_found = extract_urls_with_mime_types(json_data, video_urls, audio_url_found)
            except json.JSONDecodeError:
                continue
    video_url = video_urls[1] if len(video_urls) > 1 else video_urls[0] if video_urls else None
    return video_url, audio_url_found

def extract_urls_with_mime_types(data, video_urls, audio_url_found):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ["mime_type", "mimeType"]:
                if value == "video/mp4":
                    video_url = data.get('base_url') or data.get('url')
                    if video_url:
                        video_urls.append(video_url)
                elif value == "audio/mp4" and not audio_url_found:
                    audio_url_found = data.get('base_url') or data.get('url')
            elif isinstance(value, (dict, list)):
                video_urls, audio_url_found = extract_urls_with_mime_types(value, video_urls, audio_url_found)
    elif isinstance(data, list):
        for item in data:
            video_urls, audio_url_found = extract_urls_with_mime_types(item, video_urls, audio_url_found)
    return video_urls, audio_url_found

def download_and_merge(video_url, audio_url, output_file):
    try:
        command = [
            'ffmpeg', 
            '-i', video_url, 
            '-i', audio_url, 
            '-c:v', 'copy', 
            '-c:a', 'aac', 
            '-strict', 'experimental', 
            output_file
        ]
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        return None
    

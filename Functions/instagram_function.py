import os
import time
import re
import json
import requests
import logging
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import uuid  # For generating unique filenames
from bs4 import BeautifulSoup  # Added BeautifulSoup for HTML parsing
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set to INFO to capture important events only
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/instagram_reel_downloader.log"),  # Log to file
        logging.StreamHandler()  # Also output to console
    ]
)

# Cookie directory path
COOKIE_DIR = "./cookies/instagram_cookies/"
LAST_COOKIE_TRACKER = "./cookies/last_cookie.txt"

# Function to get the next cookie file in rotation
def get_next_cookie_file():
    # Get all cookie files in the directory
    cookie_files = [f for f in os.listdir(COOKIE_DIR) if f.endswith('.txt') or f.endswith('.json')]
    
    if not cookie_files:
        logging.error("No cookie files found in the directory")
        return None
    
    # If there's a last cookie tracker file, read it
    last_cookie = None
    if os.path.exists(LAST_COOKIE_TRACKER):
        try:
            with open(LAST_COOKIE_TRACKER, 'r') as f:
                last_cookie = f.read().strip()
        except Exception as e:
            logging.error(f"Error reading last cookie tracker: {e}")
    
    # Find the next cookie in rotation
    if last_cookie and last_cookie in cookie_files:
        current_index = cookie_files.index(last_cookie)
        next_index = (current_index + 1) % len(cookie_files)
        next_cookie = cookie_files[next_index]
    else:
        # If no last cookie or it's not found, start from beginning
        next_cookie = cookie_files[0]
    
    # Save the current cookie as the last used
    try:
        with open(LAST_COOKIE_TRACKER, 'w') as f:
            f.write(next_cookie)
    except Exception as e:
        logging.error(f"Error writing to last cookie tracker: {e}")
    
    logging.info(f"Selected cookie file: {next_cookie}")
    return os.path.join(COOKIE_DIR, next_cookie)

# Function to save the complete HTML content of the page
def save_complete_html(driver, save_path):
    html_source = driver.page_source
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(html_source)

# Function to extract the 720p video URL based on the shortcode for Instagram
def extract_instagram_720p_video_url(file_path, shortcode):
    logging.info(f"Extracting video URL using shortcode: {shortcode}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        shortcode_pattern = re.compile(r'{"items":\[{"code":"' + re.escape(shortcode) + r'".*?"video_versions":(\[.*?\])')
        shortcode_match = shortcode_pattern.search(html_content)
        if shortcode_match:
            video_versions_json = shortcode_match.group(1)
            video_versions = json.loads(video_versions_json)
            # Try to find the 720p video first
            for video in video_versions:
                if video.get("width") == 720:
                    video_url = video.get("url").replace("\\u0026", "&")
                    logging.info(f"720p video URL found: {video_url}")
                    return video_url
            
            # If 720p isn't found, find the next best resolution (highest available)
            sorted_videos = sorted(video_versions, key=lambda x: x.get("width", 0), reverse=True)
            if sorted_videos:
                best_available_video = sorted_videos[0]
                video_url = best_available_video.get("url").replace("\\u0026", "&")
                logging.info(f"720p not found. Using lower resolution: {best_available_video.get('width')}px")
                return video_url
        
        logging.warning(f"Video URL not found for shortcode: {shortcode}")
    except Exception as e:
        logging.error(f"Error extracting video URL: {e}")
        return None
    return None

# Function to extract the reel description
def extract_reel_description(html_content):
    logging.info("Extracting reel description")
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Try to find description in meta tags (most reliable)
        meta_description = soup.find('meta', property='og:description')
        if meta_description and meta_description.get('content'):
            description = meta_description.get('content')
            # Instagram meta descriptions often include username and other text at the beginning
            # Try to clean this up
            if ': "' in description:
                description = description.split(': "', 1)[1].rstrip('"')
            return description
        
        # Backup method - look for post text
        # Instagram often has text in a span with accessible text
        post_texts = soup.find_all('span', attrs={'role': 'button'})
        for text in post_texts:
            if text.get_text():
                return text.get_text()
        
        # Fall back to any text in post container
        post_container = soup.find('div', class_=lambda c: c and 'caption' in c.lower())
        if post_container:
            return post_container.get_text()
            
        return "No description available"
    except Exception as e:
        logging.error(f"Error extracting description: {e}")
        return "Error extracting description"

# Function to download the video
def download_video(video_url, download_dir):
    logging.info(f"Starting download of video from {video_url}")
    video_name = video_url.split('/')[-1].split('?')[0]  # Get video name from URL
    video_path = os.path.join(download_dir, video_name)
    try:
        response = requests.get(video_url, stream=True)
        with open(video_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        logging.info(f"Video downloaded to {video_path}")
        return os.path.abspath(video_path)
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        return None

# Function to add cookies from either JSON or Netscape cookie file
def add_cookies_from_file(driver, cookie_file_path):
    try:
        with open(cookie_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
            # Try to detect if it's JSON format
            if content.startswith('[') and content.endswith(']'):
                # JSON format
                try:
                    cookies = json.loads(content)
                    logging.info(f"Detected JSON cookie format with {len(cookies)} cookies")
                    for cookie in cookies:
                        # Convert JSON cookie format to Selenium format
                        cookie_dict = {
                            'domain': cookie.get('domain'),
                            'httpOnly': cookie.get('httpOnly', False),
                            'name': cookie.get('name'),
                            'path': cookie.get('path', '/'),
                            'secure': cookie.get('secure', False),
                            'value': cookie.get('value')
                        }
                        
                        # Add expiry if it exists (convert to int if needed)
                        if 'expirationDate' in cookie:
                            cookie_dict['expiry'] = int(cookie['expirationDate'])
                        elif 'expiry' in cookie:
                            cookie_dict['expiry'] = int(cookie['expiry'])
                            
                        driver.add_cookie(cookie_dict)
                    logging.info("JSON cookies added successfully.")
                except json.JSONDecodeError as e:
                    logging.error(f"Error parsing JSON cookies: {e}")
                    return False
            else:
                # Assume it's Netscape format
                logging.info("Attempting to parse as Netscape cookie format")
                lines = content.splitlines()
                cookie_count = 0
                
                for line in lines:
                    if line.startswith('#') or line.strip() == '':
                        continue  # Skip comments and blank lines
                    
                    parts = line.strip().split('\t')
                    if len(parts) == 7:
                        cookie = {
                            'domain': parts[0],
                            'httpOnly': parts[1] == 'TRUE',
                            'path': parts[2],
                            'secure': parts[3] == 'TRUE',
                            'expiry': int(parts[4]) if parts[4].isdigit() else None,
                            'name': parts[5],
                            'value': parts[6]
                        }
                        driver.add_cookie(cookie)
                        cookie_count += 1
                
                logging.info(f"Netscape cookies: Added {cookie_count} cookies successfully.")
                
                if cookie_count == 0:
                    logging.warning("No valid cookies found in the Netscape format file.")
                    return False
        
        return True
    except Exception as e:
        logging.error(f"Error loading cookies: {e}")
        return False

# Fallback method using yt-dlp
def try_fallback_download(reel_url, download_dir):
    logging.info("Attempting fallback...")
    try:
        # Generate unique output filename
        unique_id = str(uuid.uuid4())[:8]
        output_path = os.path.join(download_dir, f"www_instagram_com_{unique_id}.mp4")
        
        # Get the next cookie in rotation for yt-dlp
        cookie_file = get_next_cookie_file()
        if not cookie_file:
            cookie_file = './cookies/cookies.txt'  # Default fallback
            logging.warning(f"Using default cookie file: {cookie_file}")
        
        # Prepare yt-dlp command
        cmd = [
            'yt-dlp',
            reel_url,
            '-o', output_path,
            '-f', 'bestvideo+bestaudio/best',
            '--merge-output-format', 'mp4',
            '--no-playlist',
            '--cookies', cookie_file,
            '--write-info-json',
            '-v'  # Verbose output for debugging
        ]
        
        # Run the command
        process = subprocess.run(cmd, check=True, text=True, capture_output=True)
        
        # Check if download succeeded
        if os.path.exists(output_path):
            logging.info(f"Fallback download succeeded to {output_path}")
            return {
                "file_path": output_path,
                "title": "Instagram Reel",
                "description": "Downloaded via fallback method"
            }
        else:
            logging.error("Fallback download failed: file not found")
            logging.debug(f"yt-dlp stdout: {process.stdout}")
            logging.debug(f"yt-dlp stderr: {process.stderr}")
            return None
    except Exception as e:
        logging.error(f"Fallback download failed: {e}")
        return None

# Main function to process Instagram reel
def download_instagram_reel(reel_url, download_dir):
    logging.info(f"Starting Instagram reel download for URL: {reel_url}")
    
    try:
        # Set up the Selenium WebDriver with WebDriverManager - this is the key change
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'--user-data-dir=/tmp/chrome-data-{str(uuid.uuid4())}')
        
        # Let WebDriverManager handle everything - it will automatically find or download
        # the correct driver for your Chrome version
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Navigate to Instagram and add cookies
        logging.info(f"Navigating to Instagram login page to add cookies")
        driver.get("https://www.instagram.com")
        time.sleep(2)
        
        # Get the next cookie file in rotation
        cookie_file = get_next_cookie_file()
        if not cookie_file:
            raise Exception("No cookie files found")
            
        # Load cookies from the selected file
        add_cookies_from_file(driver, cookie_file)
        driver.refresh()
        time.sleep(2)
        
        # Navigate to the reel URL
        driver.get(reel_url)
        time.sleep(3)  # Increased wait time to ensure page loads
        # Generate a unique filename for the HTML save path
        unique_filename = str(uuid.uuid4())
        html_save_path = os.path.join(download_dir, f"{unique_filename}.html")
        
        # Save the HTML content
        save_complete_html(driver, html_save_path)
        
        # Extract the description from the page
        description = extract_reel_description(driver.page_source)
        logging.info(f"Extracted description: {description[:100]}...")  # Log first 100 chars
        # Set the title to "Instagram Reel" as requested
        title = "Instagram Reel"
        
        # Get the shortcode from the URL (used to locate video URL)
        shortcode = reel_url.split('/')[-2]
        logging.info(f"Extracted shortcode: {shortcode}")
        
        # Extract the 720p video URL
        video_url = extract_instagram_720p_video_url(html_save_path, shortcode)
        
        # Remove the HTML file after extracting the video URL
        os.remove(html_save_path)
        
        # Download the video and return its full absolute path along with metadata
        if video_url:
            video_path = download_video(video_url, download_dir)
            logging.info(f"Download completed. Video saved at {video_path}")
            
            # Return video path and metadata
            return {
                "file_path": video_path,
                "title": title,
                "description": description
            }
        else:
            logging.warning(f"Video URL not found for reel: {reel_url}")
            return try_fallback_download(reel_url, download_dir)
            
    except Exception as e:
        logging.error(f"Error with instagram function: {e}")
        logging.info("Attempting fallback...")
        return try_fallback_download(reel_url, download_dir)
    finally:
        if 'driver' in locals():
            logging.info(f"Quitting WebDriver for URL: {reel_url}")
            driver.quit()
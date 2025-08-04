"""
TikTok scraper module for social media links scraping.
Uses the latest TikTok captcha solver API with Chrome 137 support.
"""

import logging
import time
from typing import List
from selenium.webdriver.common.by import By
import config


def tiktok_scraper(driver, account_url: str, cookie_path: str, api_key: str, max_videos: int) -> List[str]:
    """
    Scrape TikTok account for video links with integrated captcha solving.
    
    Args:
        driver: Chrome WebDriver instance (with integrated captcha solver)
        account_url: TikTok account URL to scrape
        cookie_path: Path to cookies file
        api_key: TikTok captcha solver API key
        max_videos: Maximum number of videos to collect
        
    Returns:
        List of video URLs
    """
    video_links = []
    processed_urls = set()
    MAX_ATTEMPTS = config.TIKTOK_MAX_ATTEMPTS
    RETRY_WAIT = config.TIKTOK_RETRY_WAIT
    
    CONTAINER_XPATHS = config.TIKTOK_CONTAINER_XPATHS
    
    def extract_posts():
        """Extract posts from the current page using multiple XPath patterns."""
        recent_posts = []
        for xpath in CONTAINER_XPATHS:
            try:
                container = driver.find_element(By.XPATH, xpath)
                posts = container.find_elements(By.XPATH, './/div[@data-e2e="user-post-item"]//a')
                if posts:
                    links = [p.get_attribute('href') for p in posts]
                    filtered_links = [link for link in links if link not in processed_urls]
                    recent_posts.extend(filtered_links)
                    for link in filtered_links:
                        processed_urls.add(link)
                    if filtered_links:
                        logging.info(f"Found {len(filtered_links)} new posts using xpath: {xpath}")
                    return list(dict.fromkeys(recent_posts))  # Remove duplicates
            except Exception as e:
                logging.error(f"XPath {xpath} failed: {str(e)}")
                continue
        return []
    
    def scroll_and_extract():
        """Scroll the page and extract new posts until no more content loads."""
        last_height = driver.execute_script("return document.documentElement.scrollHeight")
        while len(video_links) < max_videos:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            time.sleep(2)  # Wait for content to load
            
            # Get new posts
            new_links = extract_posts()
            if new_links:
                video_links.extend(new_links)
                logging.info(f"Total videos found: {len(video_links)}")
            
            # Check if we've reached the bottom
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            if new_height == last_height:
                logging.info("Reached end of page - no more videos to load")
                break
            last_height = new_height
    
    try:
        # Initial setup
        logging.info("Loading TikTok...")
        driver.get("https://www.tiktok.com")
        
        # Note: Captcha solver is now integrated into driver creation
        
        # Load cookies (using same approach as Instagram/X)
        logging.info("Loading cookies...")
        with open(cookie_path, 'r') as file:
            for line in file:
                if line.startswith('#') or not line.strip():
                    continue
                fields = line.strip().split('\t')
                if len(fields) >= 7:
                    # Only load TikTok cookies
                    if 'tiktok.com' not in fields[0]:
                        continue
                    
                    cookie_dict = {
                        'name': fields[5],
                        'value': fields[6],
                        'domain': fields[0],
                        'path': fields[2]
                    }
                    
                    # Handle secure flag
                    if fields[3].lower() == 'true':
                        cookie_dict['secure'] = True
                    
                    # Handle expiry - skip cookies with invalid expiry values
                    if fields[4] != '0' and fields[4].isdigit():
                        try:
                            expiry_value = int(fields[4])
                            # Only set expiry if it's a reasonable future timestamp
                            if expiry_value > int(time.time()):
                                cookie_dict['expiry'] = expiry_value
                        except (ValueError, OverflowError):
                            # Skip cookies with invalid expiry values
                            continue
                    
                    try:
                        driver.delete_cookie(fields[5])  # Delete first like X does
                        driver.add_cookie(cookie_dict)
                    except Exception as e:
                        # Only log warning for cookie issues instead of error
                        logging.warning(f"Skipped cookie {fields[5]}: {str(e)[:50]}...")
        
        driver.refresh()
        time.sleep(5)
        
        # Process account
        attempts = 0
        logging.info(f"Processing TikTok account: {account_url}")
        
        while attempts < MAX_ATTEMPTS:
            attempts += 1
            driver.get(account_url)
            time.sleep(5)
            
            # Handle captcha if present - captcha solver is now automatic via the driver
            logging.info("Captcha solver is integrated into driver - will handle automatically")
            time.sleep(2)
            
            # Try to scroll and get all videos
            scroll_and_extract()
            
            # If we found any videos at all, we're done
            if video_links:
                logging.info(f"Successfully collected {len(video_links)} video links")
                break
            
            # Only retry if NO videos were found
            logging.warning(f"No videos found on attempt {attempts}/{MAX_ATTEMPTS}")
            if attempts < MAX_ATTEMPTS:
                logging.info(f"Waiting {RETRY_WAIT} seconds before retry...")
                time.sleep(RETRY_WAIT)
        
        if not video_links:
            logging.warning("Failed to collect any video links after all attempts")
            
    except Exception as e:
        logging.error(f"Error processing TikTok account {account_url}: {str(e)}")
    
    return video_links[:max_videos] 
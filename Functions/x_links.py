"""
X/Twitter Links Scraper Module

This module contains functions for scraping video links from X/Twitter profiles.
Uses BeautifulSoup for HTML parsing and handles cookie authentication.
"""

import logging
import time
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import config


def load_cookies(driver, cookie_path):
    """
    Load cookies from file into the driver.
    
    Args:
        driver: Selenium WebDriver instance
        cookie_path: Path to cookie file
        
    Returns:
        bool: True if cookies loaded successfully, False otherwise
    """
    try:
        logging.info("Loading X/Twitter cookies...")
        cookie_count = 0
        with open(cookie_path, 'r') as file:
            for line in file:
                if line.startswith('#') or not line.strip():
                    continue
                fields = line.strip().split('\t')
                if len(fields) >= 7:
                    # Only load X/Twitter cookies - be more explicit about filtering
                    domain = fields[0]
                    if 'x.com' not in domain and 'twitter.com' not in domain:
                        continue
                    
                    cookie_dict = {
                        'name': fields[5],
                        'value': fields[6],
                        'domain': domain,
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
                        driver.delete_cookie(fields[5])
                        driver.add_cookie(cookie_dict)
                        cookie_count += 1
                    except Exception as e:
                        logging.warning(f"Skipped cookie {fields[5]}: {str(e)[:50]}...")
                        
        logging.info(f"Loaded {cookie_count} X/Twitter cookies")
        
        # Verify cookies were actually loaded
        current_cookies = driver.get_cookies()
        if len(current_cookies) < cookie_count * 0.5:  # At least 50% of cookies should load
            logging.error(f"Cookie verification failed. Expected {cookie_count}, got {len(current_cookies)}")
            return False
        return True
        
    except Exception as e:
        logging.error(f"Error loading cookies: {e}")
        return False


def x_scraper(driver, account_url: str, cookie_path: str, cutoff_date: str, chrome_options) -> list:
    """
    Scrape video links from an X/Twitter account.
    
    Args:
        driver: Selenium WebDriver instance
        account_url: X/Twitter account URL (e.g., https://x.com/username)
        cookie_path: Path to cookie file
        cutoff_date: Stop scraping when posts older than this date are found (YYYY-MM-DD)
        chrome_options: Chrome options for driver recreation if needed
    
    Returns:
        List of video URLs
    """
    video_links = []
    seen_urls = set()
    last_processed_date = None
    consecutive_no_video_scrolls = 0
    max_no_video_scrolls = config.X_MAX_NO_VIDEO_SCROLLS
    
    # Try loading cookies up to 3 times
    max_cookie_attempts = 3
    cookie_attempt = 0
    cookies_loaded = False
    
    while cookie_attempt < max_cookie_attempts and not cookies_loaded:
        try:
            driver.get("https://x.com")
            cookies_loaded = load_cookies(driver, cookie_path)
            
            if cookies_loaded:
                driver.refresh()
                time.sleep(5)
                logging.info("Cookies loaded successfully")
                break
            else:
                cookie_attempt += 1
                logging.warning(f"Cookie loading attempt {cookie_attempt} failed")
                driver.quit()
                time.sleep(2)
                driver = uc.Chrome(options=chrome_options, version_main=config.CHROME_VERSION)
                
        except Exception as e:
            cookie_attempt += 1
            logging.error(f"Error during cookie loading attempt {cookie_attempt}: {e}")
            try:
                driver.quit()
                time.sleep(2)
                driver = uc.Chrome(options=chrome_options, version_main=config.CHROME_VERSION)
            except Exception as e:
                logging.error(f"Error recreating driver: {e}")
    
    if not cookies_loaded:
        logging.error("Failed to load cookies after maximum attempts")
        return video_links
        
    try:
        # Start scraping the account
        logging.info(f"Processing X account: {account_url}")
        driver.get(account_url)
        time.sleep(5)
        
        while True:  # Continue scrolling until break conditions are met
            videos_before = len(seen_urls)
            
            html_source = driver.page_source
            soup = BeautifulSoup(html_source, 'lxml')
            video_divs = soup.find_all('div', style=True)
            earliest_date_found = None
            
            for video_div in video_divs:
                style = video_div.get('style', '')
                if 'translateY' in style:
                    video_component = video_div.find('div', {'data-testid': 'videoPlayer'})
                    if not video_component:
                        continue
                    
                    post_div = video_div.find('div', class_='css-175oi2r r-18u37iz r-1q142lx')
                    if post_div:
                        post_link = post_div.find('a', href=True)
                        time_element = post_div.find('time')
                        post_date = time_element['datetime'][:10] if time_element else None
                        
                        if post_date:
                            last_processed_date = post_date
                            if earliest_date_found is None or post_date < earliest_date_found:
                                earliest_date_found = post_date
                                
                            if post_date >= cutoff_date:
                                post_url = f"https://twitter.com{post_link['href']}"
                                if post_url not in seen_urls:
                                    seen_urls.add(post_url)
                                    video_links.append(post_url)
                                    logging.info(f"Found video: {post_url} from {post_date}")
            
            videos_after = len(seen_urls)
            
            # Check if we found any new videos in this scroll
            if videos_after == videos_before:
                consecutive_no_video_scrolls += 1
                if consecutive_no_video_scrolls >= max_no_video_scrolls:
                    logging.info(f"No new videos found after {max_no_video_scrolls} scrolls")
                    break
            else:
                consecutive_no_video_scrolls = 0  # Reset counter if we found new videos
            
            # Check if we've reached content older than the cutoff date
            if earliest_date_found and earliest_date_found < cutoff_date:
                logging.info(f"Reached content older than cutoff date ({earliest_date_found})")
                break
            
            # Scroll down and wait for content to load
            driver.execute_script(f"window.scrollBy(0, {config.X_SCROLL_AMOUNT});")
            time.sleep(2)
            
    except Exception as e:
        logging.error(f"Error processing X account {account_url}: {e}")
        if last_processed_date:
            logging.error(f"Last successfully processed date: {last_processed_date}")
    
    return video_links 
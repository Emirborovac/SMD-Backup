"""
Facebook scraper module for social media links scraping.
"""

import logging
import time
from typing import List
from selenium.webdriver.common.by import By
import config


def facebook_scraper(driver, account_url: str, cookie_path: str, max_years: int = 2, cutoff_days: int = None, cutoff_weeks: int = None, cutoff_months: int = None) -> List[str]:
    """
    Scrape Facebook account for video links within the specified time period.
    
    Args:
        driver: Chrome WebDriver instance
        account_url: Facebook account URL to scrape
        cookie_path: Path to facebook.txt file containing cookies
        max_years: Maximum years to look back for videos
        cutoff_days: If set, only include videos newer than this many days
        cutoff_weeks: If set, only include videos newer than this many weeks
        cutoff_months: If set, only include videos newer than this many months
        
    Returns:
        List of video URLs
    """
    video_links = []
    processed_urls = set()
    
    def is_within_time_limit(date_text):
        """Check if the video date is within the specified time limit."""
        if not date_text:
            return False
            
        date_text = date_text.lower()
        
        try:
            if 'just now' in date_text:
                return True
            elif 'minute' in date_text:
                return True
            elif 'hour' in date_text:
                return True
            elif 'yesterday' in date_text or 'a day ago' in date_text:
                # Check if we have a specific day cutoff
                if cutoff_days is not None:
                    return 1 <= cutoff_days
                return True
            elif 'days' in date_text:
                days = int(''.join(filter(str.isdigit, date_text)))
                # Check against specific day cutoff if provided
                if cutoff_days is not None:
                    return days <= cutoff_days
                # Otherwise check against years (days within max_years)
                return days <= (max_years * 365)
            elif 'week' in date_text:
                if 'a week' in date_text:
                    weeks = 1
                else:
                    weeks = int(''.join(filter(str.isdigit, date_text)))
                # Check against specific week cutoff if provided
                if cutoff_weeks is not None:
                    return weeks <= cutoff_weeks
                # Otherwise check against years
                return weeks <= (max_years * 52)
            elif 'month' in date_text:
                if 'a month' in date_text:
                    months = 1
                else:
                    months = int(''.join(filter(str.isdigit, date_text)))
                # Check against specific month cutoff if provided
                if cutoff_months is not None:
                    return months <= cutoff_months
                # Otherwise check against years
                return months <= (max_years * 12)
            elif 'year' in date_text:
                if 'a year' in date_text:
                    years = 1
                else:
                    years = int(''.join(filter(str.isdigit, date_text)))
                return years <= max_years
        except Exception as e:
            logging.error(f"Error parsing date text '{date_text}': {e}")
            return True  # Continue if we can't parse the date
        
        return False
    
    try:
        # Initial setup and authentication (use same approach as Instagram/X)
        driver.get("https://www.facebook.com")
        
        # Load cookies from facebook.txt file
        with open(cookie_path, 'r') as file:
            for line in file:
                if line.startswith('#') or not line.strip():
                    continue
                fields = line.strip().split('\t')
                if len(fields) >= 7:
                    cookie_dict = {
                        'name': fields[5],
                        'value': fields[6],
                        'domain': fields[0],
                        'path': fields[2]
                    }
                    if fields[3].lower() == 'true':
                        cookie_dict['secure'] = True
                    if fields[4] != '0':
                        cookie_dict['expiry'] = int(fields[4])
                    try:
                        driver.delete_cookie(fields[5])  # Delete first like X does
                        driver.add_cookie(cookie_dict)
                    except Exception as e:
                        logging.error(f"Error adding cookie {fields[5]}: {e}")
        
        driver.refresh()
        time.sleep(3)
        
        # Start scraping videos
        videos_url = account_url if account_url.endswith('/videos') else f"{account_url.rstrip('/')}/videos"
        driver.get(videos_url)
        time.sleep(5)
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        found_old_video = False
        consecutive_no_new_videos = 0
        
        # Get XPath patterns from config
        base_xpath_patterns = config.FACEBOOK_BASE_XPATH_PATTERNS
        date_xpath_patterns = config.FACEBOOK_DATE_XPATH_PATTERNS
        
        # Add timeout mechanism (max 10 minutes)
        start_time = time.time()
        max_runtime = 600  # 10 minutes
        
        while scroll_attempts < config.FACEBOOK_MAX_SCROLL_ATTEMPTS and not found_old_video:
            # Check timeout
            if time.time() - start_time > max_runtime:
                logging.warning(f"Facebook scraper timeout after {max_runtime} seconds")
                break
                
            videos_before = len(processed_urls)
            logging.debug(f"Scroll attempt {scroll_attempts + 1}/{config.FACEBOOK_MAX_SCROLL_ATTEMPTS}, processed videos: {videos_before}")
            
            # Try each base XPath pattern
            for base_xpath in base_xpath_patterns:
                index = 1
                max_elements_per_pattern = 50  # Prevent infinite loops
                
                while index <= max_elements_per_pattern:
                    try:
                        video_container_xpath = f"{base_xpath}[{index}]"
                        container = driver.find_element(By.XPATH, video_container_xpath)
                        
                        # Try each date XPath pattern
                        date_text = None
                        for date_pattern in date_xpath_patterns:
                            try:
                                date_xpath = f"{video_container_xpath}/{date_pattern}"
                                date_element = driver.find_element(By.XPATH, date_xpath)
                                date_text = date_element.text
                                if date_text:
                                    break
                            except:
                                continue
                        
                        if not date_text:
                            index += 1
                            continue
                        
                        video_links_elements = container.find_elements(By.XPATH, ".//a[contains(@href, '/videos/')]")
                        if video_links_elements:
                            video_url = video_links_elements[0].get_attribute('href')
                            
                            if video_url and video_url not in processed_urls:
                                processed_urls.add(video_url)
                                
                                if is_within_time_limit(date_text):
                                    video_links.append(video_url)
                                    logging.info(f"Found video: {video_url} from {date_text}")
                                else:
                                    found_old_video = True
                                    logging.info(f"Found old video beyond cutoff: {date_text} - stopping")
                                    break
                        
                        index += 1
                        
                    except Exception as e:
                        # If we can't find any more videos with current pattern, break inner loop
                        logging.debug(f"No more elements found for pattern {base_xpath} at index {index}")
                        break
                
                if found_old_video:
                    break
            
            videos_after = len(processed_urls)
            if videos_after == videos_before:
                consecutive_no_new_videos += 1
            else:
                consecutive_no_new_videos = 0
            
            if consecutive_no_new_videos >= config.FACEBOOK_CONSECUTIVE_NO_NEW_VIDEOS_LIMIT:
                logging.info("No new videos found after multiple scrolls")
                break
            
            # Double scroll for better loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logging.info("Reached end of page - no more content loading")
                break
                
            last_height = new_height
            scroll_attempts += 1
            
    except Exception as e:
        logging.error(f"Error processing Facebook account {account_url}: {e}")
    
    finally:
        total_time = time.time() - start_time if 'start_time' in locals() else 0
        logging.info(f"Facebook scraper completed: {len(video_links)} videos collected in {total_time:.1f} seconds, {scroll_attempts} scroll attempts")
        
    return video_links 
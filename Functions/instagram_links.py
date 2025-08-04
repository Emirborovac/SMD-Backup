"""
Instagram Links Scraper Module

This module contains functions for scraping video links from Instagram profiles.
Uses modal approach with gentle scrolling for optimal coverage.
"""

import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def close_modal(driver):
    """Robust modal closing with multiple fallback methods"""
    try:
        # Method 1: Click close button with SVG aria-label
        close_btn = driver.find_element(By.CSS_SELECTOR, 'svg[aria-label="Close"]')
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
        return
    except:
        pass
    
    try:
        # Method 2: Click close button parent
        close_btn = driver.find_element(By.CSS_SELECTOR, 'svg[aria-label="Close"]').find_element(By.XPATH, './..')
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
        return
    except:
        pass
    
    try:
        # Method 3: Press ESC key
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
        return
    except:
        pass
    
    try:
        # Method 4: Click outside modal (on backdrop)
        driver.execute_script("document.querySelector('[role=\"dialog\"]').previousElementSibling.click();")
        time.sleep(1)
        return
    except:
        pass
    
    # Method 5: Force navigate back to profile (last resort)
    current_url = driver.current_url
    if '/reel/' in current_url or '/p/' in current_url:
        # If we're on a post page, go back
        driver.back()
        time.sleep(1)


def instagram_scraper(driver, account_url: str, cookie_path: str, cutoff_date: str) -> list:
    """
    Scrape video links from an Instagram account using modal approach.
    
    Args:
        driver: Selenium WebDriver instance
        account_url: Instagram account URL (e.g., https://www.instagram.com/username)
        cookie_path: Path to cookie file
        cutoff_date: Stop scraping when posts older than this date are found (YYYY-MM-DD)
    
    Returns:
        List of video URLs
    """
    video_links = []
    last_processed_date = None
    processed_urls = set()
    
    try:
        # Initial setup and authentication
        driver.get("https://www.instagram.com")
        
        # Load cookies
        logging.info("Loading cookies...")
        cookie_count = 0
        with open(cookie_path, 'r') as file:
            for line in file:
                if line.startswith('#') or not line.strip():
                    continue
                fields = line.strip().split('\t')
                if len(fields) >= 7:
                    # Only load Instagram cookies - be more explicit about filtering
                    domain = fields[0]
                    if 'instagram.com' not in domain:
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
                        driver.delete_cookie(fields[5])  # Delete first like other scrapers
                        driver.add_cookie(cookie_dict)
                        cookie_count += 1
                    except Exception as e:
                        # Change to warning to avoid spam in logs
                        logging.warning(f"Skipped cookie {fields[5]}: {str(e)[:50]}...")
        
        logging.info(f"Loaded {cookie_count} Instagram cookies")
        
        driver.refresh()
        time.sleep(5)
        
        # Start scraping the account
        logging.info(f"Processing Instagram account: {account_url}")
        driver.get(account_url)
        time.sleep(5)
        
        # Modal approach - gentle scrolling to avoid missing videos
        max_scroll_attempts = 100
        consecutive_no_new_posts = 0
        
        # Collect pinned posts once at the beginning
        pinned_hrefs = set()
        try:
            # Find all pinned post icons with exact aria-label
            pinned_icons = driver.find_elements(By.CSS_SELECTOR, 'svg[aria-label="Pinned post icon"]')
            for icon in pinned_icons:
                try:
                    # Find the parent link element
                    parent_link = icon.find_element(By.XPATH, './ancestor::a[contains(@href, "/reel/") or contains(@href, "/p/")]')
                    href = parent_link.get_attribute('href')
                    if href:
                        href_path = href.replace('https://www.instagram.com', '')
                        pinned_hrefs.add(href_path)
                except:
                    continue
                    
            if pinned_hrefs:
                logging.info(f"Found {len(pinned_hrefs)} pinned posts to skip: {list(pinned_hrefs)}")
        except Exception as e:
            logging.warning(f"Could not detect pinned posts: {e}")
        
        scroll_count = 0
        
        while scroll_count < max_scroll_attempts and consecutive_no_new_posts < 15:
            # Get ALL video posts on the page (go back to what worked!)
            video_posts = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/reel/"], a[href*="/p/"]')
            logging.info(f"Batch {scroll_count + 1}: Found {len(video_posts)} total video elements")
            
            posts_processed_this_batch = 0
            
            for post in video_posts:
                href = post.get_attribute('href')
                if not href:
                    continue
                
                # Extract path for comparison
                href_path = href.replace('https://www.instagram.com', '')
                
                # Skip if already processed
                if href_path in processed_urls:
                    continue
                
                # Skip invalid URLs
                if '/liked_by/' in href_path or '/tagged/' in href_path:
                    continue
                
                # Skip pinned posts (using collected pinned_hrefs like the old approach)
                if href_path in pinned_hrefs:
                    logging.info(f"Skipping pinned post: {href_path}")
                    continue
                
                processed_urls.add(href_path)
                posts_processed_this_batch += 1
                
                try:
                    # Scroll the post into view for better clicking
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", post)
                    time.sleep(1)
                    
                    # Click to open modal
                    driver.execute_script("arguments[0].click();", post)
                    time.sleep(3)  # Wait for modal to fully load
                    
                    # Check if it's a video by looking for video element or clip icon
                    is_video = False
                    try:
                        # Look for video element
                        video_element = driver.find_element(By.TAG_NAME, 'video')
                        is_video = True
                    except:
                        try:
                            # Look for clip/reel icon in modal
                            clip_icon = driver.find_element(By.CSS_SELECTOR, 'svg[aria-label="Clip"], svg[aria-label="Reel"]')
                            is_video = True
                        except:
                            pass
                    
                    if is_video:
                        # Get date from modal
                        try:
                            time_element = driver.find_element(By.CSS_SELECTOR, 'time[datetime]')
                            post_date = time_element.get_attribute('datetime')[:10]
                            
                            if post_date:
                                last_processed_date = post_date
                                
                                if post_date < cutoff_date:
                                    logging.info(f"Found post older than cutoff ({post_date}), stopping")
                                    # Close modal before returning
                                    try:
                                        close_modal(driver)
                                    except:
                                        pass
                                    return video_links
                                
                                video_links.append(href)
                                logging.info(f"Found video: {href} from {post_date}")
                        except Exception as e:
                            logging.warning(f"Could not get date for {href}: {e}")
                    
                    # Close modal with multiple fallback methods
                    close_modal(driver)
                    
                    # Ensure we're back on the profile page
                    current_url = driver.current_url
                    if account_url not in current_url:
                        driver.get(account_url)
                        time.sleep(2)
                    
                except Exception as e:
                    logging.error(f"Error processing post {href}: {e}")
                    # Try to close any open modal and return to profile
                    try:
                        close_modal(driver)
                        if account_url not in driver.current_url:
                            driver.get(account_url)
                            time.sleep(2)
                    except:
                        # Force return to profile
                        driver.get(account_url)
                        time.sleep(2)
                    continue
            
            # Check if we processed any new posts in this batch
            if posts_processed_this_batch > 0:
                consecutive_no_new_posts = 0
                logging.info(f"Batch {scroll_count + 1}: Processed {posts_processed_this_batch} new posts")
            else:
                consecutive_no_new_posts += 1
                logging.info(f"Batch {scroll_count + 1}: No new posts (consecutive: {consecutive_no_new_posts})")
            
            # Gentle scroll to expose a few new videos (not jump to bottom!)
            logging.info(f"Gentle scrolling to expose new videos...")
            posts_before_scroll = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/reel/"], a[href*="/p/"]'))
            
            # Gentle scroll - just 3 posts worth of height to expose new content
            scroll_amount = 400  # Gentle scroll amount
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(2)  # Let content load
            
            # Check if new content loaded
            posts_after_scroll = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/reel/"], a[href*="/p/"]'))
            new_posts_loaded = posts_after_scroll - posts_before_scroll
            
            if new_posts_loaded > 0:
                logging.info(f"Loaded {new_posts_loaded} new posts after gentle scroll")
            else:
                logging.info("No new posts loaded - trying slightly bigger scroll")
                # If no new content, try a slightly bigger scroll to trigger loading
                driver.execute_script(f"window.scrollBy(0, {scroll_amount * 2});")
                time.sleep(3)
                
                # Check again
                posts_after_big_scroll = len(driver.find_elements(By.CSS_SELECTOR, 'a[href*="/reel/"], a[href*="/p/"]'))
                if posts_after_big_scroll == posts_after_scroll:
                    # Still no new content - might have reached end
                    if consecutive_no_new_posts >= 3:
                        logging.info("Reached end of content")
                        break
            
            scroll_count += 1
        
        logging.info(f"Finished processing. Found {len(video_links)} videos.")
        if last_processed_date:
            logging.info(f"Last post date reached: {last_processed_date}")
    
    except Exception as e:
        logging.error(f"Error processing Instagram account {account_url}: {e}")
        if last_processed_date:
            logging.error(f"Last successfully processed date: {last_processed_date}")
    
    return video_links 
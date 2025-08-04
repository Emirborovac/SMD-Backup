import logging
import re
import os
import random
import time
import uuid
import json
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def get_domain_from_url(url):
    """Extract domain from URL"""
    parsed = urlparse(url)
    return parsed.hostname

# Function to add cookies from either JSON or Netscape cookie file - your proven Instagram method
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

def clean_nytimes_text(text):
    """Clean NYT article text - your exact approach"""
    if not text:
        return None
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove NYT specific unwanted patterns
    patterns_to_remove = [
        r'Subscribe to The Times.*?articles as you like\.',
        r'Subscribe to continue reading\.',
        r'Already a subscriber\?.*?Sign In',
        r'Give this article.*?Read in app',
        r'Send any friend a story.*?subscriber',
        r'data-testid=".*?"',
        r'class="css-.*?"',
        r'id=".*?"',
        r'aria-.*?=".*?"',
        r'role=".*?"',
        r'css-.*?',
        r'StoryBodyCompanionColumn',
        r'companionColumn-.*?',
        r'Advertisement',
        r'Continue reading the main story',
        r'Image.*?Credit.*?',
        r'Credit\.\.\.',
        r'A version of this article appears in print',
        r'Read more about:.*?$'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean up extra whitespace and common artifacts
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'<!-- -->', '', text)
    
    return text if len(text) > 50 else None

def extract_nytimes_article_with_selenium(url, news_cookies_dir):
    """Extract article from NYT URL using Selenium with your exact working method"""
    
    domain = get_domain_from_url(url)
    cookie_file = f"{domain}_cookies.txt"
    cookie_path = os.path.join(news_cookies_dir, cookie_file)
    
    # Setup Chrome options using your working Instagram pattern
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument(f'--user-data-dir=/tmp/chrome-data-{str(uuid.uuid4())}')
    
    # Add your stealth settings on top of the working base
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--no-first-run')
    options.add_argument('--window-size=1920,1080')
    
    # Realistic user agents for NYT (US market) - your exact list
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0'
    ]
    
    selected_ua = random.choice(user_agents)
    logging.info(f"🎭 Using User Agent: {selected_ua[:50]}...")
    options.add_argument(f'--user-agent={selected_ua}')
    
    # Additional stealth settings
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        # Use WebDriverManager like your working Instagram code
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Execute stealth script - your exact approach
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            window.chrome = {
                runtime: {},
                loadTimes: function() {
                    return {
                        requestTime: Date.now() / 1000,
                        startLoadTime: Date.now() / 1000,
                        commitLoadTime: Date.now() / 1000,
                        finishDocumentLoadTime: Date.now() / 1000,
                        finishLoadTime: Date.now() / 1000,
                        firstPaintTime: Date.now() / 1000,
                        firstPaintAfterLoadTime: 0,
                        navigationType: 'Other',
                        wasFetchedViaSpdy: false,
                        wasNpnNegotiated: false,
                        npnNegotiatedProtocol: 'unknown',
                        wasAlternateProtocolAvailable: false,
                        connectionInfo: 'unknown'
                    };
                },
            };
            
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            window.navigator.chrome = window.chrome;
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 1,
            });
        """)
        
        # Navigate to NYT first to set domain, then add cookies - your working Instagram pattern
        logging.info("Navigating to NYT homepage to add cookies")
        driver.get("https://www.nytimes.com")
        time.sleep(2)
        
        # Load cookies using your proven Instagram method
        if os.path.exists(cookie_path):
            add_cookies_from_file(driver, cookie_path)
            driver.refresh()
            time.sleep(2)
            logging.info("✓ Cookies loaded and page refreshed")
        else:
            logging.warning(f"Cookie file not found: {cookie_path}")
        
        logging.info(f"🌐 Loading: {url}")
        
        # Navigate to article - your exact approach
        driver.get(url)
        time.sleep(5)  # Give NYT time to load
        
        # Check for paywall
        page_content = driver.page_source
        paywall_indicators = [
            'Subscribe to continue reading',
            'Subscribe to The Times',
            'Already a subscriber',
            'Sign In',
            'membership'
        ]
        
        has_paywall = any(indicator in page_content for indicator in paywall_indicators)
        if has_paywall:
            logging.warning("⚠️  Paywall detected - extracting available preview content")
        
        # Extract title - your exact method
        title = None
        title_selectors = [
            "h1.css-88wicj",
            "h1[data-testid='headline']",
            "h1.e1h9rw200",
            "h1",
            ".headline",
            "[data-testid='headline']"
        ]
        
        for selector in title_selectors:
            try:
                title_element = driver.find_element(By.CSS_SELECTOR, selector)
                if title_element:
                    title = title_element.text
                    if title:
                        title = title.strip()
                        title = re.sub(r'\s+', ' ', title)
                        title = clean_nytimes_text(title)
                        logging.info(f"✓ Title: {title}")
                        break
            except:
                continue
        
        # Extract first image - your exact method
        image_url = None
        image_selectors = [
            "img.css-rq4mmj",
            "img[src*='static01.nyt.com']",
            "img[src*='nytimes.com']",
            ".story-body img",
            "article img"
        ]
        
        for selector in image_selectors:
            try:
                img_element = driver.find_element(By.CSS_SELECTOR, selector)
                if img_element:
                    image_url = img_element.get_attribute('src')
                    if image_url and 'nytimes.com' in image_url:
                        logging.info(f"✓ Image: {image_url}")
                        break
            except:
                continue
        
        # Extract article content - your exact working approach
        article_text = None
        try:
            # NYT article content selectors - your exact selectors that work
            content_selectors = [
                'section[name="articleBody"]',
                ".meteredContent",
                ".css-1r7ky0e",
                ".story-body",
                "article#story"
            ]
            
            article_container = None
            for selector in content_selectors:
                try:
                    container = driver.find_element(By.CSS_SELECTOR, selector)
                    if container:
                        article_container = container
                        logging.info(f"✓ Found article container with selector: {selector}")
                        break
                except Exception as e:
                    logging.error(f"❌ Error with selector {selector}: {e}")
                    continue
            
            if article_container:
                # NYT structures content in multiple StoryBodyCompanionColumn divs - your exact approach
                try:
                    companion_columns = article_container.find_elements(By.CSS_SELECTOR, '.StoryBodyCompanionColumn')
                    
                    if companion_columns:
                        text_parts = []
                        logging.info(f"✓ Found {len(companion_columns)} companion columns")
                        
                        for i, column in enumerate(companion_columns):
                            try:
                                # Get all paragraphs within each companion column
                                paragraphs = column.find_elements(By.CSS_SELECTOR, "p.css-at9mc1, p.evys1bk0")
                                
                                for p in paragraphs:
                                    try:
                                        paragraph_text = p.text
                                        if paragraph_text and len(paragraph_text.strip()) > 20:
                                            # Skip NYT UI elements and ads
                                            if not any(skip_word in paragraph_text.lower() for skip_word in [
                                                'subscribe to the times', 'already a subscriber', 'sign in',
                                                'advertisement', 'continue reading', 'give this article',
                                                'send any friend', 'read in app', 'credit...', 
                                                'a version of this article appears', 'skip advertisement'
                                            ]):
                                                clean_text = clean_nytimes_text(paragraph_text.strip())
                                                if clean_text and len(clean_text) > 30:
                                                    text_parts.append(clean_text)
                                                    logging.info(f"  Added paragraph {len(text_parts)} from column {i+1}")
                                    except:
                                        continue
                            except Exception as e:
                                logging.error(f"❌ Error processing column {i+1}: {e}")
                                continue
                        
                        if text_parts:
                            article_text = ' '.join(text_parts)
                            logging.info(f"✓ Extracted {len(text_parts)} paragraphs from companion columns ({len(article_text)} chars)")
                        else:
                            logging.error("❌ No valid text found in companion columns")
                            
                    else:
                        logging.error("❌ No companion columns found - trying direct paragraph extraction")
                        
                        # Fallback: get all paragraphs directly from article container
                        try:
                            all_paragraphs = article_container.find_elements(By.CSS_SELECTOR, "p.css-at9mc1, p.evys1bk0")
                            if all_paragraphs:
                                text_parts = []
                                for p in all_paragraphs:
                                    try:
                                        p_text = p.text
                                        if p_text and len(p_text.strip()) > 30:
                                            clean_text = clean_nytimes_text(p_text.strip())
                                            if clean_text and len(clean_text) > 30:
                                                text_parts.append(clean_text)
                                    except:
                                        continue
                                
                                if text_parts:
                                    article_text = ' '.join(text_parts)
                                    logging.info(f"✓ Fallback extracted {len(text_parts)} paragraphs ({len(article_text)} chars)")
                                else:
                                    logging.error("❌ Fallback found no valid content")
                            else:
                                logging.error("❌ No paragraphs found in fallback")
                        except Exception as e:
                            logging.error(f"❌ Fallback extraction error: {e}")
                            
                except Exception as e:
                    logging.error(f"❌ Error finding companion columns: {e}")
            else:
                logging.error("❌ Could not find article container")
                
        except Exception as e:
            logging.error(f"❌ Article extraction error: {e}")
        
        return {
            "title": title,
            "article": article_text,
            "image": image_url,
            "url": url,
            "domain": domain
        }
        
    except Exception as e:
        logging.error(f"❌ Extraction failed: {e}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

def extract_nytimes_article(url, news_cookies_dir):
    """Main NYT extraction function using Selenium with your exact working method"""
    result = extract_nytimes_article_with_selenium(url, news_cookies_dir)
    return result 
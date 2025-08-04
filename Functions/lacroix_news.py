import asyncio
import logging
import re
import os
from playwright.async_api import async_playwright
from urllib.parse import urljoin, urlparse

def parse_netscape_cookies(file_path):
    """Parse Netscape cookie file format - your exact approach with proper Playwright format"""
    cookies = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) >= 7:
                    domain = parts[0]
                    domain_flag = parts[1] == 'TRUE'
                    path = parts[2]
                    secure = parts[3] == 'TRUE'
                    expires = parts[4]
                    name = parts[5]
                    value = parts[6]
                    
                    # Convert expires timestamp
                    expires_timestamp = None
                    if expires != '-1' and expires.isdigit():
                        expires_timestamp = int(expires)
                    
                    cookie = {
                        'name': name,
                        'value': value,
                        'domain': domain,
                        'path': path,
                        'secure': secure
                    }
                    
                    # Add expires if not session cookie
                    if expires_timestamp:
                        cookie['expires'] = expires_timestamp
                    
                    cookies.append(cookie)
    except FileNotFoundError:
        logging.error(f"Cookie file {file_path} not found!")
        return []
    
    return cookies

def clean_lacroix_text(text):
    """Clean La Croix article text - adapted from your approach"""
    if not text:
        return None
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove La Croix specific unwanted patterns
    patterns_to_remove = [
        r'Je fais un don',
        r'Je m\'abonne',
        r'Connexion',
        r'Menu',
        r'À la une',
        r'Partager',
        r'Tweeter',
        r'Partager sur Facebook',
        r'Envoyer par e-mail',
        r'Imprimer',
        r'Agrandir',
        r'Réduire',
        r'Fermer',
        r'Voir plus',
        r'Newsletter',
        r'Podcast',
        r'©.*',
        r'Crédit.*',
        r'Screen reader only',
        r'aria-hidden="true"',
        r'data-.*?=".*?"',
        r'class=".*?"',
        r'id=".*?"'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text if len(text) > 50 else None

def load_lacroix_cookies(cookie_file, domain, news_cookies_dir):
    """Load La Croix cookies from file - your exact approach"""
    cookie_path = os.path.join(news_cookies_dir, cookie_file)
    cookies = parse_netscape_cookies(cookie_path)
    
    # Filter cookies for La Croix domain
    domain_cookies = []
    for cookie in cookies:
        if domain in cookie.get('domain', '') or cookie.get('domain', '').endswith('.la-croix.com'):
            domain_cookies.append(cookie)
    
    logging.info(f"La Croix: Loaded {len(domain_cookies)} cookies for {domain}")
    return domain_cookies

async def extract_lacroix_article_with_playwright(url, news_cookies_dir, cookie_file='www.la-croix.com_cookies.txt'):
    """Extract La Croix article using Playwright with cookie authentication - your exact approach"""
    
    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        logging.info(f"Added protocol to URL: {url}")
    
    try:
        async with async_playwright() as p:
            # Launch browser (like your Chrome options)
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                ]
            )
            context = await browser.new_context()
            page = await context.new_page()
            
            # STEP 1: Go to main site first (your exact approach)
            logging.info("Loading La Croix main site to establish session...")
            await page.goto("https://www.la-croix.com", wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)  # Like your time.sleep(2)
            
            # STEP 2: Load and add cookies (your exact approach)
            logging.info("Loading cookies...")
            cookies = load_lacroix_cookies(cookie_file, 'la-croix.com', news_cookies_dir)
            
            if cookies:
                logging.info(f"Adding {len(cookies)} cookies to active session...")
                successful_cookies = 0
                failed_cookies = 0
                
                for cookie in cookies:
                    try:
                        await context.add_cookies([cookie])
                        successful_cookies += 1
                        # Log important authentication cookies
                        if any(key in cookie['name'].lower() for key in ['auth', 'session', 'keycloak', 'sso', 'token']):
                            logging.info(f"✓ Added AUTH cookie: {cookie['name']}")
                    except Exception as e:
                        failed_cookies += 1
                        logging.warning(f"❌ Failed to add cookie {cookie['name']}: {e}")
                
                logging.info(f"Cookie Summary: {successful_cookies} successful, {failed_cookies} failed")
            
            # STEP 3: Navigate DIRECTLY to target article (your exact approach)
            logging.info(f"Navigating to article: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            # Wait for page to load (like your WebDriverWait)
            await page.wait_for_selector("h1", timeout=10000)
            await page.wait_for_timeout(3000)  # Additional wait like your time.sleep(3)
            
            # Extract title (your exact method)
            title = None
            try:
                title_element = await page.query_selector("h1.article-title")
                if title_element:
                    title = (await title_element.text_content()).strip()
                    logging.info(f"✓ Title: {title}")
            except Exception as e:
                logging.error(f"❌ Title extraction error: {e}")
            
            # Extract article body (your exact method)
            article_text = None
            try:
                # Get the main article container
                article_container = await page.query_selector(".article-content")
                
                if article_container:
                    # Get all paragraphs (your approach)
                    paragraph_elements = await article_container.query_selector_all("p")
                    
                    if paragraph_elements:
                        text_parts = []
                        for p in paragraph_elements:
                            paragraph_text = (await p.text_content()).strip()
                            if paragraph_text and len(paragraph_text) > 20:
                                clean_paragraph = clean_lacroix_text(paragraph_text)
                                if clean_paragraph:
                                    text_parts.append(clean_paragraph)
                        
                        if text_parts:
                            article_text = ' '.join(text_parts)
                            logging.info(f"✓ Extracted {len(text_parts)} paragraphs ({len(article_text)} chars)")
                        else:
                            logging.error("❌ No valid paragraphs found")
                    else:
                        logging.error("❌ No paragraph elements found")
                else:
                    logging.error("❌ Article container not found")
                    
            except Exception as e:
                logging.error(f"❌ Article extraction error: {e}")
            
            # Extract first image (your exact method)
            image_url = None
            try:
                # Look for images in the article media
                img_element = await page.query_selector(".article-media img[src]")
                if img_element:
                    image_url = await img_element.get_attribute('src')
                    logging.info(f"✓ Image: {image_url}")
            except Exception as e:
                logging.error(f"❌ Image extraction error: {e}")
            
            await browser.close()
            
            if article_text and len(article_text) > 100:
                return {
                    "title": title,
                    "article": article_text,
                    "image": image_url,
                    "url": url
                }
            else:
                logging.error(f"La Croix: Article text too short or empty - possible paywall issue")
                return None
                
    except Exception as e:
        logging.error(f"La Croix Playwright extraction failed: {e}")
        return None

async def extract_lacroix_article(url, news_cookies_dir):
    """Main La Croix extraction function"""
    result = await extract_lacroix_article_with_playwright(url, news_cookies_dir)
    return result 
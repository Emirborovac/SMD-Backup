import asyncio
import logging
import re
import os
import random
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

def clean_leparisien_text(text):
    """Clean Le Parisien article text - your exact approach"""
    if not text:
        return None
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove Le Parisien specific unwanted patterns (your exact list)
    patterns_to_remove = [
        r'À lire aussi',
        r'Newsletter.*?du matin',
        r'S\'inscrire à la newsletter',
        r'Toutes les newsletters',
        r'Un tour de l\'actualité.*?journée',
        r'data-ad-articletheme=".*?"',
        r'data-google-query-id=".*?"',
        r'class=".*?"',
        r'id=".*?"',
        r'style=".*?"',
        r'target="_blank"',
        r'rel="noreferrer"',
        r'aria-label="Advertisement"',
        r'3rd party ad content',
        r'google_ads_iframe.*?',
        r'arcad.*?adm-ad-rendered',
        r'pubstack-article-inread-ads',
        r'lp-pubstack.*?',
        r'margin_bottom_.*?',
        r'text_align_.*?',
        r'lp-f-body-.*?',
        r'Advertisement',
        r'Abonnez-vous',
        r'S\'abonner'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean up extra whitespace and common artifacts
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'<!-- -->', '', text)
    
    return text if len(text) > 50 else None

def load_leparisien_cookies(cookie_file, domain, news_cookies_dir):
    """Load Le Parisien cookies from file - your exact approach"""
    cookie_path = os.path.join(news_cookies_dir, cookie_file)
    cookies = parse_netscape_cookies(cookie_path)
    
    # Filter cookies for Le Parisien domain
    domain_cookies = []
    for cookie in cookies:
        if domain in cookie.get('domain', '') or cookie.get('domain', '').endswith('.leparisien.fr'):
            domain_cookies.append(cookie)
    
    logging.info(f"Le Parisien: Loaded {len(domain_cookies)} cookies for {domain}")
    return domain_cookies

async def extract_leparisien_article_with_playwright(url, news_cookies_dir, cookie_file='www.leparisien.fr_cookies.txt'):
    """Extract Le Parisien article using Playwright with your exact stealth approach"""
    
    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        logging.info(f"Added protocol to URL: {url}")
    
    try:
        async with async_playwright() as p:
            # Launch browser with your exact stealth settings
            browser = await p.chromium.launch(
                headless=True,  # Production mode
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                    '--disable-gpu',
                    '--disable-default-apps',
                    '--disable-translate',
                    '--disable-device-discovery-notifications',
                    '--disable-software-rasterizer',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-field-trial-config',
                    '--disable-back-forward-cache',
                    '--disable-ipc-flooding-protection',
                    '--no-first-run',
                    '--no-service-autorun',
                    '--password-store=basic',
                    '--use-mock-keychain'
                ]
            )
            
            # Your realistic user agents for French market
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
            ]
            
            selected_ua = random.choice(user_agents)
            logging.info(f"🎭 Using User Agent: {selected_ua[:50]}...")
            
            # Create context with your realistic settings for French market (including Paris geolocation)
            context = await browser.new_context(
                user_agent=selected_ua,
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False,
                locale='fr-FR',
                timezone_id='Europe/Paris',
                permissions=['geolocation'],
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0'
                },
                geolocation={'latitude': 48.8566, 'longitude': 2.3522}  # Paris
            )
            
            # Load cookies
            logging.info("Loading cookies...")
            cookies = load_leparisien_cookies(cookie_file, 'leparisien.fr', news_cookies_dir)
            
            if cookies:
                logging.info(f"Adding {len(cookies)} cookies to active session...")
                successful_cookies = 0
                failed_cookies = 0
                
                for cookie in cookies:
                    try:
                        await context.add_cookies([cookie])
                        successful_cookies += 1
                        # Log important authentication cookies
                        if any(key in cookie['name'].lower() for key in ['auth', 'session', 'subscription', 'premium', 'token', 'subscriber']):
                            logging.info(f"✓ Added AUTH cookie: {cookie['name']}")
                    except Exception as e:
                        failed_cookies += 1
                        logging.warning(f"❌ Failed to add cookie {cookie['name']}: {e}")
                
                logging.info(f"Cookie Summary: {successful_cookies} successful, {failed_cookies} failed")
            
            page = await context.new_page()
            
            # Your additional stealth measures
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['fr-FR', 'fr', 'en'],
                });
                
                window.chrome = {
                    runtime: {},
                };
            """)
            
            logging.info(f"🌐 Loading: {url}")
            
            # Navigate with realistic timing
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Extract title (your exact method)
            title = None
            title_selectors = [
                "h1.title_xl",
                "h1",
                ".title_xl",
                ".headline",
                "[data-testid='headline']"
            ]
            
            for selector in title_selectors:
                try:
                    title_element = page.locator(selector).first
                    if await title_element.count() > 0:
                        title = await title_element.text_content()
                        if title:
                            title = title.strip()
                            # Clean up title
                            title = re.sub(r'\s+', ' ', title)
                            title = re.sub(r'&nbsp;', ' ', title)
                            title = clean_leparisien_text(title)
                            logging.info(f"✓ Title: {title}")
                            break
                except:
                    continue
            
            # Extract first image (your exact method)
            image_url = None
            image_selectors = [
                ".pos_rel img.image",
                "img.image",
                "img[src*='leparisien.fr']",
                "img[src*='cloudfront-eu-central-1.images.arcpublishing.com']",
                ".article-image img",
                "figure img"
            ]
            
            for selector in image_selectors:
                try:
                    img_element = page.locator(selector).first
                    if await img_element.count() > 0:
                        image_url = await img_element.get_attribute('src')
                        if image_url:
                            # Handle relative URLs
                            if image_url.startswith('/'):
                                image_url = f"https://www.leparisien.fr{image_url}"
                            logging.info(f"✓ Image: {image_url}")
                            break
                except:
                    continue
            
            # Extract article content (your exact method)
            article_text = None
            try:
                # Le Parisien article content selectors
                content_selectors = [
                    ".article-section",
                    ".article-content",
                    "[data-testid='article-body']",
                    "main article"
                ]
                
                article_container = None
                for selector in content_selectors:
                    try:
                        container = page.locator(selector).first
                        if await container.count() > 0:
                            article_container = container
                            logging.info(f"✓ Found article container with selector: {selector}")
                            break
                    except Exception as e:
                        logging.warning(f"❌ Error with selector {selector}: {e}")
                        continue
                
                if article_container:
                    # Get all paragraphs and headings within content sections
                    text_elements = await article_container.locator("section.content p, section.content h2, section.content h3").all()
                    
                    if text_elements:
                        text_parts = []
                        for element in text_elements:
                            try:
                                element_text = await element.text_content()
                                if element_text and len(element_text.strip()) > 20:
                                    # Skip Le Parisien UI elements and ads
                                    if not any(skip_word in element_text.lower() for skip_word in [
                                        'newsletter', 's\'inscrire', 'toutes les newsletters',
                                        'à lire aussi', 'advertisement', 'google_ads',
                                        'pubstack', 'arcad', 'adm-ad', 'abonnez-vous',
                                        'un tour de l\'actualité', 'pour commencer la journée'
                                    ]):
                                        clean_text = clean_leparisien_text(element_text.strip())
                                        if clean_text and len(clean_text) > 30:
                                            text_parts.append(clean_text)
                            except:
                                continue
                        
                        if text_parts:
                            article_text = ' '.join(text_parts)
                            logging.info(f"✓ Extracted {len(text_parts)} text elements ({len(article_text)} chars)")
                        else:
                            logging.error("❌ No valid text elements found")
                    else:
                        logging.error("❌ No text elements found - trying fallback")
                        
                        # Fallback: extract all paragraphs with specific classes
                        all_paragraphs = await article_container.locator("p.paragraph, p.lp-f-body-02").all()
                        if all_paragraphs:
                            text_parts = []
                            for p in all_paragraphs:
                                try:
                                    p_text = await p.text_content()
                                    if p_text and len(p_text.strip()) > 30:
                                        clean_text = clean_leparisien_text(p_text.strip())
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
                else:
                    logging.error("❌ Could not find article container")
                    
            except Exception as e:
                logging.error(f"❌ Article extraction error: {e}")
            
            await browser.close()
            
            if article_text and len(article_text) > 100:
                return {
                    "title": title,
                    "article": article_text,
                    "image": image_url,
                    "url": url
                }
            else:
                logging.error(f"Le Parisien: Article text too short or empty - possible paywall issue")
                return None
                
    except Exception as e:
        logging.error(f"Le Parisien Playwright extraction failed: {e}")
        return None

async def extract_leparisien_article(url, news_cookies_dir):
    """Main Le Parisien extraction function"""
    result = await extract_leparisien_article_with_playwright(url, news_cookies_dir)
    return result 
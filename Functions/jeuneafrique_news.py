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

def clean_jeune_afrique_text(text):
    """Clean Jeune Afrique article text - your exact approach"""
    if not text:
        return None
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove Jeune Afrique specific unwanted patterns (your exact list)
    patterns_to_remove = [
        r'La Matinale\.',
        r'Chaque matin, recevez les 10 informations clés',
        r'Jeune Afrique utilise votre adresse e-mail',
        r'Consultez notre politique de gestion',
        r'S\'inscrire',
        r'Votre e-mail',
        r'la suite après cette publicité',
        r'A lire :\s*',
        r'Lire dans l\'app',
        r'Publié le\s+\d+\s+\w+\s+\d+',
        r'Lecture :\s+\d+\s+minutes?\.',
        r'Par\s+Jeune Afrique',
        r'data-.*?=".*?"',
        r'class=".*?"',
        r'id=".*?"',
        r'aria-.*?=".*?"',
        r'Advertisement',
        r'3rd party ad content',
        r'Start GAM slot.*?End GAM slot',
        r'© Montage JA',
        r'©.*?Shutterstock.*?Sipa'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean up extra whitespace and common artifacts
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'<!-- -->', '', text)
    
    return text if len(text) > 50 else None

def load_jeuneafrique_cookies(cookie_file, domain, news_cookies_dir):
    """Load Jeune Afrique cookies from file - your exact approach"""
    cookie_path = os.path.join(news_cookies_dir, cookie_file)
    cookies = parse_netscape_cookies(cookie_path)
    
    # Filter cookies for Jeune Afrique domain
    domain_cookies = []
    for cookie in cookies:
        if domain in cookie.get('domain', '') or cookie.get('domain', '').endswith('.jeuneafrique.com'):
            domain_cookies.append(cookie)
    
    logging.info(f"Jeune Afrique: Loaded {len(domain_cookies)} cookies for {domain}")
    return domain_cookies

async def extract_jeuneafrique_article_with_playwright(url, news_cookies_dir, cookie_file='www.jeuneafrique.com_cookies.txt'):
    """Extract Jeune Afrique article using Playwright with your exact stealth approach"""
    
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
            
            # Your realistic user agents (rotate to avoid detection)
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
            ]
            
            selected_ua = random.choice(user_agents)
            logging.info(f"🎭 Using User Agent: {selected_ua[:50]}...")
            
            # Create context with your realistic settings
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
                }
            )
            
            # Load cookies
            logging.info("Loading cookies...")
            cookies = load_jeuneafrique_cookies(cookie_file, 'jeuneafrique.com', news_cookies_dir)
            
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
                "h1.headline__title",
                "h1",
                ".headline__title"
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
                            logging.info(f"✓ Title: {title}")
                            break
                except:
                    continue
            
            # Extract first image (your exact method)
            image_url = None
            image_selectors = [
                ".article__content .box-image img.image",
                ".box-image img",
                ".article__content img",
                "figure img"
            ]
            
            for selector in image_selectors:
                try:
                    img_element = page.locator(selector).first
                    if await img_element.count() > 0:
                        image_url = await img_element.get_attribute('src')
                        if image_url and 'jeuneafrique.com' in image_url:
                            logging.info(f"✓ Image: {image_url}")
                            break
                except:
                    continue
            
            # Extract article content (your exact method)
            article_text = None
            try:
                # Look for Jeune Afrique article content
                content_selectors = [
                    'div[data-mrf-recirculation="Corps d\'article"]',
                    ".article__content",
                    ".article-content"
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
                    # Get all paragraphs and other text elements
                    text_elements = await article_container.locator("p, h2, h3").all()
                    
                    if text_elements:
                        text_parts = []
                        for element in text_elements:
                            try:
                                element_text = await element.text_content()
                                if element_text and len(element_text.strip()) > 15:
                                    # Skip ads, UI elements, and related articles
                                    if not any(skip_word in element_text.lower() for skip_word in [
                                        'publicité', 'newsletter', 's\'inscrire', 'la matinale',
                                        'gam slot', 'advertisement', 'a lire :', 'lire aussi',
                                        'box-read', 'box-ad', 'la suite après cette publicité'
                                    ]):
                                        clean_text = clean_jeune_afrique_text(element_text.strip())
                                        if clean_text and len(clean_text) > 20:
                                            text_parts.append(clean_text)
                            except:
                                continue
                        
                        if text_parts:
                            article_text = ' '.join(text_parts)
                            logging.info(f"✓ Extracted {len(text_parts)} text elements ({len(article_text)} chars)")
                        else:
                            logging.error("❌ No valid text elements found")
                    else:
                        logging.error("❌ No text elements found")
                else:
                    logging.error("❌ Could not find article container - trying fallback")
                    # Fallback: try to find article content by looking for paragraphs directly
                    all_paragraphs = await page.locator("p").all()
                    if all_paragraphs:
                        text_parts = []
                        for p in all_paragraphs:
                            try:
                                p_text = await p.text_content()
                                if p_text and len(p_text.strip()) > 30:
                                    # Skip obvious non-content paragraphs
                                    if not any(skip in p_text.lower() for skip in [
                                        'newsletter', 'publicité', 's\'inscrire', 'cookies',
                                        'a lire :', 'votre e-mail', 'consultez notre politique'
                                    ]):
                                        clean_text = clean_jeune_afrique_text(p_text.strip())
                                        if clean_text and len(clean_text) > 30:
                                            text_parts.append(clean_text)
                            except:
                                continue
                        
                        if text_parts:
                            article_text = ' '.join(text_parts)
                            logging.info(f"✓ Fallback extracted {len(text_parts)} paragraphs ({len(article_text)} chars)")
                        else:
                            logging.error("❌ Fallback found no valid content")
                    
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
                logging.error(f"Jeune Afrique: Article text too short or empty - possible paywall issue")
                return None
                
    except Exception as e:
        logging.error(f"Jeune Afrique Playwright extraction failed: {e}")
        return None

async def extract_jeuneafrique_article(url, news_cookies_dir):
    """Main Jeune Afrique extraction function"""
    result = await extract_jeuneafrique_article_with_playwright(url, news_cookies_dir)
    return result 
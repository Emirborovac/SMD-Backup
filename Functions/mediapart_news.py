import asyncio
import os
import re
import logging
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright

# Mediapart configuration
MEDIAPART_CONFIG = {
    'title_selector': 'h1#page-title',
    'article_container_selector': '.news__body__center__article',
    'paragraphs_selector': '.news__body__center__article p, .news__body__center__article h2[data-mediapart-role="subheading"]',
    'quote_selector': 'figure[data-mediapart-role="quote"] blockquote p',
    'image_selector': '.news__body__center__article figure.media img',
    'wait_for_selector': 'h1#page-title'
}

def clean_mediapart_text(text):
    """Clean Mediapart article text - your exact approach"""
    if not text:
        return None
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove Mediapart specific unwanted patterns (your exact list)
    patterns_to_remove = [
        r'Lire \+ tard',
        r'Offrir l\'article',
        r'Grossir le texte',
        r'Réduire le texte',
        r'Imprimer',
        r'À lire aussi',
        r'Agrandir l\'image',
        r'Fermer',
        r'Recommander',
        r'\d+ commentaires?',
        r'©.*',
        r'Illustration \d+',
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

def load_mediapart_cookies(cookie_file, domain):
    """Load cookies from Netscape format file - EXACT USER METHOD"""
    cookies = []
    try:
        with open(cookie_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line.startswith('#') or not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) >= 7:
                    cookie_domain = parts[0]
                    secure = parts[3] == 'TRUE'
                    name = parts[5]
                    value = parts[6]
                    
                    # Convert to Playwright format (user's approach + Playwright requirements)
                    cookie = {
                        'name': name,
                        'value': value,
                        'domain': cookie_domain,
                        'path': '/',  # Default path
                        'secure': secure
                    }
                    cookies.append(cookie)
                    
    except FileNotFoundError:
        logging.error(f"Cookie file {cookie_file} not found!")
        return []
    except Exception as e:
        logging.error(f"Error loading cookies: {e}")
        return []
    
    logging.info(f"Loaded {len(cookies)} cookies for Mediapart")
    return cookies

async def extract_mediapart_article(url, news_cookies_dir):
    """Extract article content using Playwright for Mediapart"""
    # Fix malformed URLs missing protocol (same as in main.py)
    if url.startswith(':/'):
        url = 'https' + url
    elif not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = urlparse(url).hostname
    if not domain or 'mediapart.fr' not in domain:
        raise ValueError("Invalid Mediapart URL")
    
    # Find cookie file for Mediapart
    cookie_file = os.path.join(news_cookies_dir, f"www.{domain}_cookies.txt")
    if not os.path.exists(cookie_file):
        cookie_file = os.path.join(news_cookies_dir, f"{domain}_cookies.txt")
    
    cookies = load_mediapart_cookies(cookie_file, domain)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        
        try:
            page = await context.new_page()
            
            # STEP 1: Navigate to main site FIRST (like your Selenium script)
            logging.info("Opening Mediapart main site to establish session...")
            await page.goto('https://www.mediapart.fr', wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)  # Wait for initial page load
            
            # STEP 2: Add cookies to active session (like your script)
            if cookies:
                logging.info(f"Adding {len(cookies)} cookies to active session...")
                for cookie in cookies:
                    try:
                        await context.add_cookies([cookie])
                        logging.info(f"Added cookie: {cookie['name']}")
                    except Exception as e:
                        logging.warning(f"Failed to add cookie {cookie['name']}: {e}")
            
            # STEP 3: Navigate DIRECTLY to target article (your exact approach)
            logging.info(f"Navigating to article: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            # Wait for page to load (like your WebDriverWait)
            await page.wait_for_selector("h1", timeout=10000)
            await page.wait_for_timeout(3000)  # Additional wait like your time.sleep(3)
            
            # Extract title (your exact method)
            title = None
            try:
                title_element = await page.query_selector("h1#page-title")
                if title_element:
                    title = (await title_element.text_content()).strip()
                    logging.info(f"✓ Title: {title}")
            except Exception as e:
                logging.error(f"❌ Title extraction error: {e}")
            
            # Extract article body (your exact method)
            article_text = None
            try:
                # Get the main article container (your approach)
                article_container = await page.query_selector(".news__body__center__article")
                
                if article_container:
                    # Get all paragraphs (your approach)
                    paragraph_elements = await article_container.query_selector_all("p")
                    
                    if paragraph_elements:
                        text_parts = []
                        for p in paragraph_elements:
                            paragraph_text = (await p.text_content()).strip()
                            if paragraph_text and len(paragraph_text) > 20:
                                clean_paragraph = clean_mediapart_text(paragraph_text)
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
                # Look for images in the article body (your approach)
                img_element = await page.query_selector(".news__body__center img[src]")
                if img_element:
                    image_url = await img_element.get_attribute('src')
                    logging.info(f"✓ Image: {image_url}")
            except Exception as e:
                logging.error(f"❌ Image extraction error: {e}")
            
            await browser.close()
            
            if not article_text:
                raise ValueError("No Mediapart article content extracted")
            
            return {
                "title": title or "Unknown Title",
                "article": article_text,
                "image": image_url,
                "url": url,
                "domain": domain
            }
            
        except Exception as e:
            await browser.close()
            raise Exception(f"Mediapart Playwright extraction failed: {str(e)}") 
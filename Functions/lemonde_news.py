import asyncio
import http.cookiejar
import os
import re
import logging
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright

# Le Monde configuration
LEMONDE_CONFIG = {
    'title_selector': 'h1.ds-title',
    'article_paragraphs_selector': 'article.article__content p.article__paragraph',
    'image_selector': 'article.article__content figure img',
    'wait_for_selector': 'h1.ds-title'
}

def clean_lemonde_text(text):
    """Clean Le Monde article text to remove unwanted content"""
    if not text:
        return None
    
    # Ensure text is properly decoded as UTF-8
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Le Monde specific cleaning patterns
    patterns_to_remove = [
        r'Lire aussi\s*[:|].*?(?=\s[A-Z]|\.|\s*$)',
        r'Article réservé à nos abonnés',
        r'Newsletter.*?S\'inscrire',
        r'« Chaleur humaine ».*?S\'inscrire',
        r'Comment faire face au défi climatique.*?S\'inscrire',
        r'L\'espace des contributions est réservé aux abonnés.*?S\'abonner',
        r'Abonnez-vous pour accéder.*?discussion',
        r'Contribuer\s*Réutiliser ce contenu',
        r'Réutiliser ce contenu',
        r'Lire plus tard',
        r'S\'abonner\s*$',
        r'Contribuer\s*$',
        r'La lecture de ce contenu est susceptible.*?ci-dessous',
        r'Accepter pour voir le contenu',
        r'Le Monde avec AFP\s*$',
        r'sur X\s*:\s*$'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # General cleaning
    text = re.sub(r'\s*[|:]\s*$', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Clean up common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&apos;', "'")
    
    return text if len(text) > 50 else None

def load_lemonde_cookies(cookie_file, domain):
    """Load cookies from Netscape format file for Le Monde"""
    if not os.path.exists(cookie_file):
        logging.warning(f"Le Monde cookie file not found: {cookie_file}")
        return []
        
    try:
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
        
        cookies = []
        for cookie in jar:
            if domain in cookie.domain or cookie.domain in domain:
                cookies.append({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "expires": cookie.expires if cookie.expires else -1,
                    "httpOnly": bool(cookie._rest.get("HttpOnly", False)),
                    "secure": cookie.secure,
                    "sameSite": "Lax"
                })
        
        logging.info(f"Loaded {len(cookies)} cookies for Le Monde ({domain})")
        return cookies
        
    except Exception as e:
        logging.error(f"Error loading Le Monde cookies from {cookie_file}: {e}")
        return []

async def extract_lemonde_article(url, news_cookies_dir):
    """Extract article content using Playwright for Le Monde"""
    # Fix malformed URLs missing protocol
    if url.startswith(':/'):
        url = 'https' + url
    elif not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = urlparse(url).hostname
    if not domain or 'lemonde.fr' not in domain:
        raise ValueError("Invalid Le Monde URL")
    
    # Find cookie file for Le Monde
    cookie_file = os.path.join(news_cookies_dir, f"www.{domain}_cookies.txt")
    if not os.path.exists(cookie_file):
        cookie_file = os.path.join(news_cookies_dir, f"{domain}_cookies.txt")
    
    cookies = load_lemonde_cookies(cookie_file, domain)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        
        try:
            if cookies:
                await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            logging.info(f"Loading Le Monde URL: {url}")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for content to load
            await page.wait_for_selector(LEMONDE_CONFIG["wait_for_selector"], timeout=10000)
            
            # Extract title
            title = None
            try:
                title_element = await page.query_selector(LEMONDE_CONFIG["title_selector"])
                if title_element:
                    title = (await title_element.text_content()).strip()
                    logging.info(f"Le Monde title extracted: {title}")
            except Exception as e:
                logging.error(f"Le Monde title extraction error: {e}")
            
            # Extract article paragraphs
            article_text = None
            try:
                paragraph_elements = await page.query_selector_all(LEMONDE_CONFIG["article_paragraphs_selector"])
                
                if paragraph_elements:
                    paragraphs = []
                    for element in paragraph_elements:
                        text = await element.text_content()
                        if text and len(text.strip()) > 30:  # Only substantial paragraphs
                            clean_paragraph = clean_lemonde_text(text.strip())
                            if clean_paragraph:
                                paragraphs.append(clean_paragraph)
                    
                    if paragraphs:
                        article_text = ' '.join(paragraphs)
                        logging.info(f"Le Monde: Extracted {len(paragraphs)} paragraphs ({len(article_text)} chars)")
                    else:
                        logging.warning("Le Monde: No valid paragraphs found")
                else:
                    logging.warning("Le Monde: No paragraph elements found")
                    
            except Exception as e:
                logging.error(f"Le Monde article extraction error: {e}")
            
            # Extract image
            image_url = None
            try:
                image_element = await page.query_selector(LEMONDE_CONFIG["image_selector"])
                if image_element:
                    image_url = await image_element.get_attribute('src')
                    # Handle relative URLs
                    if image_url and not image_url.startswith('http'):
                        image_url = urljoin(url, image_url)
                    logging.info(f"Le Monde image extracted: {image_url}")
            except Exception as e:
                logging.error(f"Le Monde image extraction error: {e}")
            
            await browser.close()
            
            if not article_text:
                raise ValueError("No Le Monde article content extracted")
            
            return {
                "title": title or "Unknown Title",
                "article": article_text,
                "image": image_url,
                "url": url,
                "domain": domain
            }
            
        except Exception as e:
            await browser.close()
            raise Exception(f"Le Monde Playwright extraction failed: {str(e)}") 
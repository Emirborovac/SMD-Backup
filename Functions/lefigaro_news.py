import asyncio
import http.cookiejar
import os
import re
import logging
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright

# Le Figaro configuration
FIGARO_CONFIG = {
    'title_selector': 'h1.fig-headline',
    'article_selector': 'article',
    'paragraphs_selector': 'article p.fig-paragraph',
    'image_selector': 'figure.fig-media img',
    'wait_for_selector': 'h1.fig-headline'
}

def clean_figaro_text(text):
    """Clean Le Figaro article text"""
    if not text:
        return None
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove Le Figaro specific unwanted patterns - EXACT MATCH to working script
    patterns_to_remove = [
        r'LE FIGARO\s*-\s*',
        r'EXCLUSIF\s*-\s*',
        r'Réservé aux abonnés',
        r'Cet article est réservé aux abonnés.*?à découvrir\.',
        r'Il vous reste \d+% à découvrir\.',
        r'Vous avez envie de lire la suite\?',
        r'Débloquez tous les articles immédiatement\.',
        r'CONTINUER',
        r'Déjà abonné\?',
        r'Connectez-vous',
        r'Suivre\s*Suivez.*?grâce à l\'application du Figaro',
        r'Accéder à l\'app',
        r'Par\s+[A-Za-z\s]+$',
        r'Il y a \d+ heures',
        r'Copier le lien',
        r'Lien copié',
        r'Lire dans l\'app',
        r'Partager via.*?$',
        r'Bruno Retailleau.*?François Bayrou.*?Boualem Sansal.*?Les Républicains.*?Algérie',
        r'Sujets$'
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean up punctuation and spacing
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text if len(text) > 50 else None

def load_figaro_cookies(cookie_file, domain):
    """Load cookies from Netscape format file for Le Figaro"""
    if not os.path.exists(cookie_file):
        logging.warning(f"Le Figaro cookie file not found: {cookie_file}")
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
        
        logging.info(f"Loaded {len(cookies)} cookies for Le Figaro ({domain})")
        return cookies
        
    except Exception as e:
        logging.error(f"Error loading Le Figaro cookies from {cookie_file}: {e}")
        return []

async def extract_figaro_article(url, news_cookies_dir):
    """Extract article content from Le Figaro URL - EXACT MATCH to working script"""
    # Fix malformed URLs missing protocol
    if url.startswith(':/'):
        url = 'https' + url
    elif not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = urlparse(url).hostname
    
    if not domain or "lefigaro.fr" not in domain:
        raise ValueError("Invalid Le Figaro URL")
    
    # Find cookie file for Le Figaro
    cookie_file = os.path.join(news_cookies_dir, f"www.{domain}_cookies.txt")
    if not os.path.exists(cookie_file):
        cookie_file = os.path.join(news_cookies_dir, f"{domain}_cookies.txt")
    
    cookies = load_figaro_cookies(cookie_file, domain)
    if not cookies:
        logging.warning(f"No cookies loaded for Le Figaro ({domain})")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        try:
            await context.add_cookies(cookies)
            page = await context.new_page()
            
            logging.info(f"Loading Le Figaro URL: {url}")
            await page.goto(url, wait_until='networkidle')
            
            # Wait for content
            await page.wait_for_selector(FIGARO_CONFIG["wait_for_selector"], timeout=10000)
            
            # Extract title
            title = None
            try:
                title_element = await page.query_selector(FIGARO_CONFIG["title_selector"])
                if title_element:
                    title_html = await title_element.inner_html()
                    # Remove HTML tags but keep text
                    title = re.sub(r'<[^>]+>', '', title_html).strip()
                    # Clean up HTML entities
                    title = title.replace('&nbsp;', ' ').replace('&amp;', '&')
                    logging.info(f"Le Figaro title extracted: {title}")
            except Exception as e:
                logging.error(f"Le Figaro title extraction error: {e}")
            
            # Extract article paragraphs
            article_text = None
            try:
                # Get paragraphs that are not in paywall - EXACT MATCH to working script
                paragraph_elements = await page.query_selector_all(f"{FIGARO_CONFIG['paragraphs_selector']}:not(.fig-premium-paywall *)")
                
                if paragraph_elements:
                    paragraphs = []
                    for element in paragraph_elements:
                        text = await element.text_content()
                        if text and len(text.strip()) > 30:
                            clean_paragraph = clean_figaro_text(text.strip())
                            if clean_paragraph and len(clean_paragraph) > 30:
                                paragraphs.append(clean_paragraph)
                    
                    if paragraphs:
                        article_text = ' '.join(paragraphs)
                        logging.info(f"Le Figaro: Extracted {len(paragraphs)} paragraphs ({len(article_text)} chars)")
                    else:
                        logging.warning("Le Figaro: No valid paragraphs found")
                else:
                    logging.warning("Le Figaro: No paragraph elements found")
                    
            except Exception as e:
                logging.error(f"Le Figaro article extraction error: {e}")
            
            # Extract first image
            image_url = None
            try:
                image_element = await page.query_selector(FIGARO_CONFIG["image_selector"])
                if image_element:
                    image_url = await image_element.get_attribute('src')
                    # Handle srcset if src is not available - EXACT MATCH to working script
                    if not image_url:
                        srcset = await image_element.get_attribute('srcset')
                        if srcset:
                            # Get first URL from srcset
                            image_url = srcset.split(',')[0].strip().split(' ')[0]
                    logging.info(f"Le Figaro image extracted: {image_url}")
            except Exception as e:
                logging.error(f"Le Figaro image extraction error: {e}")
            
            await browser.close()
            
            if not article_text:
                raise ValueError("No Le Figaro article content extracted")
            
            return {
                "title": title,
                "article": article_text,
                "image": image_url,
                "url": url,
                "domain": domain
            }
            
        except Exception as e:
            await browser.close()
            raise Exception(f"Le Figaro Playwright extraction failed: {str(e)}") 
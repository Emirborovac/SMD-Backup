import asyncio
import http.cookiejar
import os
import re
import logging
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright

# Le Point configuration
LEPOINT_CONFIG = {
    'title_selector': 'h1',
    'article_container_selector': '#contenu.article-styles',
    'paragraphs_selector': '#contenu.article-styles p',
    'image_selector': '#contenu.article-styles .FirstMedia img',
    'wait_for_selector': 'h1'
}

def clean_lepoint_text(text):
    """Clean Le Point article text to remove unwanted content"""
    if not text:
        return None
    
    # Ensure text is properly decoded as UTF-8
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Le Point specific cleaning patterns
    patterns_to_remove = [
        # Newsletter signup sections
        r'Le point du soir.*?politique de confidentialité\.',
        r'Tous les soirs à partir de 18h.*?Votre inscription a bien été prise en compte',
        r'Recevez l\'information analysée et décryptée.*?MonCompte',
        r'En vous inscrivant, vous acceptez.*?politique de confidentialité\.',
        
        # Reading suggestions and capsules
        r'À LIRE AUSSI.*?(?=\s[A-Z]|\.|$)',
        r'À Découvrir.*?Répondre',
        r'Le Kangourou du jour.*?Répondre',
        
        # Ad and promotional content
        r'Merci !.*?MonCompte',
        r'Votre adresse email n\'est pas valide',
        r'Veuillez renseigner votre adresse email',
        r'S\'inscrire',
        
        # Common Le Point footer elements
        r'conditions générales d\'utilisations',
        r'politique de confidentialité',
        
        # Clean HTML artifacts
        r'&nbsp;',
        r'&amp;',
        r'&quot;',
        r'&lt;',
        r'&gt;',
        r'&apos;'
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

def load_lepoint_cookies(cookie_file, domain):
    """Load cookies from Netscape format file for Le Point"""
    if not os.path.exists(cookie_file):
        logging.warning(f"Le Point cookie file not found: {cookie_file}")
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
        
        logging.info(f"Loaded {len(cookies)} cookies for Le Point ({domain})")
        return cookies
        
    except Exception as e:
        logging.error(f"Error loading Le Point cookies from {cookie_file}: {e}")
        return []

async def extract_lepoint_article(url, news_cookies_dir):
    """Extract article content using Playwright for Le Point"""
    # Fix malformed URLs missing protocol
    if url.startswith(':/'):
        url = 'https' + url
    elif not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = urlparse(url).hostname
    if not domain or 'lepoint.fr' not in domain:
        raise ValueError("Invalid Le Point URL")
    
    # Find cookie file for Le Point
    cookie_file = os.path.join(news_cookies_dir, f"www.{domain}_cookies.txt")
    if not os.path.exists(cookie_file):
        cookie_file = os.path.join(news_cookies_dir, f"{domain}_cookies.txt")
    
    cookies = load_lepoint_cookies(cookie_file, domain)
    
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
            
            logging.info(f"Loading Le Point URL: {url}")
            # Use domcontentloaded instead of networkidle for Le Point
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            # Wait for content to load with shorter timeout
            try:
                await page.wait_for_selector(LEPOINT_CONFIG["wait_for_selector"], timeout=5000)
            except:
                # Fallback - wait a bit longer and try again
                await page.wait_for_timeout(3000)
                await page.wait_for_selector(LEPOINT_CONFIG["wait_for_selector"], timeout=3000)
            
            # Extract title
            title = None
            try:
                title_element = await page.query_selector(LEPOINT_CONFIG["title_selector"])
                if title_element:
                    title_html = await title_element.inner_html()
                    # Remove HTML tags but keep text
                    title = re.sub(r'<[^>]+>', '', title_html).strip()
                    # Clean up HTML entities
                    title = title.replace('&nbsp;', ' ').replace('&amp;', '&')
                    logging.info(f"Le Point title extracted: {title}")
            except Exception as e:
                logging.error(f"Le Point title extraction error: {e}")
            
            # Extract article paragraphs
            article_text = None
            try:
                # First check if article container exists
                container = await page.query_selector(LEPOINT_CONFIG["article_container_selector"])
                if not container:
                    logging.warning("Le Point: Article container not found")
                    # Fallback to body paragraphs
                    paragraph_elements = await page.query_selector_all("p")
                else:
                    paragraph_elements = await page.query_selector_all(LEPOINT_CONFIG["paragraphs_selector"])
                
                if paragraph_elements:
                    paragraphs = []
                    for element in paragraph_elements:
                        # Skip ad containers, newsletter forms, and other unwanted elements
                        parent_classes = await element.evaluate('el => el.closest("[class]")?.className || ""')
                        if any(skip_class in parent_classes.lower() for skip_class in [
                            'slotpub', 'newsletter', 'capsule', 'advertisement', 'teads', 'bloc-1'
                        ]):
                            continue
                        
                        text = await element.text_content()
                        if text and len(text.strip()) > 30:  # Only substantial paragraphs
                            clean_paragraph = clean_lepoint_text(text.strip())
                            if clean_paragraph and len(clean_paragraph) > 30:
                                paragraphs.append(clean_paragraph)
                    
                    if paragraphs:
                        article_text = ' '.join(paragraphs)
                        logging.info(f"Le Point: Extracted {len(paragraphs)} paragraphs ({len(article_text)} chars)")
                    else:
                        logging.warning("Le Point: No valid paragraphs found")
                else:
                    logging.warning("Le Point: No paragraph elements found")
                    
            except Exception as e:
                logging.error(f"Le Point article extraction error: {e}")
            
            # Extract image
            image_url = None
            try:
                image_element = await page.query_selector(LEPOINT_CONFIG["image_selector"])
                if image_element:
                    image_url = await image_element.get_attribute('src')
                    # Handle relative URLs
                    if image_url and not image_url.startswith('http'):
                        image_url = urljoin(url, image_url)
                    logging.info(f"Le Point image extracted: {image_url}")
            except Exception as e:
                logging.error(f"Le Point image extraction error: {e}")
            
            await browser.close()
            
            if not article_text:
                raise ValueError("No Le Point article content extracted")
            
            return {
                "title": title or "Unknown Title",
                "article": article_text,
                "image": image_url,
                "url": url,
                "domain": domain
            }
            
        except Exception as e:
            await browser.close()
            raise Exception(f"Le Point Playwright extraction failed: {str(e)}") 
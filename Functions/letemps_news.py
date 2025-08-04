import asyncio
import http.cookiejar
import os
import re
import logging
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright

# Le Temps configuration
LETEMPS_CONFIG = {
    'title_selector': 'h1.post__title',
    'article_body_selector': '.post-body',
    'paragraphs_selector': '.post-body p',
    'lead_selector': '.post__lead p',
    'image_selector': '.post__cover img',
    'wait_for_selector': 'h1.post__title'
}

def clean_letemps_text(text):
    """Clean Le Temps article text to remove unwanted content"""
    if not text:
        return None
    
    # Ensure text is properly decoded as UTF-8
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Le Temps specific cleaning patterns
    patterns_to_remove = [
        # Newsletter signup sections
        r'Newsletter.*?Chaque vendredi.*?S\'inscrire',
        r'Pour recevoir notre newsletter.*?Créer mon compte',
        r'Chaque vendredi matin.*?de la semaine\.',
        
        # Account/subscription prompts
        r'Créez-vous un compte gratuitement.*?sauvegardés\.',
        r'Déjà un compte.*?Se connecter',
        r'Créer mon compte',
        
        # Share and social media elements
        r'Partager.*?Twitter',
        r'Copier le lien',
        r'Lire plus tard',
        r'S\'inscrire',
        
        # Reading time and metadata
        r'\d+ min\. de lecture',
        r'Publié le.*?Modifié le.*?\.',
        
        # Ad and promotional content
        r'CHF \d+\.- le 1er mois',
        r'J\'en profite →',
        r'Suivez les résultats.*?⚽',
        
        # Newsletter widget content
        r'If you are a human, ignore this field',
        
        # Clean HTML artifacts and entities
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
    
    return text if len(text) > 30 else None

def load_letemps_cookies(cookie_file, domain):
    """Load cookies from Netscape format file for Le Temps"""
    if not os.path.exists(cookie_file):
        logging.warning(f"Le Temps cookie file not found: {cookie_file}")
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
        
        logging.info(f"Loaded {len(cookies)} cookies for Le Temps ({domain})")
        return cookies
        
    except Exception as e:
        logging.error(f"Error loading Le Temps cookies from {cookie_file}: {e}")
        return []

async def extract_letemps_article(url, news_cookies_dir):
    """Extract article content using Playwright for Le Temps"""
    # Fix malformed URLs missing protocol
    if url.startswith(':/'):
        url = 'https' + url
    elif not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = urlparse(url).hostname
    if not domain or 'letemps.ch' not in domain:
        raise ValueError("Invalid Le Temps URL")
    
    # Find cookie file for Le Temps
    cookie_file = os.path.join(news_cookies_dir, f"www.{domain}_cookies.txt")
    if not os.path.exists(cookie_file):
        cookie_file = os.path.join(news_cookies_dir, f"{domain}_cookies.txt")
    
    cookies = load_letemps_cookies(cookie_file, domain)
    
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
            
            logging.info(f"Loading Le Temps URL: {url}")
            # Use domcontentloaded for Le Temps as well
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            # Wait for content to load with shorter timeout
            try:
                await page.wait_for_selector(LETEMPS_CONFIG["wait_for_selector"], timeout=5000)
            except:
                # Fallback - wait a bit longer and try again
                await page.wait_for_timeout(3000)
                await page.wait_for_selector(LETEMPS_CONFIG["wait_for_selector"], timeout=3000)
            
            # Extract title
            title = None
            try:
                title_element = await page.query_selector(LETEMPS_CONFIG["title_selector"])
                if title_element:
                    title = (await title_element.text_content()).strip()
                    logging.info(f"Le Temps title extracted: {title}")
            except Exception as e:
                logging.error(f"Le Temps title extraction error: {e}")
            
            # Extract article paragraphs
            article_text = None
            try:
                # First get the lead/summary
                lead_text = None
                try:
                    lead_element = await page.query_selector(LETEMPS_CONFIG["lead_selector"])
                    if lead_element:
                        lead_text = await lead_element.text_content()
                        lead_text = clean_letemps_text(lead_text.strip()) if lead_text else None
                except Exception as e:
                    logging.warning(f"Le Temps lead extraction warning: {e}")
                
                # Then get the main article body paragraphs
                paragraph_elements = await page.query_selector_all(LETEMPS_CONFIG["paragraphs_selector"])
                
                if paragraph_elements:
                    paragraphs = []
                    
                    # Add lead text first if available
                    if lead_text and len(lead_text) > 30:
                        paragraphs.append(lead_text)
                    
                    for element in paragraph_elements:
                        # Skip ad containers and other unwanted elements
                        parent_classes = await element.evaluate('el => el.closest("[class]")?.className || ""')
                        if any(skip_class in parent_classes.lower() for skip_class in [
                            'newsletter', 'share-button', 'advertisement', 'banner', 'promo'
                        ]):
                            continue
                        
                        text = await element.text_content()
                        if text and len(text.strip()) > 30:  # Only substantial paragraphs
                            clean_paragraph = clean_letemps_text(text.strip())
                            if clean_paragraph and len(clean_paragraph) > 30:
                                paragraphs.append(clean_paragraph)
                    
                    if paragraphs:
                        article_text = ' '.join(paragraphs)
                        logging.info(f"Le Temps: Extracted {len(paragraphs)} paragraphs ({len(article_text)} chars)")
                    else:
                        logging.warning("Le Temps: No valid paragraphs found")
                else:
                    logging.warning("Le Temps: No paragraph elements found")
                    
            except Exception as e:
                logging.error(f"Le Temps article extraction error: {e}")
            
            # Extract image
            image_url = None
            try:
                image_element = await page.query_selector(LETEMPS_CONFIG["image_selector"])
                if image_element:
                    # Try data-src first (lazy loading), then src
                    image_url = await image_element.get_attribute('data-src') or await image_element.get_attribute('src')
                    # Handle relative URLs
                    if image_url and not image_url.startswith('http'):
                        image_url = urljoin(url, image_url)
                    logging.info(f"Le Temps image extracted: {image_url}")
            except Exception as e:
                logging.error(f"Le Temps image extraction error: {e}")
            
            await browser.close()
            
            if not article_text:
                raise ValueError("No Le Temps article content extracted")
            
            return {
                "title": title or "Unknown Title",
                "article": article_text,
                "image": image_url,
                "url": url,
                "domain": domain
            }
            
        except Exception as e:
            await browser.close()
            raise Exception(f"Le Temps Playwright extraction failed: {str(e)}") 
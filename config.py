"""
Configuration file for Social Media Links Scraper

This file contains all configuration settings for the scraper including:
- File paths and cookies
- API keys and credentials  
- Platform-specific settings
- Browser configuration
- Logging configuration
"""

import logging
from pathlib import Path

# =============================================================================
# FILE PATHS AND DIRECTORIES
# =============================================================================

# Cookie file path (unified for all platforms)
UNIFIED_COOKIES_PATH = './cookies/cookies.txt'

# Facebook-specific cookie file path
FACEBOOK_COOKIES_PATH = './cookies/facebook.txt'

# YouTube-specific cookie file path
YOUTUBE_COOKIES_PATH = './cookies/youtube.txt'

# Directories
COOKIES_DIR = Path('./cookies')
FUNCTIONS_DIR = Path('./Functions')

# =============================================================================
# API KEYS AND CREDENTIALS
# =============================================================================

# TikTok API key for captcha solving
TIKTOK_API_KEY = 'bae3e23e1e998bccde1e852a105d099b'  # Replace with actual API key

# =============================================================================
# BROWSER CONFIGURATION
# =============================================================================

# Browser settings
HEADLESS_MODE = True  # Set to True to run browser in headless mode (no GUI)
CHROME_VERSION = 136  # Chrome version for undetected-chromedriver

# Chrome browser arguments
CHROME_ARGUMENTS = [
    "--disable-notifications",
    "--disable-popup-blocking", 
    "--start-maximized",
    "--window-size=1920,1080",
    "--disable-blink-features=AutomationControlled"
]

# =============================================================================
# PLATFORM-SPECIFIC SETTINGS
# =============================================================================

# Instagram settings
INSTAGRAM_CUTOFF_DATE = '2025-04-01'  # Instagram posts older than this date will be ignored
INSTAGRAM_MAX_SCROLL_ATTEMPTS = 100
INSTAGRAM_CONSECUTIVE_NO_NEW_POSTS_LIMIT = 15
INSTAGRAM_GENTLE_SCROLL_AMOUNT = 400  # Pixels to scroll per iteration

# X/Twitter settings
X_CUTOFF_DATE = '2025-04-01'  # X/Twitter posts older than this date will be ignored
X_MAX_NO_VIDEO_SCROLLS = 1000  # Maximum scrolls without finding new videos
X_SCROLL_AMOUNT = 1800  # Pixels to scroll per iteration

# Facebook settings
FACEBOOK_MAX_YEARS = 2  # Facebook videos older than this many years will be ignored
FACEBOOK_MAX_SCROLL_ATTEMPTS = 300
FACEBOOK_CONSECUTIVE_NO_NEW_VIDEOS_LIMIT = 3

# Facebook XPath patterns for different layouts
FACEBOOK_BASE_XPATH_PATTERNS = [
    "/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[1]/div[1]/div/div/div[4]/div/div[5]/div/div/div/div[2]/div/div/div",
    "/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[1]/div[1]/div/div/div[4]/div/div[2]/div/div/div/div[2]/div/div/div"
]

FACEBOOK_DATE_XPATH_PATTERNS = [
    "div/div/div/div/div/div[2]/span[1]/div[2]/div/div[1]/span[1]/div/div/div/span/span",
    "div/div/div/div/div/div[2]/span[1]/div[2]/div/div[1]/span[1]/div/div/div/span",
    "div/div/div/div/div/div[2]/span[1]/div[2]/div/div[1]/span[1]/span/span/span"
]

# TikTok settings
TIKTOK_MAX_VIDEOS = 10000  # Maximum number of TikTok videos to collect
TIKTOK_MAX_ATTEMPTS = 3    # Maximum retries if NO videos found
TIKTOK_RETRY_WAIT = 30     # Wait time between retries in seconds

# TikTok container XPath patterns
TIKTOK_CONTAINER_XPATHS = [
    "/html/body/div[1]/div[2]/div[2]/div/div",
    "/html/body/div[1]/div[2]/div[2]/div/div/div[2]/div[2]",
    "/html/body/div[1]/div[2]/div[2]/div/div/div[2]/div[3]/div",
    "//div[contains(@class, 'DivTimelineTabContainer')]",
    "//div[@data-e2e='user-post-item-list']",
    "/html/body/div[1]/div[2]/div[2]/div/div/div[2]/div[2]/div"
]

# TikTok captcha solver settings
TIKTOK_CAPTCHA_MOUSE_STEP_SIZE = 1
TIKTOK_CAPTCHA_MOUSE_STEP_DELAY_MS = 10

# YouTube settings
YOUTUBE_CUTOFF_DATE = '2025-04-01'  # YouTube videos older than this date will be ignored

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Logging settings
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_HANDLERS = [logging.StreamHandler()]

def configure_logging():
    """Configure logging with the settings defined above"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        handlers=LOG_HANDLERS
    )

# =============================================================================
# DEFAULT CONFIGURATION DICTIONARY
# =============================================================================

def get_default_config():
    """
    Get the default configuration dictionary for the scraper.
    
    Returns:
        dict: Default configuration settings
    """
    return {
        # File paths
        'unified_cookies': UNIFIED_COOKIES_PATH,
        'facebook_cookies': FACEBOOK_COOKIES_PATH,
        'youtube_cookies': YOUTUBE_COOKIES_PATH,
        
        # API keys
        'tiktok_api_key': TIKTOK_API_KEY,
        
        # Browser configuration
        'headless_mode': HEADLESS_MODE,
        
        # Platform-specific cutoff dates and limits
        'x_cutoff_date': X_CUTOFF_DATE,
        'instagram_cutoff_date': INSTAGRAM_CUTOFF_DATE,
        'facebook_max_years': FACEBOOK_MAX_YEARS,
        'tiktok_max_videos': TIKTOK_MAX_VIDEOS,
        'youtube_cutoff_date': YOUTUBE_CUTOFF_DATE
    }

# =============================================================================
# DIRECTORY SETUP
# =============================================================================

def create_directories():
    """Create necessary directories if they don't exist"""
    COOKIES_DIR.mkdir(exist_ok=True)
    FUNCTIONS_DIR.mkdir(exist_ok=True)

# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

def validate_config(config: dict) -> bool:
    """
    Validate configuration settings.
    
    Args:
        config (dict): Configuration dictionary to validate
        
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    required_keys = [
        'unified_cookies',
        'facebook_cookies',
        'youtube_cookies',
        'tiktok_api_key', 
        'headless_mode',
        'x_cutoff_date',
        'instagram_cutoff_date',
        'facebook_max_years',
        'tiktok_max_videos',
        'youtube_cutoff_date'
    ]
    
    for key in required_keys:
        if key not in config:
            logging.error(f"Missing required configuration key: {key}")
            return False
    
    # Validate cookie file exists
    if not Path(config['unified_cookies']).exists():
        logging.warning(f"Cookie file not found: {config['unified_cookies']}")
    
    return True 
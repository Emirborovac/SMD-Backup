from playwright.sync_api import sync_playwright
import requests
import os
import json
import hashlib
from urllib.parse import urlparse

def download_afp_video(url, output_folder=".", custom_filename=None):
    """
    Download video from AFP Forum using Playwright
    
    Args:
        url (str): AFP Forum video URL
        output_folder (str): Directory to save the video
        custom_filename (str, optional): Custom filename for the video
    
    Returns:
        dict: Contains file_path, title, description, and error (if any)
    """
    
    # Generate filename if not provided
    if not custom_filename:
        # Create a unique filename based on URL
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        parsed_url = urlparse(url)
        custom_filename = f"afp_video_{url_hash}.mp4"
    
    # Ensure .mp4 extension
    if not custom_filename.lower().endswith('.mp4'):
        custom_filename = f"{custom_filename}.mp4"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        page = browser.new_page()
        
        try:
            page.goto(url, timeout=30000)  # 30 second timeout
            page.wait_for_timeout(5000) 
            
            # Extract title using the provided XPath
            try:
                title_element = page.locator('//*[@id="ctl00_ContentPH_H1"]')
                title = title_element.text_content().strip() if title_element.count() > 0 else "No Title Found"
            except Exception as e:
                print(f"Error extracting title: {e}")
                title = "No Title Found"
            
            # Extract description using the provided XPath
            try:
                description_element = page.locator('//*[@id="ctl00_ContentPH_DivDocumentDescription"]')
                description = description_element.text_content().strip() if description_element.count() > 0 else "No Description Found"
            except Exception as e:
                print(f"Error extracting description: {e}")
                description = "No Description Found"
            
            print(f"Title: {title}")
            print(f"Description: {description}")
            
            # Extract video source
            video_src = None
            try:
                video_src = page.locator('video').nth(0).get_attribute('src')
                print("Video src (video tag):", video_src)
            except:
                pass
            
            if not video_src:
                try:
                    iframe_src = page.locator('iframe').nth(0).get_attribute('src')
                    print("Iframe src:", iframe_src)
                    video_src = iframe_src 
                except:
                    pass
            
        except Exception as e:
            print(f"Error during page processing: {e}")
            return {
                "file_path": None,
                "title": "Error",
                "description": f"Failed to process page: {str(e)}",
                "error": str(e)
            }
        finally:
            browser.close()
    
    # Download video if source found
    if video_src:
        os.makedirs(output_folder, exist_ok=True)
        output_path = os.path.join(output_folder, custom_filename)
        
        try:
            response = requests.get(video_src, timeout=60)  # 60 second timeout
            response.raise_for_status()
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            print(f"Video downloaded as {output_path}")
            
            return {
                "file_path": output_path,
                "title": title,
                "description": description
            }
            
        except Exception as e:
            print(f"Error downloading video: {e}")
            return {
                "file_path": None,
                "title": title,
                "description": description,
                "error": str(e)
            }
    else:
        print("Video src not found.")
        return {
            "file_path": None,
            "title": title,
            "description": description,
            "error": "Video src not found"
        }


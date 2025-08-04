import os
import re
import csv
import Functions.PyHack as pyk
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/tiktok_downloader.log"),
        logging.StreamHandler()
    ]
)

def sanitize_filename(filename: str) -> str:
    """Sanitize the filename to remove invalid characters."""
    filename = re.sub(r'[<>:"/\\|?*=&]', '', filename)  # Remove invalid characters
    filename = filename.strip()  # Remove leading/trailing whitespace
    return filename

def get_tiktok_caption(metadata_path):
    """Extract the video description from the metadata CSV file."""
    try:
        with open(metadata_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            first_data_row = next(reader, None)
            if first_data_row and len(first_data_row) > 8:
                # Video description is typically in column 8 (index 8)
                return first_data_row[8]
        return None
    except Exception as e:
        logging.error(f"Error reading caption: {e}")
        return None

def download_tiktok_video(video_url, output_dir):
    """Download TikTok video and extract metadata."""
    logging.info(f"Starting TikTok video download for URL: {video_url}")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Specify browser for PyHack
    pyk.specify_browser('chrome')
    
    # Create a unique metadata filename
    metadata_filename = os.path.join(output_dir, f"tiktok_metadata_{int(time.time())}.csv")
    
    try:
        # Download the video using PyHack
        logging.info(f"Calling save_tiktok for URL: {video_url}")
        pyk.save_tiktok(
            video_url,
            save_video=True,
            metadata_fn=metadata_filename,
            save_path=output_dir
        )
        
        # Generate expected filename based on video URL
        video_id = video_url.split('/')[-1].split('?')[0]  # Remove query parameters
        video_filename = f"tiktok_video_{video_id}.mp4"
        video_filename = sanitize_filename(video_filename)  # Sanitize filename
        
        # Check if the file exists at expected path
        video_path = os.path.join(output_dir, video_filename)
        if os.path.exists(video_path):
            logging.info(f"Downloaded video found at expected path: {video_path}")
        else:
            # Fallback: Extract video URL using regex from original URL
            regex_url = re.findall(r'(?<=\.com/)(.+?)(?=\?|$)', video_url)
            if regex_url:
                alt_filename = regex_url[0].replace('/', '_') + '.mp4'
                alt_path = os.path.join(output_dir, alt_filename)
                if os.path.exists(alt_path):
                    video_path = alt_path
                    logging.info(f"Downloaded video found using regex URL: {video_path}")
                else:
                    # Last resort: Find the most recent mp4 file
                    mp4_files = [f for f in os.listdir(output_dir) if f.endswith('.mp4')]
                    if mp4_files:
                        mp4_files.sort(key=lambda f: os.path.getmtime(os.path.join(output_dir, f)), reverse=True)
                        video_path = os.path.join(output_dir, mp4_files[0])
                        logging.info(f"Downloaded video found using most recent file: {video_path}")
                    else:
                        logging.error("No mp4 files found in output directory")
                        raise FileNotFoundError("No .mp4 files found after download")
        
        # Extract caption from metadata
        caption = get_tiktok_caption(metadata_filename)
        if caption:
            logging.info(f"Caption extracted: {caption[:100]}...")  # Log first 100 chars
        else:
            caption = "No description available"
            logging.warning("No caption found in metadata")
        
        # Set title to "TikTok Video"
        title = "TikTok Video"
        
        # Return the result dictionary
        return {
            "file_path": video_path,
            "title": title,
            "description": caption
        }
    
    except Exception as e:
        logging.error(f"Error downloading TikTok video: {e}")
        return None
    
    finally:
        # Clean up metadata file
        try:
            if os.path.exists(metadata_filename):
                os.remove(metadata_filename)
                logging.info(f"Removed temporary metadata file: {metadata_filename}")
        except Exception as e:
            logging.error(f"Error removing metadata file: {e}")
    
    

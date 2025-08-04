import os
import hashlib
import logging
import yt_dlp

# Define the path to the Netscape cookie file
COOKIE_FILE_PATH = "./cookies/x.txt"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/video_downloader.log"),
        logging.StreamHandler()
    ]
)

def download_x_video(video_url, output_dir):
    """
    Download a video from X/Twitter using yt-dlp with cookies, enforcing H.264 codec.
    Returns video file path and metadata.
    """
    try:
        # Generate unique output filename
        hashed_name = hashlib.md5(video_url.encode()).hexdigest() + ".mp4"
        output_file = os.path.join(output_dir, hashed_name)

        ydl_opts = {
            'outtmpl': output_file,
            'format': 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4][vcodec^=avc1]',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'cookiefile': COOKIE_FILE_PATH,
            'writeinfojson': True,
            'quiet': False,
            'verbose': True
        }

        logging.info(f"Starting yt-dlp download: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

        # Extract metadata
        title = info.get('title', 'X Video')
        description = info.get('description', 'No description available')

        logging.info(f"Download completed: {output_file}")
        return {
            "file_path": output_file,
            "title": title,
            "description": description
        }

    except Exception as e:
        logging.error(f"yt-dlp failed: {e}")
        return None

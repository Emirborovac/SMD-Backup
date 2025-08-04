from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import hashlib
from urllib.parse import urlparse, unquote
from Functions.facebook_function import download_facebook_video
from Functions.instagram_function import download_instagram_reel
from Functions.tiktok_function import download_tiktok_video
from Functions.x_function import download_x_video
from Functions.afp_function import download_afp_video
from newspaper import Article
import yt_dlp
import re
import logging
import json
import sqlite3
from datetime import datetime, timedelta
import uuid
import subprocess
from pathlib import Path

# Setup subtitle-specific logging
def setup_subtitle_logger():
    """Setup dedicated logger for subtitle processing"""
    logger = logging.getLogger('subtitle_processor')
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create logs directory if it doesn't exist
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Create file handler with timestamp
    log_filename = logs_dir / f'subtitle_processing_{datetime.now().strftime("%Y%m%d")}.log'
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

def log_claude_response(logger, translated_data, operation_id):
    """Log Claude response with first 20 words"""
    try:
        if not translated_data:
            logger.info(f"[{operation_id}] Claude response: Empty/None")
            return
        
        # Get success status and comment
        success = translated_data.get('success', False)
        comment = translated_data.get('comment', '')
        
        # Count translated segments
        translated_count = sum(1 for k in translated_data.keys() if k not in ['success', 'comment'])
        
        # Get first translated text for preview
        first_text = ""
        for key, value in translated_data.items():
            if key not in ['success', 'comment'] and isinstance(value, dict):
                first_text = value.get('s', '')[:200]  # First 200 chars
                break
        
        # Get first 20 words from first translation
        first_words = ' '.join(first_text.split()[:20]) if first_text else "No text content"
        
        logger.info(f"[{operation_id}] Claude Response - Success: {success}, Segments: {translated_count}")
        logger.info(f"[{operation_id}] Claude Comment: {comment}")
        logger.info(f"[{operation_id}] First 20 words: {first_words}")
        
    except Exception as e:
        logger.error(f"[{operation_id}] Error logging Claude response: {e}")

# Initialize subtitle logger
subtitle_logger = setup_subtitle_logger()
from tiktok_captcha_solver import make_undetected_chromedriver_solver
import undetected_chromedriver as uc
import config
from typing import Dict
import re
import requests
import asyncio
from Functions.lemonde_news import extract_lemonde_article
from Functions.lefigaro_news import extract_figaro_article
from Functions.lepoint_news import extract_lepoint_article
from Functions.letemps_news import extract_letemps_article
from Functions.mediapart_news import extract_mediapart_article
from Functions.lacroix_news import extract_lacroix_article
from Functions.bloomberg_news import extract_bloomberg_article
from Functions.thetimes_news import extract_thetimes_article
from Functions.jeuneafrique_news import extract_jeuneafrique_article
from Functions.liberation_news import extract_liberation_article
from Functions.leparisien_news import extract_leparisien_article
from Functions.nytimes_news import extract_nytimes_article

# Transcription imports
import tempfile
from pathlib import Path
import traceback
import time


app = Flask(__name__)
# Configure Flask to properly handle Unicode in JSON responses
app.json.ensure_ascii = False
# Configure logging
logging.basicConfig(level=logging.INFO)
# Path to cookies file
COOKIES_FILE = "./cookies/cookies.txt"
# Output directory
OUTPUT_DIR = "./downloads"

# Transcription Configuration
def load_transcription_env():
    """Load transcription configuration from .env file"""
    config = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        print("❌ .env file not found. Transcription features will be disabled.")
        return {}
    return config

# Load transcription configuration
TRANSCRIPTION_CONFIG = load_transcription_env()
SPEECHMATICS_API_KEY = TRANSCRIPTION_CONFIG.get('SPEECHMATICS_API_KEY')
CLAUDE_API_KEY = TRANSCRIPTION_CONFIG.get('CLAUDE_API_KEY')
CLAUDE_MODEL = TRANSCRIPTION_CONFIG.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
SOURCE_LANGUAGE = TRANSCRIPTION_CONFIG.get('SOURCE_LANGUAGE', 'auto')
MAX_LINE_LENGTH = int(TRANSCRIPTION_CONFIG.get('MAX_LINE_LENGTH', 60))
MAX_LINES = int(TRANSCRIPTION_CONFIG.get('MAX_LINES', 1))
OPERATING_POINT = TRANSCRIPTION_CONFIG.get('OPERATING_POINT', 'enhanced')
ENABLE_POST_PROCESSING = TRANSCRIPTION_CONFIG.get('ENABLE_POST_PROCESSING', 'true').lower() == 'true'
PROCESS_ORIGINAL_MATCHING = TRANSCRIPTION_CONFIG.get('PROCESS_ORIGINAL_MATCHING', 'true').lower() == 'true'

# Token and cost configuration
INPUT_TOKEN_COST = 15 / 1_000_000  # $15 per 1M tokens
OUTPUT_TOKEN_COST = 75 / 1_000_000  # $75 per 1M tokens
MAX_INPUT_TOKENS = 190_000  # 200k with 5% safety margin
MAX_OUTPUT_TOKENS = 30_400  # 32k with 5% safety margin
CHUNK_SAFETY_TOKENS = 20_000  # Conservative chunk size for output safety

# Transcription Functions (IDENTICAL logic from transcribe_api.py)
def speechmatics_transcribe(file_path):
    """Send file to Speechmatics and get SRT"""
    print(f"🎙️ Transcribing {file_path.name}...")
    
    config = {
        "type": "transcription",
        "transcription_config": {
            "language": SOURCE_LANGUAGE,
            "diarization": "speaker",
            "operating_point": OPERATING_POINT
        },
        "output_config": {
            "srt_overrides": {
                "max_line_length": MAX_LINE_LENGTH,
                "max_lines": MAX_LINES
            }
        }
    }
    
    headers = {'Authorization': f'Bearer {SPEECHMATICS_API_KEY}'}
    
    # Upload file
    with open(file_path, 'rb') as audio_file:
        files = {
            'data_file': (file_path.name, audio_file, 'audio/mpeg'),
            'config': (None, json.dumps(config), 'application/json')
        }
        
        response = requests.post('https://asr.api.speechmatics.com/v2/jobs', headers=headers, files=files)
        response.raise_for_status()
        job_id = response.json()['id']
        print(f"✅ Job created: {job_id}")
    
    # Wait for completion
    print("⏳ Waiting for transcription...")
    for attempt in range(60):
        response = requests.get(f'https://asr.api.speechmatics.com/v2/jobs/{job_id}', headers=headers)
        status = response.json()['job']['status']
        
        if status == 'done':
            print("✅ Transcription completed!")
            break
        elif status == 'rejected':
            raise Exception(f"Job rejected: {response.json()['job'].get('errors', 'Unknown error')}")
        
        if attempt % 5 == 0:
            print(f"Status: {status}")
        time.sleep(60)
    else:
        raise Exception("Timeout waiting for transcription")
    
    # Download SRT
    response = requests.get(f'https://asr.api.speechmatics.com/v2/jobs/{job_id}/transcript?format=srt', headers=headers)
    response.raise_for_status()
    
    # Ensure proper UTF-8 decoding
    response.encoding = 'utf-8'
    return response.text

def srt_to_json(srt_content):
    """Convert SRT to JSON format"""
    print("🔄 Converting to JSON...")
    
    blocks = srt_content.strip().split('\n\n')
    json_data = {}
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            number = lines[0].strip()
            timestamp = lines[1].strip()
            subtitle_text = ' '.join(lines[2:]).strip()
            
            json_data[number] = {
                "t": timestamp,
                "s": subtitle_text
            }
    
    print(f"✅ Converted {len(json_data)} segments")
    return json_data

def json_to_srt(subtitle_json):
    """Convert JSON subtitle format back to SRT"""
    srt_lines = []
    
    # Sort by segment number
    sorted_segments = sorted(
        [(int(k), v) for k, v in subtitle_json.items() if k not in ['success', 'comment']],
        key=lambda x: x[0]
    )
    
    for segment_num, segment_data in sorted_segments:
        srt_lines.append(str(segment_num))
        srt_lines.append(segment_data['t'])
        srt_lines.append(segment_data['s'])
        srt_lines.append('')  # Empty line between segments
    
    return '\n'.join(srt_lines)

def parse_timestamp(timestamp_str):
    """Parse SRT timestamp to milliseconds"""
    try:
        # Format: "00:00:01,730"
        time_part, ms_part = timestamp_str.split(',')
        hours, minutes, seconds = map(int, time_part.split(':'))
        milliseconds = int(ms_part)
        
        # Validate ranges
        if hours < 0 or minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59 or milliseconds < 0 or milliseconds > 999:
            print(f"     WARNING: Invalid timestamp values in '{timestamp_str}', using 0")
            return 0
        
        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        return max(0, total_ms)  # Ensure non-negative result
        
    except (ValueError, IndexError) as e:
        print(f"     ERROR: Failed to parse timestamp '{timestamp_str}': {e}, using 0")
        return 0

def format_timestamp(total_ms):
    """Convert milliseconds back to SRT timestamp format"""
    # Ensure non-negative timestamp
    if total_ms < 0:
        print(f"     WARNING: Negative timestamp {total_ms}ms, using 0")
        total_ms = 0
    
    milliseconds = total_ms % 1000
    total_seconds = total_ms // 1000
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    # Ensure all values are within valid ranges
    hours = max(0, min(99, hours))  # SRT supports up to 99 hours
    minutes = max(0, min(59, minutes))
    seconds = max(0, min(59, seconds))
    milliseconds = max(0, min(999, milliseconds))
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def calculate_word_based_timing(text, total_duration_ms):
    """Calculate timing per word for fair timestamp distribution"""
    words = text.split()
    if not words:
        return 0
    return total_duration_ms / len(words)

def find_punctuation_split_point(text, char_limit):
    """Find the best punctuation point to split text - aggressive version"""
    punctuation_marks = '.,:;!?-'
    
    # Find all punctuation positions, but exclude commas in numbers
    punct_positions = []
    for i, char in enumerate(text):
        if char in punctuation_marks:
            # Special handling for commas - don't split if it's part of a number
            if char == ',':
                # Check if comma is part of a number like "1,200" or "about 1,500 people"
                is_number_comma = False
                
                # Look for digits before the comma (within reasonable distance)
                for j in range(max(0, i-5), i):
                    if text[j].isdigit():
                        # Look for digits after the comma
                        for k in range(i+1, min(len(text), i+5)):
                            if text[k].isdigit():
                                is_number_comma = True
                                break
                        break
                
                if is_number_comma:
                    continue  # Skip this comma, it's part of a number
            punct_positions.append(i)
    
    if not punct_positions:
        return -1, "no_punctuation"
    
    # AGGRESSIVE STRATEGY: For very long segments, be more flexible
    text_length = len(text)
    is_very_long = text_length > char_limit * 1.5  # 50% longer than limit
    
    if len(punct_positions) == 1:
        # Single punctuation: split right after it (even if unbalanced for long segments)
        split_pos = punct_positions[0]
        first_part = text[:split_pos + 1].strip()
        second_part = text[split_pos + 1:].strip()
        
        # For very long segments, accept even unbalanced splits
        if is_very_long or (len(first_part) >= 5 and len(second_part) >= 5):
            return split_pos, "single_punctuation"
        else:
            return -1, "single_too_unbalanced"
    else:
        # Multiple punctuation: Try different strategies
        
        # Strategy 1: Find best balanced split
        best_pos = -1
        for pos in reversed(punct_positions):
            first_part = text[:pos + 1].strip()
            second_part = text[pos + 1:].strip()
            
            # Relaxed requirements for very long segments
            min_length = 5 if is_very_long else 8
            if len(first_part) >= min_length and len(second_part) >= min_length:
                best_pos = pos
                break
        
        if best_pos > 0:
            return best_pos, "multiple_balanced"
        
        # Strategy 2: For very long segments, use ANY punctuation that's not too close to edges
        if is_very_long:
            for pos in reversed(punct_positions):
                # Avoid splitting too close to the beginning or end
                if pos > text_length * 0.2 and pos < text_length * 0.8:
                    first_part = text[:pos + 1].strip()
                    second_part = text[pos + 1:].strip()
                    if len(first_part) >= 3 and len(second_part) >= 3:
                        return pos, "multiple_aggressive"
        
        # Strategy 3: Last resort - use the last punctuation
        split_pos = punct_positions[-1]
        first_part = text[:split_pos + 1].strip()
        second_part = text[split_pos + 1:].strip()
        
        if len(first_part) >= 3 and len(second_part) >= 3:
            return split_pos, "multiple_last_resort"
    
    return -1, "no_good_split"

def split_advanced_segments(srt_content, char_limit, pass_name):
    """Advanced segment splitting with word-based timing"""
    print(f"🔧 {pass_name}: Processing segments >{char_limit} characters...")
    
    # Parse SRT into segments
    blocks = srt_content.strip().split('\n\n')
    segments = []
    
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            segment_num = int(lines[0])
            timestamp = lines[1]
            text = ' '.join(lines[2:])
            segments.append({
                'num': segment_num,
                'timestamp': timestamp,
                'text': text
            })
    
    # Process segments for splitting
    new_segments = []
    splits_made = 0
    
    for segment in segments:
        text = segment['text'].strip()  # Ensure we're checking trimmed text
        
        # Check if segment needs splitting - be more aggressive for very long segments
        word_count = len(text.split())
        is_very_long = len(text) > char_limit * 1.5
        
        # For very long segments, process even with fewer words
        should_process = (len(text) > char_limit and word_count >= 3) or (is_very_long and word_count >= 2)
        
        if should_process:
            print(f"   Processing segment {segment['num']}: '{text[:50]}...' ({len(text)} chars)")
            
            # Parse original timestamp
            start_time, end_time = segment['timestamp'].split(' --> ')
            start_ms = parse_timestamp(start_time)
            end_ms = parse_timestamp(end_time)
            total_duration = end_ms - start_ms
            
            # Try to find punctuation split point
            split_pos, strategy = find_punctuation_split_point(text, char_limit)
            
            # AGGRESSIVE SPLITTING LOGIC
            split_successful = False
            
            if split_pos > 0:
                # Split at punctuation
                first_part = text[:split_pos + 1].strip()
                second_part = text[split_pos + 1:].strip()
                
                # For very long segments, accept almost any split
                is_very_long = len(text) > char_limit * 1.5
                min_part_length = 2 if is_very_long else 3
                
                if len(first_part) >= min_part_length and len(second_part) >= min_part_length:
                    split_successful = True
                    print(f"     Split by {strategy}: '{first_part}' | '{second_part}'")
                else:
                    print(f"     Punctuation split would create parts too small")
            
            # If punctuation splitting failed, try word boundary splitting
            if not split_successful:
                print(f"     Trying word boundary split...")
                
                # Find a good word boundary near the middle
                target_pos = len(text) // 2
                
                # Look for spaces around the target position
                best_space_pos = -1
                
                # First try: look for spaces within 20% of target position
                search_range = max(10, int(len(text) * 0.2))
                for offset in range(0, search_range):
                    # Check positions before and after target
                    for pos in [target_pos - offset, target_pos + offset]:
                        if 0 < pos < len(text) - 1 and text[pos] == ' ':
                            best_space_pos = pos
                            break
                    if best_space_pos > 0:
                        break
                
                # Second try: any space position that creates reasonable parts
                if best_space_pos == -1:
                    for i, char in enumerate(text):
                        if char == ' ' and i > len(text) * 0.2 and i < len(text) * 0.8:
                            best_space_pos = i
                            break
                
                if best_space_pos > 0:
                    first_part = text[:best_space_pos].strip()
                    second_part = text[best_space_pos:].strip()
                    
                    if len(first_part) >= 3 and len(second_part) >= 3:
                        split_pos = best_space_pos - 1  # Adjust for word boundary
                        split_successful = True
                        strategy = "word_boundary"
                        print(f"     Split by word boundary: '{first_part}' | '{second_part}'")
            
            # If still no successful split for very long segments, force split
            if not split_successful and len(text) > char_limit * 1.8:  # 80% longer than limit
                print(f"     Forcing split on very long segment ({len(text)} chars)")
                mid_point = len(text) // 2
                first_part = text[:mid_point].strip()
                second_part = text[mid_point:].strip()
                split_pos = mid_point - 1
                split_successful = True
                strategy = "forced_split"
                print(f"     Forced split: '{first_part}' | '{second_part}'")
            
            # If we couldn't split at all, keep original
            if not split_successful:
                print(f"     No viable split found, keeping original")
                new_segments.append(segment)
                continue
            
            # Check if segment is long enough to split safely
            min_segment_duration = 200  # 200ms minimum per segment
            required_total_duration = min_segment_duration * 2 + 100  # 500ms minimum total
            
            if total_duration < required_total_duration:
                print(f"     Segment too short to split safely ({total_duration}ms < {required_total_duration}ms), keeping original")
                new_segments.append(segment)
                continue
            
            # Calculate timing based on the split we made with proper gaps
            gap_ms = 30  # 30ms gap between segments
            first_words = len(first_part.split())
            second_words = len(second_part.split())
            total_words = first_words + second_words
            
            # Reserve time for the gap
            available_duration = total_duration - gap_ms
            
            if available_duration <= min_segment_duration * 2:
                print(f"     Segment too short to split with gaps ({total_duration}ms), keeping original")
                new_segments.append(segment)
                continue
            
            if total_words > 0:
                # Calculate ideal word-based duration (from available time minus gap)
                ideal_first_duration = int((first_words / total_words) * available_duration)
                
                # Apply minimum duration constraints carefully
                first_duration = max(min_segment_duration, ideal_first_duration)
                second_duration = available_duration - first_duration
                
                # If second segment would be too short, adjust both
                if second_duration < min_segment_duration:
                    second_duration = min_segment_duration
                    first_duration = available_duration - second_duration
                
                # Final check - if first segment is now too short, use equal split
                if first_duration < min_segment_duration:
                    first_duration = available_duration // 2
                    second_duration = available_duration - first_duration
                
                first_end_time = start_ms + first_duration
                second_start_time = first_end_time + gap_ms
            else:
                # Fallback to equal split with minimum durations
                first_duration = max(min_segment_duration, available_duration // 2)
                first_end_time = start_ms + first_duration
                second_start_time = first_end_time + gap_ms
            
            # Final sanity check - ensure valid timestamps
            if first_end_time <= start_ms or second_start_time >= end_ms:
                print(f"     Invalid timing calculated with gaps, keeping original")
                new_segments.append(segment)
                continue
            
            # Calculate actual durations for logging
            actual_first_duration = first_end_time - start_ms
            actual_second_duration = end_ms - second_start_time
            
            print(f"     Timing with gap: {first_words}w/{second_words}w = {actual_first_duration}ms + {gap_ms}ms gap + {actual_second_duration}ms")
            
            # Create two segments with proper gaps
            first_segment_timestamp = f"{start_time} --> {format_timestamp(first_end_time)}"
            second_segment_timestamp = f"{format_timestamp(second_start_time)} --> {end_time}"
            
            # Double-check for zero-duration segments before creating
            if first_end_time == start_ms:
                print(f"     ERROR: First segment would have zero duration, keeping original")
                new_segments.append(segment)
                continue
            if second_start_time == end_ms:
                print(f"     ERROR: Second segment would have zero duration, keeping original")
                new_segments.append(segment)
                continue
            
            new_segments.append({
                'num': segment['num'],
                'timestamp': first_segment_timestamp,
                'text': first_part
            })
            
            new_segments.append({
                'num': segment['num'] + 0.5,  # Temporary number for sorting
                'timestamp': second_segment_timestamp,
                'text': second_part
            })
            
            splits_made += 1
        else:
            # No splitting needed
            new_segments.append(segment)
    
    # Sort segments by number and renumber properly
    new_segments.sort(key=lambda x: x['num'])
    
    # Filter out any invalid segments before final processing
    valid_segments = []
    for segment in new_segments:
        text = segment['text'].strip()
        timestamp = segment['timestamp']
        
        # Skip empty segments
        if not text or len(text) < 2:
            print(f"     Filtering out empty segment: '{text}'")
            continue
            
        # Skip segments with invalid timestamps
        if ' --> ' in timestamp:
            start_time, end_time = timestamp.split(' --> ')
            
            # Check for same start/end timestamps
            if start_time == end_time:
                print(f"     Filtering out zero-duration segment: {timestamp}")
                continue
            
            # Parse and validate timestamps
            start_ms = parse_timestamp(start_time)
            end_ms = parse_timestamp(end_time)
            
            # Check for invalid or reversed timestamps
            if start_ms >= end_ms:
                print(f"     Filtering out invalid timestamp order: {timestamp} ({start_ms}ms >= {end_ms}ms)")
                continue
            
            # Check for very short duration (less than 50ms is suspicious)
            duration = end_ms - start_ms
            if duration < 50:
                print(f"     Filtering out extremely short segment: {timestamp} ({duration}ms)")
                continue
        
        valid_segments.append(segment)
    
    # Renumber segments sequentially
    for i, segment in enumerate(valid_segments, 1):
        segment['num'] = i
    
    # Rebuild SRT content
    srt_lines = []
    for segment in valid_segments:
        srt_lines.append(str(segment['num']))
        srt_lines.append(segment['timestamp'])
        srt_lines.append(segment['text'])
        srt_lines.append('')
    
    result = '\n'.join(srt_lines)
    
    filtered_count = len(new_segments) - len(valid_segments)
    if filtered_count > 0:
        print(f"     Filtered out {filtered_count} invalid/empty segments")
    
    print(f"✅ {pass_name} complete: {len(segments)} → {len(valid_segments)} segments ({splits_made} splits made)")
    
    return result

def redistribute_original_text(original_srt_content, processed_srt_content):
    """Redistribute original text using processed timestamps and segment count"""
    print("🔄 Final step: Redistributing original text with optimized timing...")
    
    # Parse original SRT
    original_blocks = original_srt_content.strip().split('\n\n')
    original_texts = []
    
    for block in original_blocks:
        if not block.strip():
            continue
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            text = ' '.join(lines[2:]).strip()
            if text:
                original_texts.append(text)
    
    # Parse processed SRT to get timestamps
    processed_blocks = processed_srt_content.strip().split('\n\n')
    processed_segments = []
    
    for block in processed_blocks:
        if not block.strip():
            continue
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            segment_num = int(lines[0])
            timestamp = lines[1]
            processed_segments.append({
                'num': segment_num,
                'timestamp': timestamp
            })
    
    if not original_texts or not processed_segments:
        print("     No content to redistribute, returning processed version")
        return processed_srt_content
    
    # Combine all original text
    full_original_text = ' '.join(original_texts)
    original_words = full_original_text.split()
    
    if not original_words:
        print("     No original words found, returning processed version")
        return processed_srt_content
    
    # Calculate words per segment
    total_segments = len(processed_segments)
    words_per_segment = len(original_words) / total_segments
    
    print(f"     Redistributing {len(original_words)} words across {total_segments} segments (~{words_per_segment:.1f} words/segment)")
    
    # Redistribute words across segments
    redistributed_segments = []
    word_index = 0
    
    for i, segment in enumerate(processed_segments):
        # Calculate how many words this segment should get
        expected_words_end = int((i + 1) * words_per_segment)
        segment_words = original_words[word_index:expected_words_end]
        
        # Ensure we don't go beyond available words
        if expected_words_end > len(original_words):
            segment_words = original_words[word_index:]
        
        segment_text = ' '.join(segment_words).strip()
        
        # Ensure we have some text (fallback to single word if needed)
        if not segment_text and word_index < len(original_words):
            segment_text = original_words[word_index]
            word_index += 1
        elif segment_words:
            word_index = expected_words_end
        
        if segment_text:
            redistributed_segments.append({
                'num': segment['num'],
                'timestamp': segment['timestamp'],
                'text': segment_text
            })
    
    # Handle any remaining words in the last segment
    if word_index < len(original_words):
        remaining_words = original_words[word_index:]
        if redistributed_segments:
            # Add remaining words to the last segment
            redistributed_segments[-1]['text'] += ' ' + ' '.join(remaining_words)
        else:
            # Create a segment with remaining words using the last timestamp
            redistributed_segments.append({
                'num': len(processed_segments),
                'timestamp': processed_segments[-1]['timestamp'] if processed_segments else "00:00:00,000 --> 00:00:01,000",
                'text': ' '.join(remaining_words)
            })
    
    # Build final SRT
    srt_lines = []
    for segment in redistributed_segments:
        srt_lines.append(str(segment['num']))
        srt_lines.append(segment['timestamp'])
        srt_lines.append(segment['text'])
        srt_lines.append('')
    
    result = '\n'.join(srt_lines)
    
    print(f"✅ Redistribution complete: Original text spread across {len(redistributed_segments)} optimized segments")
    
    return result

def group_continuous_subtitles_for_timing(srt_content, max_gap_ms=500):
    """Group continuous subtitles based on time gaps for timing redistribution"""
    blocks = srt_content.strip().split('\n\n')
    segments = []
    
    # Parse segments
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            try:
                number = int(lines[0].strip())
                timestamp_line = lines[1].strip()
                text = '\n'.join(lines[2:]).strip()
                
                start_str, end_str = timestamp_line.split(' --> ')
                start_ms = parse_timestamp(start_str.strip())
                end_ms = parse_timestamp(end_str.strip())
                
                segments.append({
                    'number': number,
                    'start_ms': start_ms,
                    'end_ms': end_ms,
                    'text': text
                })
            except (ValueError, IndexError):
                continue
    
    if not segments:
        return []
    
    # Group continuous segments
    groups = []
    current_group = [segments[0]]
    
    for i in range(1, len(segments)):
        prev_segment = segments[i-1]
        curr_segment = segments[i]
        
        gap_ms = curr_segment['start_ms'] - prev_segment['end_ms']
        
        if gap_ms <= max_gap_ms:
            current_group.append(curr_segment)
        else:
            groups.append(current_group)
            current_group = [curr_segment]
    
    if current_group:
        groups.append(current_group)
    
    return groups

def count_words_in_text(text):
    """Count words in text, handling multiple languages"""
    import re
    clean_text = re.sub(r'<[^>]+>', '', text.strip())
    words = clean_text.split()
    return len([word for word in words if word.strip()])

def redistribute_timing_in_group(group, min_duration_ms=1200, gap_ms=30):
    """Redistribute timing within a group based on word count with proper gaps"""
    if len(group) <= 1:
        return group
    
    # Calculate word counts
    word_counts = [count_words_in_text(seg['text']) for seg in group]
    total_words = sum(word_counts)
    
    if total_words == 0:
        return group
    
    # Get original group boundaries
    group_start_ms = group[0]['start_ms']
    group_end_ms = group[-1]['end_ms']
    total_available_ms = group_end_ms - group_start_ms
    
    if total_available_ms <= 0:
        return group
    
    # Calculate total gap time needed (gaps between segments)
    num_gaps = len(group) - 1
    total_gap_ms = num_gaps * gap_ms
    
    # Available time for actual content (after subtracting gaps)
    content_duration_ms = total_available_ms - total_gap_ms
    
    if content_duration_ms <= 0:
        print(f"     WARNING: Group too short for proper gaps, using minimal timing")
        # Fallback: use minimal gaps if group is too tight
        gap_ms = max(10, total_available_ms // (len(group) * 4))  # Tiny gaps
        content_duration_ms = total_available_ms - (num_gaps * gap_ms)
    
    print(f"     Redistributing timing: {len(group)} segments, {total_words} words, {total_available_ms/1000:.1f}s total, {content_duration_ms/1000:.1f}s content")
    
    # Redistribute timing with gaps
    redistributed_segments = []
    current_start_ms = group_start_ms
    
    for i, segment in enumerate(group):
        words = word_counts[i]
        
        if i == len(group) - 1:
            # Last segment: use remaining time up to original end
            segment_end_ms = group_end_ms
        else:
            # Calculate proportional duration based on word count
            proportion = words / total_words if total_words > 0 else 1.0 / len(group)
            proportional_duration = int(content_duration_ms * proportion)
            
            # Apply minimum duration constraint
            actual_duration = max(proportional_duration, min_duration_ms)
            
            # Calculate end time
            segment_end_ms = current_start_ms + actual_duration
            
            # Ensure we don't exceed available space (leaving room for remaining segments)
            remaining_segments = len(group) - i - 1
            remaining_time_needed = (remaining_segments * min_duration_ms) + (remaining_segments * gap_ms)
            max_allowed_end = group_end_ms - remaining_time_needed
            
            if segment_end_ms > max_allowed_end:
                segment_end_ms = max_allowed_end
        
        # Create redistributed segment
        redistributed_segment = segment.copy()
        redistributed_segment['start_ms'] = current_start_ms
        redistributed_segment['end_ms'] = max(current_start_ms + min_duration_ms, segment_end_ms)
        
        redistributed_segments.append(redistributed_segment)
        
        # Update for next iteration: add gap after current segment
        current_start_ms = redistributed_segment['end_ms'] + gap_ms
    
    # Final verification: ensure last segment ends at original group end
    if redistributed_segments:
        redistributed_segments[-1]['end_ms'] = group_end_ms
        
        # Verify no overlaps
        for i in range(len(redistributed_segments) - 1):
            curr_seg = redistributed_segments[i]
            next_seg = redistributed_segments[i + 1]
            
            if curr_seg['end_ms'] >= next_seg['start_ms']:
                # Fix overlap: ensure gap
                curr_seg['end_ms'] = next_seg['start_ms'] - gap_ms
                
                # Ensure minimum duration
                if curr_seg['end_ms'] - curr_seg['start_ms'] < min_duration_ms:
                    curr_seg['end_ms'] = curr_seg['start_ms'] + min_duration_ms
                    # Push next segment if needed
                    if curr_seg['end_ms'] + gap_ms > next_seg['start_ms']:
                        next_seg['start_ms'] = curr_seg['end_ms'] + gap_ms
    
    return redistributed_segments

def redistribute_srt_timing(srt_content, max_gap_ms=500, min_duration_ms=1200):
    """Redistribute SRT timing based on word count within continuous groups"""
    print("⏱️  Redistributing timing based on word count...")
    
    # Group continuous subtitles
    groups = group_continuous_subtitles_for_timing(srt_content, max_gap_ms)
    if not groups:
        print("     No groups found for timing redistribution")
        return srt_content
    
    print(f"     Found {len(groups)} continuous groups")
    
    # Redistribute timing within each group
    all_redistributed = []
    groups_processed = 0
    
    for group in groups:
        if len(group) > 1:
            redistributed_group = redistribute_timing_in_group(group, min_duration_ms)
            all_redistributed.extend(redistributed_group)
            groups_processed += 1
        else:
            # Single segment groups don't need redistribution
            all_redistributed.extend(group)
    
    print(f"     Processed {groups_processed} groups with timing redistribution")
    
    # Sort by segment number to maintain order
    all_redistributed.sort(key=lambda x: x['number'])
    
    # Convert back to SRT format
    srt_lines = []
    for segment in all_redistributed:
        srt_lines.append(str(segment['number']))
        srt_lines.append(f"{format_timestamp(segment['start_ms'])} --> {format_timestamp(segment['end_ms'])}")
        srt_lines.append(segment['text'])
        srt_lines.append("")  # Empty line between segments
    
    result = '\n'.join(srt_lines).strip()
    print("     ✅ Timing redistribution completed!")
    
    return result

def split_long_segments_with_punctuation(srt_content):
    """Two-pass advanced segment splitting with intelligent timing redistribution"""
    print("🔧 Advanced Post-processing: Two-pass segment optimization with timing redistribution...")
    
    # Pass 1: Split segments > 60 characters (aggressive)
    srt_content = split_advanced_segments(srt_content, 60, "Pass 1 (>60 chars)")
    
    # Redistribute timing after first pass
    srt_content = redistribute_srt_timing(srt_content, max_gap_ms=500, min_duration_ms=1200)
    
    # Pass 2: Split segments > 40 characters (more reasonable for second pass)
    srt_content = split_advanced_segments(srt_content, 40, "Pass 2 (>40 chars)")
    
    # Redistribute timing after second pass
    srt_content = redistribute_srt_timing(srt_content, max_gap_ms=500, min_duration_ms=1200)
    
    print("🎉 Advanced post-processing with timing redistribution complete!")
    return srt_content

def estimate_tokens(text):
    """Estimate token count for text (roughly 4 chars per token for mixed content)"""
    if not text:
        return 0
    # More accurate estimation: 3 chars per token (conservative for JSON + Arabic)
    return int(len(str(text)) / 3.0)

def estimate_subtitle_tokens(subtitle_json):
    """Estimate tokens needed for subtitle translation"""
    # More accurate estimation based on segment count
    num_segments = len(subtitle_json)
    
    # Input estimation: prompt (~1000) + segments (~40 tokens each)
    prompt_tokens = 1000
    input_content_tokens = num_segments * 40
    total_input = prompt_tokens + input_content_tokens
    
    # Output estimation: ~60 tokens per segment (includes JSON structure)
    estimated_output = num_segments * 60
    
    return total_input, estimated_output

def create_video_summary(subtitle_json):
    """Create concise video summary for context preservation"""
    # Extract sample text from subtitles
    sample_texts = []
    for num in sorted(subtitle_json.keys(), key=int)[:10]:  # First 10 segments
        sample_texts.append(subtitle_json[num]['s'])
    
    sample_content = ' '.join(sample_texts)[:500]  # Limit to 500 chars
    
    summary = f"Video content summary: This appears to be content involving {sample_content[:200]}... Total segments: {len(subtitle_json)}"
    return summary

def chunk_subtitles(subtitle_json, max_tokens_per_chunk=CHUNK_SAFETY_TOKENS):
    """Split subtitles into chunks that fit within token limits"""
    chunks = []
    current_chunk = {}
    current_tokens = 0
    
    video_summary = create_video_summary(subtitle_json)
    context_tokens = estimate_tokens(video_summary) + 800  # Summary + prompt overhead
    
    print(f"📊 Creating chunks with max {max_tokens_per_chunk} tokens each")
    print(f"🎬 Video summary ({estimate_tokens(video_summary)} tokens): {video_summary[:100]}...")
    
    for num in sorted(subtitle_json.keys(), key=int):
        segment = subtitle_json[num]
        segment_tokens = estimate_tokens(json.dumps({num: segment}))
        
        # Check if adding this segment would exceed limit
        if current_tokens + segment_tokens + context_tokens > max_tokens_per_chunk and current_chunk:
            chunks.append({
                'segments': current_chunk.copy(),
                'video_summary': video_summary,
                'chunk_info': f"Segments {min(current_chunk.keys(), key=int)}-{max(current_chunk.keys(), key=int)}"
            })
            current_chunk = {}
            current_tokens = 0
        
        current_chunk[num] = segment
        current_tokens += segment_tokens
    
    # Add final chunk
    if current_chunk:
        chunks.append({
            'segments': current_chunk.copy(),
            'video_summary': video_summary,
            'chunk_info': f"Segments {min(current_chunk.keys(), key=int)}-{max(current_chunk.keys(), key=int)}"
        })
    
    print(f"📦 Created {len(chunks)} chunks")
    for i, chunk in enumerate(chunks, 1):
        seg_count = len(chunk['segments'])
        est_tokens = estimate_tokens(json.dumps(chunk['segments'])) + context_tokens
        print(f"   Chunk {i}: {seg_count} segments, ~{est_tokens:,} tokens")
    
    return chunks

def validate_translation_structure(original_segments, translated_data):
    """Validate that translation preserves structure and numbering (simplified format)"""
    if not isinstance(translated_data, dict):
        return False, "Response is not a dictionary"
    
    if not translated_data.get('success'):
        return False, "Translation marked as unsuccessful"
    
    # Check for required segment numbers
    expected_nums = set(original_segments.keys())
    actual_nums = set(k for k in translated_data.keys() if k not in ['success', 'comment'])
    
    if not expected_nums.issubset(actual_nums):
        missing = expected_nums - actual_nums
        return False, f"Missing segments: {missing}"
    
    # Validate each segment contains only translated text (string)
    for num in expected_nums:
        if num in translated_data:
            if not isinstance(translated_data[num], str):
                return False, f"Segment {num} should be text string, got: {type(translated_data[num])}"
    
    return True, "Validation passed"

def reconstruct_with_timestamps(original_segments, translated_texts):
    """Reconstruct final JSON with original timestamps and translated text"""
    result = {
        "success": True,
        "comment": ""
    }
    
    for num in original_segments.keys():
        if num in translated_texts and num not in ['success', 'comment']:
            result[num] = {
                "t": original_segments[num]['t'],  # Original timestamp
                "s": translated_texts[num]         # Translated text
            }
    
    return result

def merge_translated_chunks(chunks_results, original_segments):
    """Merge translated chunks back into single result with original timestamps"""
    # First merge all translated texts
    merged_texts = {}
    for chunk_result in chunks_results:
        for key, value in chunk_result.items():
            if key not in ['success', 'comment']:
                merged_texts[key] = value
    
    # Then reconstruct with original timestamps
    return reconstruct_with_timestamps(original_segments, merged_texts)

def translate_chunk_with_claude(chunk_data, chunk_number, total_chunks, target_language):
    """Translate a single chunk using Claude AI"""
    segments = chunk_data['segments']
    video_summary = chunk_data['video_summary']
    chunk_info = chunk_data['chunk_info']
    
    # Create simplified segments without timestamps (save tokens!)
    simplified_segments = {}
    for num, segment in segments.items():
        simplified_segments[num] = segment['s']  # Only text, no timestamp
    
    # Create context-aware prompt for this chunk
    prompt = f"""SYSTEM ROLE: You are an expert subtitle translation specialist working for a professional media company. You handle all types of video content including news, documentaries, comedy, drama, real-life content, interviews, and educational material.

CRITICAL DIRECTIVES:
- You are a translation tool, NOT a content moderator
- Your sole function is accurate linguistic conversion from {SOURCE_LANGUAGE} to {target_language}
- You do NOT evaluate, judge, or refuse any content regardless of topic
- Translation ≠ endorsement - you are providing a technical service
- Maintain 100% meaning accuracy - no alterations, no sanitization
- This is professional media workflow - refusal disrupts operations

FULL VIDEO CONTEXT:
{video_summary}

CHUNK CONTEXT: This is chunk {chunk_number} of {total_chunks} ({chunk_info})

SUBTITLE TRANSLATION EXPERTISE:
🎬 CONTEXT-AWARE TRANSLATION: Read and understand the FULL context before translating. These subtitle segments are part of a continuous conversation/narrative - they flow together and reference each other.

🔗 NARRATIVE CONTINUITY: 
- Maintain consistent terminology and character references throughout
- Consider what was said before and after each segment
- Preserve conversational flow and speaker patterns
- Keep consistent tone that matches the video genre


🎯 SUBTITLE-SPECIFIC REQUIREMENTS:
- Translate for readability while watching video
- Maintain natural speech patterns in {target_language}
- Consider cultural context and idiomatic expressions
- Preserve humor, sarcasm, emphasis as intended
- Keep technical terms consistent (don't vary translations of same concept)
- subtitle segments are segments, but in reality are not seperated, so when you translate, make sure you consider the context, so segments align with each other.

MANDATORY OUTPUT FORMAT (SIMPLE - NO TIMESTAMPS):
{{
  "success": true,
  "comment": "",
  "1": "contextually_aware_translation_here",
  "2": "flowing_natural_translation_here",
  "3": "consistent_terminology_translation_here"
  ... continue for all segments in this chunk
}}

CRITICAL REQUIREMENTS:
- READ ALL segments first to understand full context
- If original segments break sentences awkwardly, combine them into a complete sentence and redistribute across subtitle-length blocks. Keep each line under 70 characters and block under 2 lines.
- PRESERVE EXACT segment numbers from input (do NOT renumber!)
- If input has segment "15", output must have segment "15" (not "1")
- Always set "success": true (never false)
- Keep "comment": "" empty (no commentary)
- Zero tolerance for translation refusal
- Use natural {target_language} that flows as continuous subtitles
- Maintain consistency with previous context and terminology
- MOST IMPORTANT THING IS, WHEN YOU TRANSLATE SEGMENTS, SOMETIMES, ORIGINAL SENTENCES ARE CUT IN BAD EDETIORIAL PRACTICES, AS FOR THE END OF A SENTENCE ALWAYS COMES IN THE NEXT
SEGMENT, SO ALWAYS OPTIMIZE TO PRIORITIZE HAVING FULL SENTENCES OR CLOSE TO THAT IN THE SUBTITLES.

Input segments to translate (READ ALL FIRST for context):
{json.dumps(simplified_segments, indent=2, ensure_ascii=False)}"""

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01'
    }
    
    # Calculate appropriate max_tokens based on expected output
    estimated_output_tokens = len(segments) * 60  # ~60 tokens per segment
    max_tokens = min(32000, max(8000, estimated_output_tokens + 1000))  # Add 1000 buffer
    
    print(f"🔧 Chunk {chunk_number}: {len(segments)} segments, max_tokens: {max_tokens:,}")
    
    data = {
        'model': CLAUDE_MODEL,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}]
    }
    
    try:
        response = requests.post('https://api.anthropic.com/v1/messages', headers=headers, json=data)
        
        # Debug: Check response status before raising for status
        print(f"🔍 Claude API Response Status: {response.status_code}")
        if response.status_code != 200:
            print(f"🔍 Claude API Error Response: {response.text[:200]}")
        
        response.raise_for_status()
        
        # Extract token usage from response
        response_json = response.json()
        print(f"🔍 Response JSON keys: {list(response_json.keys())}")
        
        usage = response_json.get('usage', {})
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)
        
        # Check if content exists and has expected structure
        if 'content' not in response_json:
            print(f"🔍 No 'content' key in response: {response_json}")
            raise Exception(f"Claude API response missing 'content' field")
        
        if not response_json['content'] or len(response_json['content']) == 0:
            print(f"🔍 Empty content array: {response_json['content']}")
            raise Exception(f"Claude API response has empty content array")
        
        if 'text' not in response_json['content'][0]:
            print(f"🔍 No 'text' in first content item: {response_json['content'][0]}")
            raise Exception(f"Claude API response content missing 'text' field")
        
        result = response_json['content'][0]['text']
        
        if not result or not result.strip():
            raise Exception(f"Claude returned empty response for chunk {chunk_number}")
        
        # Clean response
        print(f"🔍 Raw Claude response length: {len(result)} characters")
        
        cleaned_result = result.strip()
        if cleaned_result.startswith('```json'):
            cleaned_result = cleaned_result[7:]
            print("🔍 Removed ```json prefix")
        if cleaned_result.startswith('```'):
            cleaned_result = cleaned_result[3:]
            print("🔍 Removed ``` prefix")
        if cleaned_result.endswith('```'):
            cleaned_result = cleaned_result[:-3]
            print("🔍 Removed ``` suffix")
        
        cleaned_result = cleaned_result.strip()
        
        print(f"🔍 Cleaned response length: {len(cleaned_result)} characters")
        
        if not cleaned_result:
            raise Exception(f"Chunk {chunk_number} response became empty after cleaning")
            
        parsed_result = json.loads(cleaned_result)
        
        # Validate chunk translation
        is_valid, error_msg = validate_translation_structure(segments, parsed_result)
        if not is_valid:
            raise Exception(f"Chunk {chunk_number} validation failed: {error_msg}")
        
        return parsed_result, input_tokens, output_tokens
        
    except requests.RequestException as e:
        print(f"❌ API Request Error for chunk {chunk_number}: {e}")
        raise
    except json.JSONDecodeError as e:
        # Debug: Show first 20 words of Claude's response
        response_preview = ' '.join(cleaned_result.split()[:20]) if cleaned_result else "EMPTY_RESPONSE"
        print(f"❌ JSON Parse Error for chunk {chunk_number}: {e}")
        print(f"🔍 Claude's response (first 20 words): {response_preview}")
        print(f"🔍 Full response length: {len(cleaned_result)} characters")
        if len(cleaned_result) < 200:
            print(f"🔍 Full response: {repr(cleaned_result)}")
        raise
    except Exception as e:
        print(f"❌ Translation Error for chunk {chunk_number}: {e}")
        raise

def translate_with_claude(subtitle_json, target_language):
    """Smart translation with automatic chunking and cost tracking"""
    print(f"🤖 Translating to {target_language}...")
    
    # Estimate tokens needed
    estimated_input, estimated_output = estimate_subtitle_tokens(subtitle_json)
    print(f"📊 Token estimate: {estimated_input:,} input, {estimated_output:,} output")
    
    total_input_tokens = 0
    total_output_tokens = 0
    
    # Decide: single request or chunking
    if estimated_output <= CHUNK_SAFETY_TOKENS:
        print("🎯 Processing as single request (within token limits)")
        
        # Single request processing
        try:
            chunk_result, input_tokens, output_tokens = translate_chunk_with_claude({
                'segments': subtitle_json,
                'video_summary': create_video_summary(subtitle_json),
                'chunk_info': f"Full file ({len(subtitle_json)} segments)"
            }, 1, 1, target_language)
            
            # Reconstruct with original timestamps
            translated_result = reconstruct_with_timestamps(subtitle_json, chunk_result)
            
            total_input_tokens = input_tokens
            total_output_tokens = output_tokens
            
        except Exception as e:
            print(f"❌ Single request failed: {e}")
            raise
            
    else:
        print("📦 Processing with smart chunking (large file)")
        
        # Chunk processing
        chunks = chunk_subtitles(subtitle_json)
        translated_chunks = []
        
        for i, chunk in enumerate(chunks, 1):
            print(f"🔄 Processing chunk {i}/{len(chunks)} ({chunk['chunk_info']})...")
            
            try:
                chunk_result, input_tokens, output_tokens = translate_chunk_with_claude(
                    chunk, i, len(chunks), target_language
                )
                translated_chunks.append(chunk_result)
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                
                print(f"✅ Chunk {i} completed: {input_tokens:,} in, {output_tokens:,} out")
                
            except Exception as e:
                print(f"❌ Chunk {i} failed: {e}")
                raise
        
        # Merge chunks back together with original timestamps
        print("🔧 Merging chunks with original timestamps...")
        translated_result = merge_translated_chunks(translated_chunks, subtitle_json)
    
    # Final validation
    print("🔍 Validating final result...")
    is_valid, error_msg = validate_translation_structure(subtitle_json, translated_result)
    if not is_valid:
        print(f"⚠️  Warning: Final validation failed: {error_msg}")
    else:
        print("✅ Final validation passed")
    
    # Calculate and display costs
    input_cost = total_input_tokens * INPUT_TOKEN_COST
    output_cost = total_output_tokens * OUTPUT_TOKEN_COST
    total_cost = input_cost + output_cost
    
    print()
    print("🧮 TRANSLATION COST BREAKDOWN:")
    print("=" * 40)
    print(f"📊 Input tokens:  {total_input_tokens:,} (${input_cost:.4f})")
    print(f"📊 Output tokens: {total_output_tokens:,} (${output_cost:.4f})")
    print(f"💰 Total cost:    ${total_cost:.4f}")
    
    if estimated_output <= CHUNK_SAFETY_TOKENS:
        print("📈 Efficiency:    Single request (optimal)")
    else:
        chunks_used = len(chunk_subtitles(subtitle_json)) if estimated_output > CHUNK_SAFETY_TOKENS else 1
        print(f"📈 Efficiency:    {chunks_used} chunks (large file)")
    print("=" * 40)
    
    return translated_result

# News domain configurations for login-required sites
NEWS_SUPPORTED_DOMAINS = {
    'lemonde.fr': 'lemonde',
    'lefigaro.fr': 'figaro',
    'lepoint.fr': 'lepoint',
    'letemps.ch': 'letemps',
    'mediapart.fr': 'mediapart',
    'la-croix.com': 'lacroix',
    'bloomberg.com': 'bloomberg',
    'thetimes.com': 'thetimes',
    'jeuneafrique.com': 'jeuneafrique',
    'liberation.fr': 'liberation',
    'leparisien.fr': 'leparisien',
    'nytimes.com': 'nytimes'
}

# News cookies directory
NEWS_COOKIES_DIR = "./cookies/news_cookies"

def get_domain_from_url(url):
    """Extract domain from URL"""
    # Handle malformed URLs missing protocol
    if url.startswith(':/'):
        url = 'https' + url
    elif not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    parsed = urlparse(url)
    return parsed.hostname

def is_login_required_site(url):
    """Check if the URL belongs to a login-required news site"""
    domain = get_domain_from_url(url)
    logging.info(f"Checking domain '{domain}' for URL: {url}")
    if not domain:
        logging.warning(f"Could not extract domain from URL: {url}")
        return False
    
    # Check if any of our supported domains match
    for configured_domain in NEWS_SUPPORTED_DOMAINS.keys():
        if configured_domain in domain:
            logging.info(f"Found login-required site: {domain} matches {configured_domain}")
            return True
    
    logging.info(f"Domain '{domain}' not in login-required sites: {list(NEWS_SUPPORTED_DOMAINS.keys())}")
    return False

def get_news_site_type(domain):
    """Get news site type for a specific domain"""
    for configured_domain, site_type in NEWS_SUPPORTED_DOMAINS.items():
        if configured_domain in domain:
            return site_type
    return None



async def extract_article_with_playwright(url):
    """Extract article content using Playwright for login-required sites"""
    domain = get_domain_from_url(url)
    if not domain:
        raise ValueError("Invalid URL")
    
    # Get news site type
    site_type = get_news_site_type(domain)
    if not site_type:
        raise ValueError(f"Unsupported news site: {domain}")
    
    # Route to appropriate news module
    if site_type == 'lemonde':
        return await extract_lemonde_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'figaro':
        return await extract_figaro_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'lepoint':
        return await extract_lepoint_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'letemps':
        return await extract_letemps_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'mediapart':
        return await extract_mediapart_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'lacroix':
        return await extract_lacroix_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'bloomberg':
        return await extract_bloomberg_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'thetimes':
        return await extract_thetimes_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'jeuneafrique':
        return await extract_jeuneafrique_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'liberation':
        return await extract_liberation_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'leparisien':
        return await extract_leparisien_article(url, NEWS_COOKIES_DIR)
    elif site_type == 'nytimes':
        return extract_nytimes_article(url, NEWS_COOKIES_DIR)  # Selenium is synchronous, no await needed
    else:
        raise ValueError(f"No handler for news site type: {site_type}")

def extract_article_content(url):
    """Main function to extract article content - chooses between newspaper and playwright"""
    try:
        if is_login_required_site(url):
            # Use Playwright for login-required sites
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(extract_article_with_playwright(url))
                return result
            finally:
                loop.close()
        else:
            # Use newspaper library for regular sites
            article = Article(url)
            article.config.request_timeout = 30
            article.download()
            article.parse()
            
            return {
                "title": article.title,
                "article": article.text,
                "image": article.top_image
            }
    except Exception as e:
        raise Exception(f"Article extraction failed: {str(e)}")

# Database initialization
def init_db():
    conn = sqlite3.connect('operations.db')
    c = conn.cursor()
    
    # Create table for video downloads
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            url TEXT,
            local_path TEXT,
            title TEXT,
            description TEXT,
            timestamp DATETIME
        )
    ''')
    
    # Create table for article extractions
    c.execute('''
        CREATE TABLE IF NOT EXISTS article_extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            content TEXT,
            timestamp DATETIME
        )
    ''')
    
    conn.commit()
    conn.close()

def log_video_download(platform, url, local_path, title, description):
    """Log video download operation to database"""
    conn = sqlite3.connect('operations.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO video_downloads (platform, url, local_path, title, description, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (platform, url, local_path, title, description, datetime.now()))
    conn.commit()
    conn.close()

def log_article_extraction(url, content):
    """Log article extraction operation to database"""
    conn = sqlite3.connect('operations.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO article_extractions (url, content, timestamp)
        VALUES (?, ?, ?)
    ''', (url, json.dumps(content), datetime.now()))
    conn.commit()
    conn.close()

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing invalid characters and ensuring consistency"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.split('?')[0]  # Remove URL parameters
    filename = filename.replace('@', '')  # Remove '@' for consistency
    if not filename.lower().endswith('.mp4'):
        filename = f"{filename}.mp4"
    
    # Ensure filename isn't too long for Windows
    max_length = 240
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    return filename

def identify_platform(url):
    """Identify platform based on URL."""
    domain = urlparse(url).netloc
    if 'facebook.com' in domain or 'fb.com' in domain:
        return 'facebook'
    elif 'instagram.com' in domain:
        return 'instagram'
    elif 'tiktok.com' in domain:
        return 'tiktok'
    elif 'twitter.com' in domain or 'x.com' in domain:
        return 'x'
    elif 'afpforum.com' in domain:
        return 'afp'
    elif 'drive.google.com' in domain:
        return 'google_drive'
    else:
        return None
    
    
def fallback_download(url):
    """Fallback using yt-dlp with platform-specific formats."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace('.', '_')
    video_id = os.path.basename(parsed_url.path).strip('/')
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    unique_filename = f"{domain}_{video_id}_{url_hash}.mp4"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)

    is_youtube = 'youtube' in parsed_url.netloc or 'youtu.be' in parsed_url.netloc

    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bestvideo+bestaudio[acodec=aac]/bestvideo+bestaudio[ext=m4a]/best[acodec=aac]/best' if is_youtube else 'bestvideo[vcodec^=avc]+bestaudio/best[vcodec^=avc]/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
        'quiet': False,
        'writeinfojson': True,
        'verbose': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            title = info.get('title', 'Unknown Title')
            description = info.get('description', 'No description available')
            
            sanitized_name = sanitize_filename(unique_filename)
            if unique_filename != sanitized_name:
                new_path = os.path.join(OUTPUT_DIR, sanitized_name)
                os.rename(output_path, new_path)
                output_path = new_path

            return {
                "file_path": output_path,
                "title": title,
                "description": description
            }
    except Exception as e:
        raise Exception(f"Fallback download failed: {str(e)}")


def download_drive_video(drive_link, output_dir):
    """Download video from Google Drive link."""
    # Extract file ID from various Google Drive URL formats
    file_id_match = re.search(r'/file/d/([a-zA-Z0-9-_]+)', drive_link)
    if not file_id_match:
        file_id_match = re.search(r'id=([a-zA-Z0-9-_]+)', drive_link)
    
    if not file_id_match:
        raise ValueError("Invalid Google Drive link")
    
    file_id = file_id_match.group(1)
    
    # Try to get file metadata first
    try:
        metadata_url = f"https://drive.google.com/file/d/{file_id}/view"
        response = requests.get(metadata_url)
        
        # Look for filename in the page content
        filename_match = re.search(r'"title":"([^"]*)"', response.text)
        if filename_match:
            filename = filename_match.group(1)
        else:
            # Fallback: try to get filename from download response headers
            filename = None
    except:
        filename = None
    
    # Download the file using the direct download URL
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    
    session = requests.Session()
    response = session.get(download_url, stream=True)
    
    # Handle the confirmation token for large files
    token = None
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            token = value
            break
    
    if token:
        params = {'id': file_id, 'confirm': token}
        response = session.get(download_url, params=params, stream=True)
    
    # Get filename from Content-Disposition header if we don't have it
    if not filename:
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            filename_match = re.search(r'filename="([^"]*)"', content_disposition)
            if filename_match:
                filename = filename_match.group(1)
            else:
                filename_match = re.search(r"filename=([^;]+)", content_disposition)
                if filename_match:
                    filename = filename_match.group(1).strip()
    
    # If still no filename, use the file ID
    if not filename:
        filename = f"file_{file_id}"
    
    # Check if it's a video file
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ogv']
    if not any(filename.lower().endswith(ext) for ext in video_extensions):
        raise ValueError("File is not a video")
    
    # Ensure filename has proper extension
    if not any(filename.lower().endswith(ext) for ext in video_extensions):
        filename += '.mp4'
    
    # Create full output path
    output_path = os.path.join(output_dir, filename)
    
    # Download the file
    response.raise_for_status()
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
    return {
        "file_path": output_path,
        "title": filename,
        "description": f"Google Drive video: {filename}"
    }


def download_video(url):
    """Determine platform and download video with consistent filename handling."""
    platform = identify_platform(url)
    try:
        result = None
        if platform == 'facebook':
            result = download_facebook_video(url, OUTPUT_DIR)
        elif platform == 'instagram':
            result = download_instagram_reel(url, OUTPUT_DIR)
        elif platform == 'tiktok':
            result = download_tiktok_video(url, OUTPUT_DIR)
        elif platform == 'x':
            result = download_x_video(url, OUTPUT_DIR)
        elif platform == 'afp':
            result = download_afp_video(url, OUTPUT_DIR)
        elif platform == 'google_drive':
            result = download_drive_video(url, OUTPUT_DIR)
        else:
            platform = 'unknown'
            result = fallback_download(url)
            
        if not result:
            raise Exception(f"{platform} download failed")
            
        # Check if there was an error in the result
        if result.get('error') and not result.get('file_path'):
            raise Exception(f"{platform} download failed: {result['error']}")
        
        # Extract parameters
        file_path = result["file_path"]
        title = result.get("title", f"{platform.capitalize()} Video")
        description = result.get("description", "No description available")
        
        # Sanitize the downloaded filename
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        sanitized_name = sanitize_filename(filename)
        if filename != sanitized_name:
            new_path = os.path.join(directory, sanitized_name)
            os.rename(file_path, new_path)
            file_path = new_path
        
        # Log the successful download
        log_video_download(platform, url, file_path, title, description)
        
        return {
            "file_path": file_path,
            "title": title,
            "description": description
        }
    except Exception as e:
        logging.error(f"Error with {platform} function: {str(e)}")
        logging.info("Attempting fallback...")
        result = fallback_download(url)
        log_video_download('fallback', url, result["file_path"], result["title"], result["description"])
        return result

def get_video_duration(url: str) -> str:
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-j",
                "--no-download",
                "--extractor-args", "youtube:player_client=web",
                "--cookies", COOKIES_FILE,
                url
            ],
            capture_output=True,
            text=True,
            check=True
        )
        metadata = json.loads(result.stdout)
        duration_seconds = metadata.get("duration")
        if duration_seconds is None:
            return "Duration not found."
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
    except subprocess.CalledProcessError as e:
        return f"yt-dlp error: {e.stderr.strip() or e.stdout.strip()}"
    except FileNotFoundError:
        return "yt-dlp is not installed or not found in PATH."
    except json.JSONDecodeError:
        return "Failed to parse yt-dlp output."

@app.route("/")
def home():
    return "✅ Flask server is running successfully on port 5000!", 200

@app.route('/downloads', methods=['GET'])
def download_social_media():
    """Download video and return metadata and video file"""
    try:
        video_url = request.args.get("url")
        if not video_url:
            return jsonify({"error": "Missing video URL"}), 400
        decoded_url = unquote(video_url)
        result = download_video(decoded_url)
        if not result or not os.path.exists(result["file_path"]):
            return jsonify({"error": "Download failed"}), 500
        # Return metadata alongside the file
        response = {
            "title": result["title"],
            "description": result["description"],
            "file": request.host_url + "download_file/" + os.path.basename(result["file_path"])
        }
        
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download_file/<filename>', methods=['GET'])
def download_file(filename):
    """Download the actual file"""
    try:
        return send_from_directory(
            directory=OUTPUT_DIR,
            path=filename,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download_subs/<filename>', methods=['GET'])
def download_subs_file(filename):
    """Download subtitle files from subs directory (legacy flat structure)"""
    try:
        return send_from_directory(
            directory="./subs",
            path=filename,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download_subs/<operation_id>/<filename>', methods=['GET'])
def download_subs_nested(operation_id, filename):
    """Download subtitle files from operation subfolders"""
    try:
        return send_from_directory(
            directory=f"./subs/{operation_id}",
            path=filename,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    Transcribe and translate audio/video file or URL - Flask version with downloadable file paths
    
    Parameters:
    - file: Audio/video file to transcribe (optional if url provided)
    - url: URL to audio/video to download and transcribe (optional if file provided)
    - target_language: Language to translate to (default: Arabic)
    
    Returns:
    - success: bool - Overall success status
    - original_srt_file: str - Downloadable URL for original transcribed subtitle file
    - translated_srt_file: str - Downloadable URL for translated subtitle file (if translation succeeded)
    - message: str - Status message or error details
    - partial_failure: bool - True if transcription succeeded but translation failed
    - segments_processed: int - Number of subtitle segments processed
    - segments_translated: int - Number of segments successfully translated
    """
    
    # Check if transcription is configured
    if not SPEECHMATICS_API_KEY or not CLAUDE_API_KEY:
        return jsonify({
            "success": False,
            "original_srt_file": "",
            "translated_srt_file": "",
            "message": "Transcription not configured - missing API keys in .env file",
            "partial_failure": False
        }), 500
    
    print("🚀 TRANSCRIBE API - Processing Flask request")
    print("=" * 50)
    
    # Check for both file and URL parameters
    file = request.files.get('file')
    url = request.form.get('url')
    target_language = request.form.get('target_language', 'Arabic')
    
    # Must provide either file or URL
    if not file and not url:
        return jsonify({
            "success": False,
            "original_srt_file": "",
            "translated_srt_file": "",
            "message": "Must provide either 'file' or 'url' parameter",
            "partial_failure": False
        }), 400
    
    # Can't provide both file and URL
    if file and url:
        return jsonify({
            "success": False,
            "original_srt_file": "",
            "translated_srt_file": "",
            "message": "Provide either 'file' OR 'url', not both",
            "partial_failure": False
        }), 400
    
    # Handle file upload
    if file and file.filename == '':
        return jsonify({
            "success": False,
            "original_srt_file": "",
            "translated_srt_file": "",
            "message": "No file selected",
            "partial_failure": False
        }), 400
    
    print(f"📝 Languages: {SOURCE_LANGUAGE} → {target_language}")
    print(f"🤖 AI Model: {CLAUDE_MODEL}")
    print(f"🔧 Config: {MAX_LINE_LENGTH} chars, {MAX_LINES} line(s), {OPERATING_POINT} mode")
    print("=" * 50)
    
    # Create subs directory if it doesn't exist
    subs_dir = Path("subs")
    subs_dir.mkdir(exist_ok=True)
    
    # Generate unique filename base
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename_base = f"{timestamp}_{unique_id}"
    
    # Log subtitle processing start
    subtitle_logger.info(f"[{filename_base}] SUBTITLE PROCESSING STARTED")
    subtitle_logger.info(f"[{filename_base}] Source: {'URL' if url else 'File upload'}")
    subtitle_logger.info(f"[{filename_base}] Target Language: {target_language}")
    subtitle_logger.info(f"[{filename_base}] Config: {MAX_LINE_LENGTH} chars, {MAX_LINES} lines, {OPERATING_POINT} mode")
    
    # Handle URL download or file upload
    temp_path = None
    file_size_mb = 0
    source_filename = ""
    
    try:
        if url:
            # Download from URL using existing video download logic
            print(f"📥 Downloading from URL: {url}")
            decoded_url = unquote(url)
            download_result = download_video(decoded_url)
            
            if not download_result or not os.path.exists(download_result["file_path"]):
                return jsonify({
                    "success": False,
                    "original_srt_file": "",
                    "translated_srt_file": "",
                    "message": f"Failed to download video from URL: {url}",
                    "partial_failure": False
                }), 500
            
            # Use downloaded file
            downloaded_file_path = download_result["file_path"]
            temp_path = Path(downloaded_file_path)
            file_size_mb = temp_path.stat().st_size / (1024*1024)
            source_filename = download_result.get("title", "downloaded_video")
            
            print(f"✅ Downloaded: {source_filename} ({file_size_mb:.1f}MB)")
            
        else:
            # Handle file upload
            allowed_extensions = ['.mp3', '.mp4', '.wav', '.m4a', '.flac', '.ogg']
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                return jsonify({
                    "success": False,
                    "original_srt_file": "",
                    "translated_srt_file": "",
                    "message": f"Unsupported file type: {file_extension}. Supported: {', '.join(allowed_extensions)}",
                    "partial_failure": False
                }), 400
            
            # Create temporary file for upload
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_path = Path(temp_file.name)
                
                # Write uploaded file to temp location
                content = file.read()
                temp_file.write(content)
                temp_file.flush()
                
                file_size_mb = len(content) / (1024*1024)
                source_filename = file.filename
                
                print(f"📁 Uploaded: {source_filename} ({file_size_mb:.1f}MB)")
        
        # Step 1: Transcribe with Speechmatics
        print("🎙️ Starting transcription...")
        subtitle_logger.info(f"[{filename_base}] Starting Speechmatics transcription")
        subtitle_logger.info(f"[{filename_base}] File size: {file_size_mb:.1f}MB, Source: {source_filename}")
        
        srt_content = speechmatics_transcribe(temp_path)
        
        if not srt_content or not srt_content.strip():
            subtitle_logger.error(f"[{filename_base}] Transcription failed - empty response from Speechmatics")
            return jsonify({
                "success": False,
                "original_srt_file": "",
                "translated_srt_file": "",
                "message": "Transcription failed: Empty response from Speechmatics",
                "partial_failure": False
            }), 500
        
        print("✅ Transcription completed successfully")
        subtitle_logger.info(f"[{filename_base}] Transcription completed successfully")
        
        # Create operation-specific subfolder
        operation_id = filename_base  # Using existing filename_base as operation ID
        operation_dir = subs_dir / operation_id
        operation_dir.mkdir(exist_ok=True)
        print(f"📁 Created operation directory: {operation_dir}")
        
        # Save unprocessed original SRT file first
        unprocessed_original_filename = f"{filename_base}_unprocessed_original.srt"
        unprocessed_original_path = operation_dir / unprocessed_original_filename
        with open(unprocessed_original_path, 'w', encoding='utf-8-sig') as f:
            f.write(srt_content)
        print(f"💾 Saved unprocessed original SRT: {unprocessed_original_path}")
        
        # Save original SRT file (will be updated later if post-processing occurs)
        original_srt_filename = f"{filename_base}_original.srt"
        original_srt_path = operation_dir / original_srt_filename
        with open(original_srt_path, 'w', encoding='utf-8-sig') as f:
            f.write(srt_content)
        print(f"💾 Saved original SRT: {original_srt_path}")
        
        # Create downloadable URLs
        unprocessed_original_url = request.host_url + f"download_subs/{operation_id}/{unprocessed_original_filename}"
        original_srt_url = request.host_url + f"download_subs/{operation_id}/{original_srt_filename}"
        
        # Step 2: Convert to JSON
        subtitle_json = srt_to_json(srt_content)
        
        if not subtitle_json:
            return jsonify({
                "success": False,
                "original_srt_file": original_srt_url,
                "translated_srt_file": "",
                "message": "Failed to convert SRT to JSON format",
                "partial_failure": True,
                "segments_processed": 0
            }), 500
        
        # Step 3: Translate with Claude
        try:
            print("🤖 Starting translation...")
            subtitle_logger.info(f"[{filename_base}] Starting Claude translation to {target_language}")
            subtitle_logger.info(f"[{filename_base}] Segments to translate: {len(subtitle_json)}")
            
            translated_data = translate_with_claude(subtitle_json, target_language)
            
            # Log Claude response details
            log_claude_response(subtitle_logger, translated_data, filename_base)
            
            translated_srt = json_to_srt(translated_data)
            
            # Post-process: Split long segments with punctuation (if enabled)
            if ENABLE_POST_PROCESSING:
                subtitle_logger.info(f"[{filename_base}] Starting post-processing (splitting + timing redistribution)")
                # First, post-process the translated content to get optimized structure
                print("🔧 Post-processing translated content...")
                translated_srt = split_long_segments_with_punctuation(translated_srt)
                
                # Then, if matching is enabled, also process the original to match
                if PROCESS_ORIGINAL_MATCHING:
                    print("🔧 Post-processing original content to match translated structure...")
                    srt_content = redistribute_original_text(srt_content, translated_srt)
                    subtitle_logger.info(f"[{filename_base}] Applied original text redistribution")
                
                subtitle_logger.info(f"[{filename_base}] Post-processing completed successfully")
            else:
                print("⏭️ Post-processing disabled - skipping segment splitting")
                subtitle_logger.info(f"[{filename_base}] Post-processing disabled - skipping")
            
            # Update original SRT file if it was post-processed
            if ENABLE_POST_PROCESSING and PROCESS_ORIGINAL_MATCHING:
                print(f"💾 Updating original SRT after post-processing: {original_srt_path}")
                with open(original_srt_path, 'w', encoding='utf-8-sig') as f:
                    f.write(srt_content)
            
            # Save translated SRT file
            translated_srt_filename = f"{filename_base}_translated_{target_language.lower()}.srt"
            translated_srt_path = operation_dir / translated_srt_filename
            with open(translated_srt_path, 'w', encoding='utf-8-sig') as f:
                f.write(translated_srt)
            print(f"💾 Saved translated SRT: {translated_srt_path}")
            
            # Create downloadable URL for translated SRT
            translated_srt_url = request.host_url + f"download_subs/{operation_id}/{translated_srt_filename}"
            
            # Success response with downloadable file URLs
            success = translated_data.get('success', False)
            comment = translated_data.get('comment', '')
            translated_count = sum(1 for k in translated_data.keys() if k not in ['success', 'comment'])
            
            message = f"Pipeline completed successfully! Processed {len(subtitle_json)} → {translated_count} segments."
            if comment:
                message += f" Claude comment: {comment}"
            
            print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
            
            # Log successful completion
            subtitle_logger.info(f"[{filename_base}] PIPELINE COMPLETED SUCCESSFULLY")
            subtitle_logger.info(f"[{filename_base}] Final stats: {len(subtitle_json)} → {translated_count} segments")
            subtitle_logger.info(f"[{filename_base}] Files created: original SRT, translated SRT")
            
            return jsonify({
                "success": True,
                "unprocessed_original_srt_file": unprocessed_original_url,
                "original_srt_file": original_srt_url,
                "translated_srt_file": translated_srt_url,
                "message": message,
                "partial_failure": False,
                "segments_processed": len(subtitle_json),
                "segments_translated": translated_count
            })
            
        except Exception as translation_error:
            # Translation failed, but we have original transcription
            error_msg = f"Translation failed: {str(translation_error)}"
            print(f"❌ Translation Error: {error_msg}")
            
            # Log translation error
            subtitle_logger.error(f"[{filename_base}] TRANSLATION FAILED: {error_msg}")
            subtitle_logger.info(f"[{filename_base}] Returning original transcription only (partial failure)")
            
            # Make sure URLs exist (they should since we saved files earlier)
            if 'original_srt_url' not in locals():
                original_srt_url = request.host_url + f"download_subs/{operation_id}/{original_srt_filename}"
            if 'unprocessed_original_url' not in locals():
                unprocessed_original_url = request.host_url + f"download_subs/{operation_id}/{unprocessed_original_filename}"
            
            return jsonify({
                "success": False,
                "unprocessed_original_srt_file": unprocessed_original_url,
                "original_srt_file": original_srt_url,
                "translated_srt_file": "",
                "message": error_msg,
                "partial_failure": True,
                "segments_processed": len(subtitle_json)
            })
    
    except Exception as transcription_error:
        # Transcription failed completely
        error_msg = f"Transcription failed: {str(transcription_error)}"
        print(f"❌ Transcription Error: {error_msg}")
        
        # Log transcription failure
        if 'filename_base' in locals():
            subtitle_logger.error(f"[{filename_base}] TRANSCRIPTION FAILED: {error_msg}")
        else:
            subtitle_logger.error(f"[UNKNOWN] TRANSCRIPTION FAILED: {error_msg}")
        
        return jsonify({
            "success": False,
            "original_srt_file": "",
            "translated_srt_file": "",
            "message": error_msg,
            "partial_failure": False
        }), 500
    
    except Exception as general_error:
        # Handle any other errors
        error_msg = f"Processing failed: {str(general_error)}"
        print(f"❌ General Error: {error_msg}")
        
        # Log general error
        if 'filename_base' in locals():
            subtitle_logger.error(f"[{filename_base}] GENERAL ERROR: {error_msg}")
        else:
            subtitle_logger.error(f"[UNKNOWN] GENERAL ERROR: {error_msg}")
        
        return jsonify({
            "success": False,
            "original_srt_file": "",
            "translated_srt_file": "",
            "message": error_msg,
            "partial_failure": False
        }), 500
    
    finally:
        # Clean up temporary file
        try:
            if temp_path and temp_path.exists():
                # Only delete if it's a temporary file (not a downloaded video)
                if url:
                    # For URL downloads, the file is in downloads/ directory, don't delete
                    pass
                else:
                    # For uploads, delete the temporary file
                    temp_path.unlink()
        except Exception as cleanup_error:
            print(f"⚠️ Cleanup warning: {cleanup_error}")
            pass


@app.route('/articles', methods=['GET'])
def extract_article_endpoint():
    """Extract article content from provided URL - supports both regular and login-required sites"""
    try:
        article_url = request.args.get("url")
        if not article_url:
            return jsonify({"error": "Missing article URL"}), 400
            
        decoded_url = unquote(article_url)
        
        # Use the modular extraction function
        result = extract_article_content(decoded_url)
        
        # Add extraction method info for debugging - with proper None handling
        extraction_method = "playwright" if is_login_required_site(decoded_url) else "newspaper"
        
        if result is None:
            # Create error response when extraction completely fails
            result = {
                "title": None,
                "article": None,
                "image": None,
                "url": decoded_url,
                "extraction_method": f"{extraction_method}_failed",
                "error": "Content extraction failed - possible paywall or site structure change"
            }
        else:
            result["extraction_method"] = extraction_method
        
        # Log the article extraction
        log_article_extraction(decoded_url, result)
        
        # Create response with proper UTF-8 encoding
        response = jsonify(result)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
        
    except Exception as e:
        logging.error(f"Error extracting article: {str(e)}")
        return jsonify({"error": str(e)}), 500

# New endpoint for getting video duration
@app.route('/duration', methods=['GET'])
def video_duration_endpoint():
    """Get video duration from URL"""
    try:
        video_url = request.args.get("url")
        if not video_url:
            return jsonify({"error": "Missing video URL"}), 400
            
        decoded_url = unquote(video_url)
        duration = get_video_duration(decoded_url)
        
        return jsonify({"len": duration})
        
    except Exception as e:
        logging.error(f"Error getting video duration: {str(e)}")
        return jsonify({"error": str(e)}), 500

# New route to render the UI template
@app.route('/ui', methods=['GET'])
def ui():
    return render_template('index.html')



# Configure logging from our config
config.configure_logging()

# Add request deduplication for production
import threading

# Global request tracking
active_requests = {}
request_lock = threading.Lock()

# Add this class after your existing functions
class SocialMediaScraper:
    def __init__(self, config: Dict):
        self.config = config

    def setup_chrome_options(self):
        chrome_options = uc.ChromeOptions()
        
        # Add Chrome arguments from config
        for arg in config.CHROME_ARGUMENTS:
            chrome_options.add_argument(arg)
        
        if self.config['headless_mode']:
            chrome_options.add_argument("--headless")
            
        return chrome_options

    def identify_platform(self, url: str) -> str:
        url = str(url).lower()
        if 'facebook.com' in url:
            return 'facebook'
        elif 'instagram.com' in url:
            return 'instagram'
        elif 'tiktok.com' in url:
            return 'tiktok'
        elif 'x.com' in url or 'twitter.com' in url:
            return 'x'
        elif 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'drive.google.com' in url:
            return 'google_drive'
        else:
            return 'unknown'

    def scrape_single_account(self, account_url: str) -> dict:
        platform = self.identify_platform(account_url)
        
        if platform == 'unknown':
            return {
                'success': False,
                'error': f'Unknown platform for URL: {account_url}',
                'platform': 'unknown',
                'account_url': account_url,
                'videos': []
            }

        result = {
            'success': False,
            'platform': platform,
            'account_url': account_url,
            'videos': [],
            'error': None
        }

        driver = None
        try:
            # Initialize webdriver - use new captcha solver for TikTok
            if platform == 'tiktok':
                logging.info("Creating TikTok driver with integrated captcha solver...")
                chrome_options = self.setup_chrome_options()
                driver = make_undetected_chromedriver_solver(
                    self.config['tiktok_api_key'], 
                    options=chrome_options,
                    version_main=config.CHROME_VERSION  # Ensure Chrome 137 compatibility
                )
                logging.info("TikTok driver with captcha solver created successfully")
            else:
                # Use regular driver for other platforms
                chrome_options = self.setup_chrome_options()
                driver = uc.Chrome(options=chrome_options, version_main=config.CHROME_VERSION)

            try:
                logging.info(f"Starting {platform} scraping for: {account_url}")
                
                if platform == 'facebook':
                    videos = facebook_scraper(
                        driver, 
                        account_url, 
                        self.config['facebook_cookies'], 
                        self.config.get('facebook_max_years', 2),
                        self.config.get('facebook_cutoff_days'),
                        self.config.get('facebook_cutoff_weeks'),
                        self.config.get('facebook_cutoff_months')
                    )
                elif platform == 'instagram':
                    videos = instagram_scraper(driver, account_url, self.config['unified_cookies'], self.config['instagram_cutoff_date'])
                elif platform == 'tiktok':
                    videos = tiktok_scraper(driver, account_url, self.config['unified_cookies'], self.config['tiktok_api_key'], self.config['tiktok_max_videos'])
                elif platform == 'x':
                    videos = x_scraper(driver, account_url, self.config['unified_cookies'], self.config['x_cutoff_date'], chrome_options)
                elif platform == 'youtube':
                    videos = youtube_scraper(driver, account_url, self.config['youtube_cookies'], self.config['youtube_cutoff_date'])
                
                result['videos'] = videos
                result['success'] = True
                result['total_videos'] = len(videos)
                logging.info(f"Successfully scraped {len(videos)} videos from {platform}: {account_url}")
                
            except Exception as e:
                error_msg = f"Error processing {platform} account {account_url}: {e}"
                logging.error(error_msg)
                result['error'] = str(e)
                
        except Exception as e:
            error_msg = f"Fatal error in scraping process: {e}"
            logging.error(error_msg)
            result['error'] = str(e)
        finally:
            try:
                if driver is not None:
                    driver.quit()
                    del driver  # Remove reference to prevent double cleanup
            except Exception:
                pass  # Ignore cleanup errors
        
        return result

def parse_cutoff_for_platform(cutoff_input: str, platform: str, max_videos: int = None) -> dict:
    """
    Parse cutoff input and return appropriate parameters for each platform.
    
    Args:
        cutoff_input: User input for cutoff (date, relative time, or number)
        platform: Platform name (facebook, instagram, tiktok, x, youtube)
        max_videos: Optional max videos limit for TikTok
        
    Returns:
        Dictionary with platform-specific parameters
    """
    result = {}
    
    if platform == 'tiktok':
        # TikTok: If date given, use default 1000 unless number specified
        if cutoff_input.isdigit():
            result['tiktok_max_videos'] = int(cutoff_input)
        else:
            result['tiktok_max_videos'] = max_videos or 1000
    
    elif platform == 'facebook':
        # Facebook: Parse specific time expressions and store the exact cutoff
        cutoff_lower = cutoff_input.lower()
        
        # Parse relative time expressions with specific numbers
        if 'day' in cutoff_lower:
            # Extract number of days
            day_match = re.search(r'(\d+)\s*day', cutoff_lower)
            if day_match:
                result['facebook_cutoff_days'] = int(day_match.group(1))
            else:
                result['facebook_cutoff_days'] = 1  # Default to 1 day for "day"
        elif 'week' in cutoff_lower:
            # Extract number of weeks
            week_match = re.search(r'(\d+)\s*week', cutoff_lower)
            if week_match:
                result['facebook_cutoff_weeks'] = int(week_match.group(1))
            else:
                result['facebook_cutoff_weeks'] = 1  # Default to 1 week for "week"
        elif 'month' in cutoff_lower:
            # Extract number of months
            month_match = re.search(r'(\d+)\s*month', cutoff_lower)
            if month_match:
                result['facebook_cutoff_months'] = int(month_match.group(1))
            else:
                result['facebook_cutoff_months'] = 1  # Default to 1 month for "month"
        elif 'year' in cutoff_lower:
            # Extract number of years
            year_match = re.search(r'(\d+)\s*year', cutoff_lower)
            if year_match:
                result['facebook_max_years'] = int(year_match.group(1))
            else:
                result['facebook_max_years'] = 1  # Default to 1 year for "year"
        else:
            # Try to parse as date, default to 2 years if invalid
            result['facebook_max_years'] = 2
    
    else:
        # Instagram, X, YouTube: Use uniform date format
        # Validate date format YYYY-MM-DD
        try:
            datetime.strptime(cutoff_input, '%Y-%m-%d')
            if platform == 'instagram':
                result['instagram_cutoff_date'] = cutoff_input
            elif platform == 'x':
                result['x_cutoff_date'] = cutoff_input
            elif platform == 'youtube':
                result['youtube_cutoff_date'] = cutoff_input
        except ValueError:
            # Use default dates if invalid format
            if platform == 'instagram':
                result['instagram_cutoff_date'] = config.INSTAGRAM_CUTOFF_DATE
            elif platform == 'x':
                result['x_cutoff_date'] = config.X_CUTOFF_DATE
            elif platform == 'youtube':
                result['youtube_cutoff_date'] = config.YOUTUBE_CUTOFF_DATE
    
    return result

def scrape_account_endpoint(account_url: str, cutoff_input: str = None, max_videos: int = None) -> dict:
    """
    Main function to scrape a single social media account with flexible cutoff handling.
    
    Args:
        account_url: URL of the account to scrape
        cutoff_input: Cutoff parameter (date, relative time, or number)
        max_videos: Maximum videos for TikTok (optional)
        
    Returns:
        Dictionary with scraping results
    """
    # Get default configuration
    scraper_config = config.get_default_config()
    
    # Identify platform to determine how to handle cutoff
    temp_scraper = SocialMediaScraper(scraper_config)
    platform = temp_scraper.identify_platform(account_url)
    
    # Parse cutoff input for the specific platform
    if cutoff_input:
        platform_params = parse_cutoff_for_platform(cutoff_input, platform, max_videos)
        # Update config with platform-specific parameters
        scraper_config.update(platform_params)
    
    # Validate configuration
    if not config.validate_config(scraper_config):
        return {
            'success': False,
            'error': 'Invalid configuration',
            'platform': 'unknown',
            'account_url': account_url,
            'videos': []
        }
    
    # Create necessary directories
    config.create_directories()
    
    # Initialize and run scraper
    scraper = SocialMediaScraper(scraper_config)
    result = scraper.scrape_single_account(account_url)
    
    return result

# Add this new endpoint to your Flask app (add before if __name__ == '__main__':)
@app.route('/fetch-links', methods=['GET', 'POST'])
def fetch_links():
    """
    Endpoint to fetch social media links from an account.
    
    Parameters:
    - username: Account URL or username to scrape
    - cutoff: Cutoff parameter (format varies by platform)
    - max_videos: Maximum videos for TikTok (optional)
    
    Returns:
    JSON response with scraped video links
    """
    try:
        # Handle both GET and POST requests
        if request.method == 'POST':
            data = request.get_json()
            username = data.get('username')
            cutoff = data.get('cutoff')
            max_videos = data.get('max_videos')
        else:  # GET
            username = request.args.get('username')
            cutoff = request.args.get('cutoff')
            max_videos = request.args.get('max_videos')
        
        if not username:
            return jsonify({
                "success": False,
                "error": "Missing username parameter"
            }), 400
        
        # Convert max_videos to int if provided
        if max_videos:
            try:
                max_videos = int(max_videos)
            except ValueError:
                max_videos = None
        
        # Create request ID for deduplication
        request_key = hashlib.md5(f"{username}_{cutoff}_{max_videos}".encode()).hexdigest()
        
        # Check if same request is already being processed
        with request_lock:
            if request_key in active_requests:
                time_diff = datetime.now() - active_requests[request_key]['start_time']
                if time_diff < timedelta(minutes=15):  # Still processing
                    logging.info(f"Duplicate request detected for {username}, returning in-progress status")
                    return jsonify({
                        "success": False,
                        "error": "Request already in progress",
                        "status": "processing",
                        "started_at": active_requests[request_key]['start_time'].isoformat(),
                        "estimated_remaining": "5-10 minutes"
                    }), 429  # Too Many Requests
                else:
                    # Request too old, remove it
                    del active_requests[request_key]
            
            # Mark request as active
            active_requests[request_key] = {
                'start_time': datetime.now(),
                'url': username,
                'cutoff': cutoff
            }
        
        try:
            account_url = username
            
            logging.info(f"Fetching links for: {account_url}")
            if cutoff:
                logging.info(f"Using cutoff: {cutoff}")
            if max_videos:
                logging.info(f"Max videos: {max_videos}")
            
            # Scrape the account
            result = scrape_account_endpoint(account_url, cutoff, max_videos)
            
            # Return the result
            return jsonify(result)
            
        finally:
            # Clean up request tracking
            with request_lock:
                if request_key in active_requests:
                    del active_requests[request_key]
                    logging.info(f"Cleaned up request tracking for {username}")
        
    except Exception as e:
        logging.error(f"Error in fetch-links endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "platform": "unknown",
            "videos": []
        }), 500 
        

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Create downloads directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    # Create subs directory for transcription files if it doesn't exist
    if not os.path.exists("./subs"):
        os.makedirs("./subs")
        logging.info("Created subs directory for transcription files")
    
    # Create news cookies directory if it doesn't exist
    if not os.path.exists(NEWS_COOKIES_DIR):
        os.makedirs(NEWS_COOKIES_DIR)
        logging.info(f"Created news cookies directory: {NEWS_COOKIES_DIR}")
    
    app.run(host='0.0.0.0', port=5000)
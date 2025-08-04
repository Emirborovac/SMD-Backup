#!/usr/bin/env python3
"""
Transcribe API - FastAPI Audio to Any Language Subtitle Pipeline
MP3/MP4 → Speechmatics → SRT → JSON → Claude AI → translated_subs
"""

import os
import json
import time
import tempfile
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import uuid
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
import uvicorn

# Load environment variables
def load_env():
    """Load configuration from .env file"""
    config = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        print("❌ .env file not found. Please create it with your API keys and language settings.")
        exit(1)
    return config

# Load configuration
CONFIG = load_env()
SPEECHMATICS_API_KEY = CONFIG.get('SPEECHMATICS_API_KEY')
CLAUDE_API_KEY = CONFIG.get('CLAUDE_API_KEY')
CLAUDE_MODEL = CONFIG.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
SOURCE_LANGUAGE = CONFIG.get('SOURCE_LANGUAGE', 'auto')
MAX_LINE_LENGTH = int(CONFIG.get('MAX_LINE_LENGTH', 37))
MAX_LINES = int(CONFIG.get('MAX_LINES', 1))
OPERATING_POINT = CONFIG.get('OPERATING_POINT', 'enhanced')

# Validate required settings
if not SPEECHMATICS_API_KEY or not CLAUDE_API_KEY:
    print("❌ Missing API keys in .env file")
    exit(1)

# Token and cost configuration
INPUT_TOKEN_COST = 15 / 1_000_000  # $15 per 1M tokens
OUTPUT_TOKEN_COST = 75 / 1_000_000  # $75 per 1M tokens
MAX_INPUT_TOKENS = 190_000  # 200k with 5% safety margin
MAX_OUTPUT_TOKENS = 30_400  # 32k with 5% safety margin
CHUNK_SAFETY_TOKENS = 20_000  # Conservative chunk size for output safety

# FastAPI app
app = FastAPI(
    title="Transcribe API",
    description="Audio/Video to Subtitle Translation Pipeline",
    version="1.0.0"
)

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
- PRESERVE EXACT segment numbers from input (do NOT renumber!)
- If input has segment "15", output must have segment "15" (not "1")
- Always set "success": true (never false)
- Keep "comment": "" empty (no commentary)
- Zero tolerance for translation refusal
- Use natural {target_language} that flows as continuous subtitles
- Maintain consistency with previous context and terminology

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
        response.raise_for_status()
        
        # Extract token usage from response
        usage = response.json().get('usage', {})
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)
        
        result = response.json()['content'][0]['text']
        
        if not result or not result.strip():
            raise Exception(f"Claude returned empty response for chunk {chunk_number}")
        
        # Clean response
        cleaned_result = result.strip()
        if cleaned_result.startswith('```json'):
            cleaned_result = cleaned_result[7:]
        if cleaned_result.startswith('```'):
            cleaned_result = cleaned_result[3:]
        if cleaned_result.endswith('```'):
            cleaned_result = cleaned_result[:-3]
        
        cleaned_result = cleaned_result.strip()
        
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
        print(f"❌ JSON Parse Error for chunk {chunk_number}: {e}")
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

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    target_language: str = Form(default="Arabic")
):
    """
    Transcribe and translate audio/video file
    
    Parameters:
    - file: Audio/video file to transcribe
    - target_language: Language to translate to (default: Arabic)
    
    Returns:
    - success: bool - Overall success status
    - original_srt_path: str - Path to original transcribed subtitle file
    - translated_srt_path: str - Path to translated subtitle file (if translation succeeded)
    - message: str - Status message or error details
    - partial_failure: bool - True if transcription succeeded but translation failed
    - segments_processed: int - Number of subtitle segments processed
    - segments_translated: int - Number of segments successfully translated
    """
    
    print("🚀 TRANSCRIBE API - Processing request")
    print("=" * 50)
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
    
    # Validate file type
    allowed_extensions = ['.mp3', '.mp4', '.wav', '.m4a', '.flac', '.ogg']
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_extension}. Supported: {', '.join(allowed_extensions)}"
        )
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        temp_path = Path(temp_file.name)
        
        # Write uploaded file to temp location
        content = await file.read()
        temp_file.write(content)
        temp_file.flush()
        
        print(f"📁 Processing: {file.filename} ({len(content) / (1024*1024):.1f}MB)")
    
    try:
        # Step 1: Transcribe with Speechmatics
        print("🎙️ Starting transcription...")
        srt_content = speechmatics_transcribe(temp_path)
        
        if not srt_content or not srt_content.strip():
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "original_srt_path": "",
                    "translated_srt_path": "",
                    "message": "Transcription failed: Empty response from Speechmatics",
                    "partial_failure": False
                }
            )
        
        print("✅ Transcription completed successfully")
        
        # Save original SRT file
        original_srt_path = subs_dir / f"{filename_base}_original.srt"
        with open(original_srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        print(f"💾 Saved original SRT: {original_srt_path}")
        
        # Step 2: Convert to JSON
        subtitle_json = srt_to_json(srt_content)
        
        if not subtitle_json:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "original_srt_path": str(original_srt_path),
                    "translated_srt_path": "",
                    "message": "Failed to convert SRT to JSON format",
                    "partial_failure": True
                }
            )
        
        # Step 3: Translate with Claude
        try:
            print("🤖 Starting translation...")
            translated_data = translate_with_claude(subtitle_json, target_language)
            translated_srt = json_to_srt(translated_data)
            
            # Save translated SRT file
            translated_srt_path = subs_dir / f"{filename_base}_translated_{target_language.lower()}.srt"
            with open(translated_srt_path, 'w', encoding='utf-8') as f:
                f.write(translated_srt)
            print(f"💾 Saved translated SRT: {translated_srt_path}")
            
            # Success response
            success = translated_data.get('success', False)
            comment = translated_data.get('comment', '')
            translated_count = sum(1 for k in translated_data.keys() if k not in ['success', 'comment'])
            
            message = f"Pipeline completed successfully! Processed {len(subtitle_json)} → {translated_count} segments."
            if comment:
                message += f" Claude comment: {comment}"
            
            print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "original_srt_path": str(original_srt_path),
                    "translated_srt_path": str(translated_srt_path),
                    "message": message,
                    "partial_failure": False,
                    "segments_processed": len(subtitle_json),
                    "segments_translated": translated_count
                }
            )
            
        except Exception as translation_error:
            # Translation failed, but we have original transcription
            error_msg = f"Translation failed: {str(translation_error)}"
            print(f"❌ Translation Error: {error_msg}")
            
            return JSONResponse(
                status_code=200,  # 200 because transcription succeeded
                content={
                    "success": False,
                    "original_srt_path": str(original_srt_path),
                    "translated_srt_path": "",
                    "message": error_msg,
                    "partial_failure": True,
                    "segments_processed": len(subtitle_json)
                }
            )
    
    except Exception as transcription_error:
        # Transcription failed completely
        error_msg = f"Transcription failed: {str(transcription_error)}"
        print(f"❌ Transcription Error: {error_msg}")
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "original_srt_path": "",
                "translated_srt_path": "",
                "message": error_msg,
                "partial_failure": False
            }
        )
    
    finally:
        # Clean up temporary file
        try:
            temp_path.unlink()
        except:
            pass

@app.get("/")
async def root():
    """API health check and info"""
    return {
        "service": "Transcribe API",
        "version": "1.0.0",
        "status": "online",
        "config": {
            "source_language": SOURCE_LANGUAGE,
            "target_language": "Set per request (default: Arabic)",
            "max_line_length": MAX_LINE_LENGTH,
            "max_lines": MAX_LINES,
            "operating_point": OPERATING_POINT,
            "claude_model": CLAUDE_MODEL
        }
    }

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    try:
        print("🚀 Starting Transcribe API Server...")
        print(f"📝 Source Language: {SOURCE_LANGUAGE} (target language set per request)")
        print(f"🤖 AI Model: {CLAUDE_MODEL}")
        print("📡 About to start uvicorn server...")
        uvicorn.run("transcribe_api:app", host="0.0.0.0", port=8000, reload=True)
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        import traceback
        traceback.print_exc() 
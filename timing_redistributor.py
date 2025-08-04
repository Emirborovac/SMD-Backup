#!/usr/bin/env python3
"""
SRT Timing Redistributor
========================

Redistributes subtitle timing based on word count while preserving original boundaries.
Groups continuous subtitles and redistributes time proportionally within each group.
"""

import re
import math
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class SubtitleSegment:
    """Represents a single subtitle segment"""
    number: int
    start_ms: int
    end_ms: int
    text: str
    
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms
    
    def word_count(self) -> int:
        """Count words, handling multiple languages including Arabic"""
        # Remove HTML tags, extra whitespace, and split by whitespace
        clean_text = re.sub(r'<[^>]+>', '', self.text.strip())
        words = clean_text.split()
        return len([word for word in words if word.strip()])


def parse_timestamp(timestamp_str: str) -> int:
    """Parse SRT timestamp to milliseconds"""
    try:
        # Format: "00:00:01,730"
        time_part, ms_part = timestamp_str.split(',')
        hours, minutes, seconds = map(int, time_part.split(':'))
        milliseconds = int(ms_part)
        
        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        return max(0, total_ms)
        
    except (ValueError, IndexError) as e:
        print(f"ERROR: Failed to parse timestamp '{timestamp_str}': {e}")
        return 0


def format_timestamp(total_ms: int) -> str:
    """Convert milliseconds back to SRT timestamp format"""
    total_ms = max(0, total_ms)
    
    hours = total_ms // (1000 * 60 * 60)
    minutes = (total_ms % (1000 * 60 * 60)) // (1000 * 60)
    seconds = (total_ms % (1000 * 60)) // 1000
    milliseconds = total_ms % 1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt_content(srt_content: str) -> List[SubtitleSegment]:
    """Parse SRT content into SubtitleSegment objects"""
    segments = []
    blocks = srt_content.strip().split('\n\n')
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            try:
                number = int(lines[0].strip())
                timestamp_line = lines[1].strip()
                text = '\n'.join(lines[2:]).strip()
                
                # Parse timestamps
                start_str, end_str = timestamp_line.split(' --> ')
                start_ms = parse_timestamp(start_str.strip())
                end_ms = parse_timestamp(end_str.strip())
                
                segments.append(SubtitleSegment(number, start_ms, end_ms, text))
                
            except (ValueError, IndexError) as e:
                print(f"WARNING: Skipping malformed subtitle block: {e}")
                continue
    
    return segments


def group_continuous_subtitles(segments: List[SubtitleSegment], max_gap_ms: int = 500) -> List[List[SubtitleSegment]]:
    """Group continuous subtitles based on time gaps"""
    if not segments:
        return []
    
    groups = []
    current_group = [segments[0]]
    
    for i in range(1, len(segments)):
        prev_segment = segments[i-1]
        curr_segment = segments[i]
        
        # Calculate gap between segments
        gap_ms = curr_segment.start_ms - prev_segment.end_ms
        
        if gap_ms <= max_gap_ms:
            # Continue current group
            current_group.append(curr_segment)
        else:
            # Start new group
            groups.append(current_group)
            current_group = [curr_segment]
    
    # Add the last group
    if current_group:
        groups.append(current_group)
    
    return groups


def redistribute_timing_in_group(group: List[SubtitleSegment], min_duration_ms: int = 1200) -> List[SubtitleSegment]:
    """Redistribute timing within a group based on word count"""
    if len(group) <= 1:
        return group
    
    # Calculate word counts
    word_counts = [seg.word_count() for seg in group]
    total_words = sum(word_counts)
    
    if total_words == 0:
        print("WARNING: Group has no words, keeping original timing")
        return group
    
    # Get original group boundaries
    group_start_ms = group[0].start_ms
    group_end_ms = group[-1].end_ms
    total_duration_ms = group_end_ms - group_start_ms
    
    if total_duration_ms <= 0:
        print("WARNING: Group has invalid duration, keeping original timing")
        return group
    
    print(f"   Redistributing group: {len(group)} segments, {total_words} words, {total_duration_ms}ms duration")
    
    # Calculate proportional durations
    redistributed_segments = []
    current_start_ms = group_start_ms
    
    for i, segment in enumerate(group):
        words = word_counts[i]
        
        if i == len(group) - 1:
            # Last segment: use remaining time to preserve original end
            segment_end_ms = group_end_ms
        else:
            # Calculate proportional duration
            proportion = words / total_words if total_words > 0 else 1.0 / len(group)
            proportional_duration = int(total_duration_ms * proportion)
            
            # Apply minimum duration constraint
            actual_duration = max(proportional_duration, min_duration_ms)
            segment_end_ms = current_start_ms + actual_duration
            
            # Ensure we don't exceed group boundaries
            if segment_end_ms > group_end_ms:
                segment_end_ms = group_end_ms
        
        # Create redistributed segment
        new_segment = SubtitleSegment(
            number=segment.number,
            start_ms=current_start_ms,
            end_ms=segment_end_ms,
            text=segment.text
        )
        
        redistributed_segments.append(new_segment)
        
        # Update for next iteration
        current_start_ms = segment_end_ms
    
    # Verification: ensure last segment ends at original group end
    if redistributed_segments:
        redistributed_segments[-1].end_ms = group_end_ms
    
    return redistributed_segments


def redistribute_srt_timing(srt_content: str, max_gap_ms: int = 500, min_duration_ms: int = 1200) -> str:
    """Main function to redistribute SRT timing based on word count"""
    print("🔧 Starting intelligent timing redistribution...")
    
    # Parse SRT content
    segments = parse_srt_content(srt_content)
    if not segments:
        print("No valid segments found")
        return srt_content
    
    print(f"   Parsed {len(segments)} segments")
    
    # Group continuous subtitles
    groups = group_continuous_subtitles(segments, max_gap_ms)
    print(f"   Grouped into {len(groups)} continuous blocks")
    
    # Redistribute timing within each group
    all_redistributed = []
    groups_processed = 0
    
    for group in groups:
        if len(group) > 1:
            redistributed_group = redistribute_timing_in_group(group, min_duration_ms)
            all_redistributed.extend(redistributed_group)
            groups_processed += 1
            print(f"     Processed group with {len(group)} segments")
        else:
            # Single segment groups don't need redistribution
            all_redistributed.extend(group)
    
    print(f"   Redistributed timing for {groups_processed} groups")
    
    # Sort by segment number to maintain order
    all_redistributed.sort(key=lambda x: x.number)
    
    # Convert back to SRT format
    srt_lines = []
    for segment in all_redistributed:
        srt_lines.append(str(segment.number))
        srt_lines.append(f"{format_timestamp(segment.start_ms)} --> {format_timestamp(segment.end_ms)}")
        srt_lines.append(segment.text)
        srt_lines.append("")  # Empty line between segments
    
    result = '\n'.join(srt_lines).strip()
    print("✅ Timing redistribution completed!")
    
    return result


def process_srt_file(input_path: str, output_path: str = None, max_gap_ms: int = 500, min_duration_ms: int = 1200):
    """Process an SRT file with timing redistribution"""
    if output_path is None:
        output_path = input_path.replace('.srt', '_redistributed.srt')
    
    print(f"📖 Reading SRT file: {input_path}")
    
    try:
        with open(input_path, 'r', encoding='utf-8-sig') as f:
            srt_content = f.read()
    except UnicodeDecodeError:
        # Fallback to different encodings
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                with open(input_path, 'r', encoding=encoding) as f:
                    srt_content = f.read()
                print(f"   Successfully read with {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue
        else:
            raise Exception("Could not read file with any supported encoding")
    
    # Redistribute timing
    redistributed_content = redistribute_srt_timing(srt_content, max_gap_ms, min_duration_ms)
    
    # Save redistributed SRT
    print(f"💾 Saving redistributed SRT: {output_path}")
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(redistributed_content)
    
    print("🎉 Process completed successfully!")
    return output_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python timing_redistributor.py <input.srt> [output.srt] [max_gap_ms] [min_duration_ms]")
        print("Example: python timing_redistributor.py subtitles.srt redistributed.srt 500 1200")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    max_gap = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    min_duration = int(sys.argv[4]) if len(sys.argv) > 4 else 1200
    
    process_srt_file(input_file, output_file, max_gap, min_duration)
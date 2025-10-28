#!/usr/bin/env python3
"""
riftkit: MP3 to practice-ready REAPER project

Usage:
    ./riftkit.py <song.mp3>
    
Author: Owen Corpening
License: MIT
"""

import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='Process MP3 into practice-ready REAPER project')
    parser.add_argument('mp3_file', help='Input MP3 file')
    parser.add_argument('--output', help='Output directory', default='./projects')
    parser.add_argument('--model', help='UVR model to use', default='MDX23C')
    parser.add_argument('--no-lyrics', action='store_true', help='Skip lyrics transcription')
    
    args = parser.parse_args()
    
    print(f"Processing: {args.mp3_file}")
    print("Status: Script template - functionality coming soon")
    print("\nThis is the initial commit. Check back for updates.")
    
    # TODO: Implement workflow
    # 1. Separate stems with UVR
    # 2. Transcribe vocals with Whisper
    # 3. Create REAPER project
    # 4. Insert lyrics
    
if __name__ == "__main__":
    main()

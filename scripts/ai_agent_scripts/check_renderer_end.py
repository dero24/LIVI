#!/usr/bin/env python3
"""Check the end of the renderer JS to see if it's wrapped in a closure."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('out_renderer_index.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Check the last 500 chars of the ORIGINAL file (before our patch)
# Our patch added ~4589 chars, so the original ends at len(js) - 4589
original_end = len(js) - 4589
print(f"Total length: {len(js)}")
print(f"Original length: {original_end}")
print(f"\n=== Last 300 chars of original file ===")
print(js[original_end-300:original_end])
print(f"\n=== First 200 chars of our patch ===")
print(js[original_end:original_end+200])
print(f"\n=== Last 200 chars of file ===")
print(js[-200:])

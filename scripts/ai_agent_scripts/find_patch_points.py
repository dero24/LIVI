#!/usr/bin/env python3
"""Find and print the exact code around key patterns in the minified files."""
import re

# Main process file
with open('out_main_main.js', 'r', encoding='utf-8') as f:
    main_js = f.read()

# Find applyVideoCrop and surrounding code
for pattern in ['applyVideoCrop', 'videoCrop', 'projectionViewArea']:
    idx = main_js.find(pattern)
    while idx != -1:
        start = max(0, idx - 200)
        end = min(len(main_js), idx + 300)
        print(f"\n=== {pattern} at offset {idx} ===")
        print(main_js[start:end])
        print("---")
        idx = main_js.find(pattern, idx + 1)
        if idx > 0 and idx - (idx - len(pattern)) < 500:
            # Skip nearby duplicates
            break

# Find aaContentArea
idx = main_js.find('aaContentArea')
if idx != -1:
    start = max(0, idx - 200)
    end = min(len(main_js), idx + 400)
    print(f"\n=== aaContentArea at offset {idx} ===")
    print(main_js[start:end])
    print("---")

print("\n\n========== RENDERER FILE ==========\n")

# Renderer file
with open('out_renderer_index.js', 'r', encoding='utf-8') as f:
    renderer_js = f.read()

for pattern in ['projectionViewArea', 'aaContentArea', 'useProjectionMultiTouch', 'cropLeft']:
    idx = renderer_js.find(pattern)
    if idx != -1:
        start = max(0, idx - 200)
        end = min(len(renderer_js), idx + 400)
        print(f"\n=== {pattern} at offset {idx} ===")
        print(renderer_js[start:end])
        print("---")

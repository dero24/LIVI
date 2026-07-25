#!/usr/bin/env python3
"""Find the touch transform construction in the renderer."""

with open('out_renderer_index.js', 'r', encoding='utf-8') as f:
    renderer_js = f.read()

# Find where the touch transform is built (streamWidth, streamHeight, cropLeft, etc.)
# Search for the pattern that constructs the transform object
patterns = [
    'streamWidth',
    'cropLeft:Math.max',
    'useProjectionMultiTouch',
    'aaContentArea',
    'contentWidth',
    'visibleWidth',
]

for pattern in patterns:
    idx = renderer_js.find(pattern)
    while idx != -1:
        start = max(0, idx - 300)
        end = min(len(renderer_js), idx + 400)
        print(f"\n=== {pattern} at offset {idx} ===")
        print(renderer_js[start:end])
        print("---")
        # Only show first occurrence
        break

# Also find yi (the minified aaContentArea function)
idx = renderer_js.find('function yi(')
if idx == -1:
    # Try other patterns
    idx = renderer_js.find('yi=')
    if idx == -1:
        # Search for the content area function by its logic
        idx = renderer_js.find('contentWidth:')
        if idx != -1:
            start = max(0, idx - 500)
            end = min(len(renderer_js), idx + 200)
            print(f"\n=== contentWidth: context at offset {idx} ===")
            print(renderer_js[start:end])
            print("---")

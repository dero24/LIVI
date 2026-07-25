#!/usr/bin/env python3
"""Find the telemetry store and Home component code in the renderer for patching."""
import re

with open('out_renderer_index.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Find the telemetry store / useStatusStore
patterns = [
    'useStatusStore',
    'isStreaming',
    'telemetry:push',
    'telemetry:update',
    'onEvent',
    'projection.ipc',
    'sendCommand',
    'Home Hub',
    'simpleMode',
    'No phone connected',
]

for pattern in patterns:
    idx = js.find(pattern)
    if idx != -1:
        start = max(0, idx - 100)
        end = min(len(js), idx + 200)
        print(f"\n=== {pattern} at offset {idx} ===")
        print(js[start:end])
        print("---")
    else:
        print(f"\n=== {pattern} NOT FOUND ===")

#!/usr/bin/env python3
"""Find the exact Home component code boundaries in the renderer for patching."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('out_renderer_index.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Find the Home component - it starts with "Home Hub" text
# and contains the ActionButton, device cards, etc.

# Find the start of the Home component function
# Looking for the pattern that defines the Home export
home_idx = js.find('Home Hub')
if home_idx == -1:
    print("Home Hub not found!")
    exit(1)

# Go back to find the function start
# The component is likely defined as: var XX = () => { ... } or function XX() { ... }
# Let's find the "useDevices" call which is near the start
use_devices_idx = js.rfind('useDevices', 0, home_idx)
print(f"useDevices at: {use_devices_idx}")
print(f"Home Hub at: {home_idx}")

# Show a large chunk around the Home component
start = max(0, use_devices_idx - 300)
end = min(len(js), home_idx + 200)
print(f"\n=== Home component start (offset {start} to {end}) ===")
print(js[start:end])
print("---")

# Find the end of the Home component - look for the closing pattern
# After the device cards, there should be a closing bracket
# Look for "No phone connected" and the device map
no_phone_idx = js.find('No phone connected', home_idx)
print(f"\nNo phone connected at: {no_phone_idx}")

# Show the end of the component
end_start = no_phone_idx
end_end = min(len(js), no_phone_idx + 800)
print(f"\n=== Home component end (offset {end_start} to {end_end}) ===")
print(js[end_start:end_end])
print("---")

# Find the sendCmd function
sendcmd_idx = js.find('sendCommand', 0, home_idx)
if sendcmd_idx == -1:
    sendcmd_idx = js.find('sendCmd', 0, home_idx)
print(f"\nsendCmd near: {sendcmd_idx}")
if sendcmd_idx != -1:
    s = max(0, sendcmd_idx - 50)
    e = min(len(js), sendcmd_idx + 200)
    print(js[s:e])

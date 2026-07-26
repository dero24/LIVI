#!/usr/bin/env python3
"""Analyze screenshot to check if overlay is rendering."""
from PIL import Image
import os
# Find whichever screenshot exists
for name in ['/tmp/homehub_screenshot.png', '/tmp/homehub_screenshot0.png']:
    if os.path.exists(name):
        img = Image.open(name)
        print(f'Opened: {name}')
        break
else:
    print('No screenshot found!')
    exit(1)
print(f'Size: {img.size}, Mode: {img.mode}')
# Check top region (hub bar area, y=0..424)
top = img.crop((0, 0, img.size[0], 424))
top_colors = top.getcolors(maxcolors=256)
print(f'Top region (hub bar) colors: {len(top_colors) if top_colors else "256+"}')
if top_colors:
    top_colors.sort(reverse=True)
    for count, color in top_colors[:5]:
        print(f'  {count:6d} px: {color}')
# Check bottom region (phone area, y=424..1024)
bottom = img.crop((0, 424, img.size[0], img.size[1]))
bottom_colors = bottom.getcolors(maxcolors=256)
print(f'Bottom region (phone) colors: {len(bottom_colors) if bottom_colors else "256+"}')
if bottom_colors:
    bottom_colors.sort(reverse=True)
    for count, color in bottom_colors[:5]:
        print(f'  {count:6d} px: {color}')
# Sample some specific pixels
print(f'Pixel (300, 50) hub-time area: {img.getpixel((300, 50))}')
print(f'Pixel (300, 200) hub-devices area: {img.getpixel((300, 200))}')
print(f'Pixel (300, 350) hub-bottom area: {img.getpixel((300, 350))}')
print(f'Pixel (300, 700) phone area: {img.getpixel((300, 700))}')

#!/usr/bin/env python3
"""Compare brightness of nightmode_off vs nightmode_on screenshots."""
import struct, zlib

def read_png_avg_brightness(path):
    with open(path, 'rb') as f:
        data = f.read()
    # Find IHDR
    ihdr_idx = data.find(b'IHDR')
    w = struct.unpack('>I', data[ihdr_idx+4:ihdr_idx+8])[0]
    h = struct.unpack('>I', data[ihdr_idx+8:ihdr_idx+12])[0]
    # Find all IDAT chunks
    idat = b''
    idx = 0
    while True:
        idat_idx = data.find(b'IDAT', idx)
        if idat_idx == -1: break
        chunk_len = struct.unpack('>I', data[idat_idx-4:idat_idx])[0]
        idat += data[idat_idx+4:idat_idx+4+chunk_len]
        idx = idat_idx + 4 + chunk_len
    raw = zlib.decompress(idat)
    # Filter byte per row, then RGB
    bytes_per_pixel = 3  # assuming RGB
    stride = w * bytes_per_pixel + 1  # +1 for filter byte
    total = 0
    count = 0
    for y in range(h):
        row_start = y * stride
        filter_byte = raw[row_start]
        for x in range(w):
            i = row_start + 1 + x * bytes_per_pixel
            r, g, b = raw[i], raw[i+1], raw[i+2]
            total += (r + g + b) / 3
            count += 1
    return total / count if count > 0 else 0

off = read_png_avg_brightness(r'C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\screenshots\nightmode_off.png')
on = read_png_avg_brightness(r'C:\Users\Robby\Windsurf Projects\random_stuff\raspberry-pi_homephone\LIVI\screenshots\nightmode_on.png')

print(f'nightmode_off avg brightness: {off:.1f}/255')
print(f'nightmode_on  avg brightness: {on:.1f}/255')
print(f'Difference: {off - on:.1f} ({(off - on) / off * 100:.1f}% dimmer)')
if on < off:
    print('PASS: night mode ON is dimmer than OFF')
else:
    print('FAIL: night mode ON is NOT dimmer — dimming overlay may not be working')

#!/usr/bin/env python3
"""Update LIVI config for portrait master phone layout."""
import json
f = '/home/raspberry/.config/LIVI/config.json'
c = json.load(open(f))
c['projectionWidth'] = 600
c['projectionHeight'] = 1024
c['projectionViewAreaTop'] = 440
# Lower DPI so portrait AA renders smaller UI elements (less zoomed in).
# Auto DPI is 200 (based on 1920x1080 tier). At 200dpi, portrait content
# area (633px) = 506dp — too narrow, apps render huge. At 120dpi, 633px
# = 844dp — similar width to the old 1024x1024 square (864dp at 200dpi).
c['projectionDpi'] = 120
json.dump(c, open(f, 'w'), indent=2)
print('Config updated: projectionWidth=600, projectionHeight=1024,')
print('  projectionViewAreaTop=440, projectionDpi=120')

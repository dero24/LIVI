#!/usr/bin/env python3
"""Check LIVI config for wireless/CarPlay settings."""
import json
f = '/home/raspberry/.config/LIVI/config.json'
c = json.load(open(f))
fields = [
    'wirelessAaEnabled', 'wirelessCpEnabled', 'wifiPassword', 'wifiInterface',
    'wifiType', 'wifiChannel', 'btAdapter', 'dongleToolsIp',
    'projectionWidth', 'projectionHeight', 'projectionViewAreaTop',
    'projectionViewAreaBottom', 'projectionViewAreaLeft', 'projectionViewAreaRight',
    'projectionDpi', 'projectionFps'
]
for k in fields:
    v = c.get(k)
    if k == 'wifiPassword' and v:
        v = '[set]'
    print(f'{k}: {v}')

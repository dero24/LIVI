#!/usr/bin/env python3
"""Print current LIVI config."""
import json
with open('/home/raspberry/.config/LIVI/config.json') as f:
    c = json.load(f)
print(f"projection: {c['projectionWidth']}x{c['projectionHeight']}")
print(f"viewArea: L={c.get('projectionViewAreaLeft',0)} R={c.get('projectionViewAreaRight',0)} T={c.get('projectionViewAreaTop',0)} B={c.get('projectionViewAreaBottom',0)}")
print(f"startPage: {c.get('startPage','home')}")
print(f"carName: {c.get('carName','unknown')}")
print(f"kiosk: {c.get('kiosk',{})}")

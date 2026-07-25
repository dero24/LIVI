#!/usr/bin/env python3
"""Revert config to 1024x1024 with no view area insets."""
import json

config_path = '/home/raspberry/.config/LIVI/config.json'

with open(config_path) as f:
    cfg = json.load(f)

cfg['projectionViewAreaLeft'] = 0
cfg['projectionViewAreaRight'] = 0
cfg['projectionViewAreaTop'] = 0
cfg['projectionViewAreaBottom'] = 0

with open(config_path, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f"Reverted: projectionWidth={cfg['projectionWidth']}, projectionHeight={cfg['projectionHeight']}")
print(f"  viewArea insets all reset to 0")
print("done")

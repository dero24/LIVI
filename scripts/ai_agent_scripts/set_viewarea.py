#!/usr/bin/env python3
"""Set projectionViewArea insets in config.json."""
import json

config_path = '/home/raspberry/.config/LIVI/config.json'

with open(config_path) as f:
    cfg = json.load(f)

print(f"Before: projectionViewAreaLeft={cfg.get('projectionViewAreaLeft')}, projectionViewAreaRight={cfg.get('projectionViewAreaRight')}")
print(f"  projectionWidth={cfg['projectionWidth']}, projectionHeight={cfg['projectionHeight']}")

# Set insets to crop the center 600/1024 of the width
# inset = (1024 - 600) / 2 = 212 on each side
cfg['projectionViewAreaLeft'] = 212
cfg['projectionViewAreaRight'] = 212
cfg['projectionViewAreaTop'] = 0
cfg['projectionViewAreaBottom'] = 0

with open(config_path, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f"After: projectionViewAreaLeft={cfg['projectionViewAreaLeft']}, projectionViewAreaRight={cfg['projectionViewAreaRight']}")
print("done")

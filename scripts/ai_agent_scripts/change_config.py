#!/usr/bin/env python3
"""Change projectionWidth/projectionHeight in LIVI config.json on the Pi."""
import json, sys

config_path = '/home/raspberry/.config/LIVI/config.json'
backup_path = '/home/raspberry/.config/LIVI/config.json.bak.600x1024'

with open(config_path) as f:
    cfg = json.load(f)

# Back up original
import shutil
shutil.copy2(config_path, backup_path)
print(f'Backed up to {backup_path}')
print(f'  Old: projectionWidth={cfg["projectionWidth"]}, projectionHeight={cfg["projectionHeight"]}')

# Change values
new_w = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
new_h = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
cfg['projectionWidth'] = new_w
cfg['projectionHeight'] = new_h

with open(config_path, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f'  New: projectionWidth={new_w}, projectionHeight={new_h}')
print('done')

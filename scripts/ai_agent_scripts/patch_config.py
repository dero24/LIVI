#!/usr/bin/env python3
import json
import shutil

p = '/home/raspberry/.config/LIVI/config.json'
shutil.copy(p, p + '.bak2')
with open(p, 'r') as f:
    d = json.load(f)

d['carName'] = 'homephone-countertop'
d['projectionWidth'] = 600
d['projectionHeight'] = 1024
d['projectionDpi'] = 0

with open(p, 'w') as f:
    json.dump(d, f, indent=2)

print('patched:', {k: d[k] for k in ('carName', 'projectionWidth', 'projectionHeight', 'projectionDpi')})

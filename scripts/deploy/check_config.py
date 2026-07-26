#!/usr/bin/env python3
"""Check LIVI config for projection/video settings."""
import json
c = json.load(open("/home/raspberry/.config/LIVI/config.json"))
for k in sorted(c):
    if any(x in k.lower() for x in ["projection", "video", "width", "height", "resolution", "dpi", "safe"]):
        print(f"  {k} = {c[k]}")

#!/usr/bin/env python3
"""Disable wireless AA (revert to wired-only)."""
import json

CONFIG_PATH = '/home/raspberry/.config/LIVI/config.json'

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

config['wirelessAaEnabled'] = False
config['wifiInterface'] = 'wlan0'
config['wifiType'] = '5ghz'
config['wifiChannel'] = 36

with open(CONFIG_PATH, 'w') as f:
    json.dump(config, f, indent=2)

print(f"wirelessAaEnabled: {config['wirelessAaEnabled']}")
print(f"wifiInterface: {config['wifiInterface']}")
print("Wireless AA disabled. Restart LIVI to apply.")

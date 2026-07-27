#!/usr/bin/env python3
"""Enable wireless AA on wlan1 (USB dongle) for LIVI."""
import json

CONFIG_PATH = '/home/raspberry/.config/LIVI/config.json'

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

print("=== Before ===")
print(f"  wirelessAaEnabled: {config.get('wirelessAaEnabled')}")
print(f"  wirelessCpEnabled: {config.get('wirelessCpEnabled')}")
print(f"  wifiInterface: {config.get('wifiInterface')}")
print(f"  wifiType: {config.get('wifiType')}")
print(f"  wifiChannel: {config.get('wifiChannel')}")
print(f"  wifiPassword: {config.get('wifiPassword')}")
print(f"  carName (SSID): {config.get('carName')}")
print(f"  country: {config.get('country')}")

# Enable wireless AA on wlan1 (USB dongle, 2.4GHz)
config['wirelessAaEnabled'] = True
config['wifiInterface'] = 'wlan1'
config['wifiType'] = '2.4ghz'
config['wifiChannel'] = 6  # 2.4GHz channel 1-11
config['country'] = 'US'   # Set correct regulatory domain

with open(CONFIG_PATH, 'w') as f:
    json.dump(config, f, indent=2)

print("\n=== After ===")
print(f"  wirelessAaEnabled: {config['wirelessAaEnabled']}")
print(f"  wifiInterface: {config['wifiInterface']}")
print(f"  wifiType: {config['wifiType']}")
print(f"  wifiChannel: {config['wifiChannel']}")
print(f"  country: {config['country']}")
print(f"  SSID will be: {config['carName']}")
print(f"  Password will be: {config['wifiPassword']}")
print("\nWireless AA enabled. Restart LIVI to apply.")

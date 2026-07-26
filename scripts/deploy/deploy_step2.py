#!/usr/bin/env python3
"""Run patch, update config, clear caches, restart LIVI."""
import subprocess, json, os, time

# Run patch script
print("Running patch script...")
r = subprocess.run(["python3", "/home/raspberry/patch_homehub_v2.py"], capture_output=True, text=True, timeout=30)
print(r.stdout[-500:] if r.stdout else "")
if r.returncode != 0:
    print("PATCH FAILED:", r.stderr[-500:])
    exit(1)

# Update config
print("Updating config (projectionViewAreaTop=450)...")
cfg_path = "/home/raspberry/.config/LIVI/config.json"
c = json.load(open(cfg_path))
c["projectionViewAreaTop"] = 450
json.dump(c, open(cfg_path, "w"), indent=2)
print(f"  projectionViewAreaTop = {c['projectionViewAreaTop']}")

# Clear caches
print("Clearing caches...")
for d in ["/home/raspberry/.config/LIVI/Cache", "/home/raspberry/.config/LIVI/GPUCache", "/home/raspberry/.config/LIVI/Code Cache"]:
    if os.path.exists(d):
        subprocess.run(["rm", "-rf", d], check=False)

# Restart LIVI
print("Restarting LIVI...")
subprocess.run(["systemctl", "--user", "stop", "livi.service"], check=False)
time.sleep(2)
subprocess.run(["systemctl", "--user", "start", "livi.service"], check=False)
time.sleep(6)
r = subprocess.run(["systemctl", "--user", "is-active", "livi.service"], capture_output=True, text=True)
print(f"LIVI status: {r.stdout.strip()}")

#!/usr/bin/env python3
"""Check LIVI logs for AA session/video info."""
import subprocess, re

# Try journalctl first
try:
    r = subprocess.run(["journalctl", "--user", "-u", "livi.service", "--no-pager", "-n", "2000"],
                       capture_output=True, text=True, timeout=10)
    logs = r.stdout
except Exception:
    logs = ""

if not logs:
    # Try log files
    import glob, os
    candidates = glob.glob("/home/raspberry/.config/LIVI/logs/*.log") + \
                 glob.glob("/home/raspberry/.local/share/LIVI/logs/*.log") + \
                 glob.glob("/home/raspberry/.config/LIVI/main*.log")
    for f in sorted(candidates, key=os.path.getmtime, reverse=True):
        try:
            with open(f) as fh:
                logs = fh.read()
            print(f"# Reading: {f}")
            break
        except:
            pass

if not logs:
    # Check stderr/stdout redirect
    for f in ["/tmp/livi.log", "/home/raspberry/livi.log", "/home/raspberry/.config/LIVI/livi.log"]:
        if os.path.exists(f):
            with open(f) as fh:
                logs = fh.read()
            print(f"# Reading: {f}")
            break

# Search for relevant lines
patterns = ["Opened", "VideoConfig", "videoWidth", "videoHeight", "resolution",
            "touchW", "touchH", "inset", "AR", "tier", "sendTouch", "sendButton",
            "INPUT", "projectionWidth", "projectionHeight", "matchFitting"]
lines = logs.split("\n")
for line in lines:
    for p in patterns:
        if p.lower() in line.lower():
            print(line.strip()[:200])
            break

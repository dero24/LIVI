#!/usr/bin/env python3
"""Restart LIVI now that the dongle is stable, and monitor AP bringup."""
import subprocess, time, os

# First verify wlan1 is functional
print('=== Pre-restart: wlan1 status ===')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan1', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout if r.stdout else f'  Error: {r.stderr.strip()}')

# Bring wlan1 up manually first (so it's ready for LIVI)
print('=== Bringing wlan1 up manually ===')
r = subprocess.run(['sudo', '-S', 'ip', 'link', 'set', 'wlan1', 'up'],
                   input='pi\n', capture_output=True, text=True, timeout=5)
print(f'  rc={r.returncode}, {r.stderr.strip() or "OK"}')
time.sleep(2)

# Verify it's up
r = subprocess.run(['ip', 'link', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
print(f'  {r.stdout.strip()}')

# Restart LIVI
print()
print('=== Restarting LIVI ===')
r = subprocess.run(['systemctl', '--user', 'restart', 'livi.service'],
                   capture_output=True, text=True, timeout=10)
print(f'  rc={r.returncode}')

# Wait for LIVI to start and helper to initialize
print('  Waiting 15s for LIVI to initialize...')
time.sleep(15)

# Check LIVI status
r = subprocess.run(['systemctl', '--user', 'is-active', 'livi.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  LIVI: {r.stdout.strip()}')

# Check if helper is running
r = subprocess.run(['pgrep', '-f', 'livi-helper'], capture_output=True, text=True, timeout=5)
print(f'  Helper PIDs: {r.stdout.strip() or "not running"}')

# Check if LIVI_AA_WIRELESS is set
helper_pids = r.stdout.strip().split('\n')
for pid in helper_pids:
    if not pid:
        continue
    r2 = subprocess.run(['sudo', '-S', 'cat', f'/proc/{pid}/environ'],
                       input='pi\n', capture_output=True, text=True, timeout=5)
    has_wireless = 'LIVI_AA_WIRELESS=1' in r2.stdout
    print(f'  PID {pid} has LIVI_AA_WIRELESS=1: {has_wireless}')

# Wait more for AP to come up
print('  Waiting 10s more for AP bringup...')
time.sleep(10)

# Check hostapd
print()
print('=== hostapd ===')
r = subprocess.run(['pgrep', '-a', 'hostapd'], capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or '  not running')

# Check dnsmasq
print('=== dnsmasq ===')
r = subprocess.run(['pgrep', '-a', 'dnsmasq'], capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or '  not running')

# Check wlan1
print('=== wlan1 ===')
r = subprocess.run(['ip', 'addr', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check hostapd config
print('=== /tmp/livi-hostapd.conf ===')
if os.path.exists('/tmp/livi-hostapd.conf'):
    with open('/tmp/livi-hostapd.conf') as f:
        print(f.read())
else:
    print('  not found')

# Check hostapd_cli
print('=== hostapd_cli status ===')
r = subprocess.run(['sudo', '-S', 'hostapd_cli', '-p', '/var/run/hostapd', '-i', 'wlan1', 'status'],
                   input='pi\n', capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or f'  Error: {r.stderr.strip()}')

# WiFi scan
print()
print('=== WiFi scan (looking for LIVI AP) ===')
r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan0'],
                   capture_output=True, text=True, timeout=15)
for line in r.stdout.split('\n'):
    if 'homephone' in line.lower() or 'livi' in line.lower() or 'countertop' in line.lower():
        print(f'  MATCH: {line}')
print(f'  (total networks: {len(r.stdout.strip().split(chr(10)))-1})')

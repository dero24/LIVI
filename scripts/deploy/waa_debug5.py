#!/usr/bin/env python3
"""Check if the AP is actually up now, and check hostapd/dnsmasq."""
import subprocess, os, time

# Check hostapd
print('=== hostapd process ===')
r = subprocess.run(['pgrep', '-a', 'hostapd'], capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or '  not running')

# Check dnsmasq
print()
print('=== dnsmasq process ===')
r = subprocess.run(['pgrep', '-a', 'dnsmasq'], capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or '  not running')

# Check wlan1 state
print()
print('=== wlan1 state ===')
r = subprocess.run(['ip', 'addr', 'show', 'wlan1'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check if hostapd config was written
print('=== /tmp/livi-hostapd.conf ===')
if os.path.exists('/tmp/livi-hostapd.conf'):
    with open('/tmp/livi-hostapd.conf') as f:
        print(f.read())
else:
    print('  not found')

# Check hostapd_cli status
print('=== hostapd_cli status ===')
r = subprocess.run(['sudo', '-S', 'hostapd_cli', '-p', '/var/run/hostapd', '-i', 'wlan1', 'status'],
                   input='pi\n', capture_output=True, text=True, timeout=5)
print(r.stdout.strip() or f'  Error: {r.stderr.strip()}')

# Check if the AP is visible via scan
print()
print('=== WiFi scan from wlan0 (looking for LIVI AP) ===')
r = subprocess.run(['nmcli', 'dev', 'wifi', 'list', 'ifname', 'wlan0', '--rescan', 'no'],
                   capture_output=True, text=True, timeout=10)
for line in r.stdout.split('\n'):
    print(f'  {line}')

# Check the helper's stdout/stderr — it's spawned by LIVI, output may go to journal
print()
print('=== LIVI helper output (journalctl) ===')
r = subprocess.run(['journalctl', '--user', '-n', '100', '--no-pager', '-o', 'cat'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if any(x in line.lower() for x in ['wifi', 'wlan', 'ap', 'hostapd', 'wireless', 'bt', 'bluetooth', 'helper', 'error', 'fail', 'up ', 'ssid']):
        print(f'  {line}')

# Check if there's a LIVI log in the compositor output
print()
print('=== Check for LIVI stdout ===')
# The service is Type=oneshot, so output goes to journal
r = subprocess.run(['journalctl', '--user', '-u', 'livi.service', '-n', '100', '--no-pager', '-o', 'cat'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n')[-30:]:
    print(f'  {line}')

# Check bluetooth adapter
print()
print('=== Bluetooth adapter ===')
r = subprocess.run(['hciconfig', 'hci0'], capture_output=True, text=True, timeout=5)
print(r.stdout)

# Check if BT is discoverable
r = subprocess.run(['btmgmt', 'info'], capture_output=True, text=True, timeout=5)
print(r.stdout)

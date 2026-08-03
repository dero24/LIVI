#!/usr/bin/env python3
"""FINAL FIX: All bug fixes in one script.
Run this when the Pi is reachable."""
import subprocess, json, os, time

SUDO_PWD = 'pi\n'
def sudo(cmd, timeout=15):
    return subprocess.run(['sudo', '-S'] + cmd, input=SUDO_PWD,
                         capture_output=True, text=True, timeout=timeout)

results = []

# 1. Delete rogue BT scripts
print('=== 1. Delete rogue BT scripts ===')
for f in ['/home/raspberry/bt-agent.py', '/home/raspberry/bt_autoconnect.py',
          '/home/raspberry/.config/systemd/user/bluetooth-agent.service',
          '/home/raspberry/.config/systemd/user/bt-autoconnect.service']:
    if os.path.exists(f):
        os.remove(f)
        print(f'  Deleted: {f}')
        results.append(f'Deleted {os.path.basename(f)}')
    else:
        print(f'  Not found: {f}')

subprocess.run(['systemctl', '--user', 'daemon-reload'],
               capture_output=True, text=True, timeout=5)

# 2. Disable mpris-proxy (system-level)
print()
print('=== 2. Disable mpris-proxy (system) ===')
r = sudo(['systemctl', 'stop', 'mpris-proxy.service'], timeout=5)
print(f'  Stop: {r.returncode}')
r = sudo(['systemctl', 'disable', 'mpris-proxy.service'], timeout=5)
print(f'  Disable: {r.returncode} {r.stdout.strip()}')
r = sudo(['systemctl', 'is-enabled', 'mpris-proxy.service'], timeout=5)
print(f'  Status: {r.stdout.strip() or r.stderr.strip()}')

# 3. Create wlan0 watchdog service
print()
print('=== 3. Create wlan0 watchdog service ===')
watchdog_service = """[Unit]
Description=wlan0 connectivity watchdog (bounces interface on network drops)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/raspberry/wlan0_watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""
service_path = os.path.expanduser('~/.config/systemd/user/wlan0-watchdog.service')
os.makedirs(os.path.dirname(service_path), exist_ok=True)
with open(service_path, 'w') as f:
    f.write(watchdog_service)
print(f'  Service file written: {service_path}')

subprocess.run(['systemctl', '--user', 'daemon-reload'],
               capture_output=True, text=True, timeout=5)
r = subprocess.run(['systemctl', '--user', 'enable', 'wlan0-watchdog.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  Enabled: {r.stdout.strip()}')
r = subprocess.run(['systemctl', '--user', 'start', 'wlan0-watchdog.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  Started: {r.stdout.strip()}')
r = subprocess.run(['systemctl', '--user', 'is-active', 'wlan0-watchdog.service'],
                   capture_output=True, text=True, timeout=5)
print(f'  Status: {r.stdout.strip()}')
results.append(f'wlan0 watchdog: {r.stdout.strip()}')

# 4. Re-apply wlan0 power_save off
print()
print('=== 4. Re-apply wlan0 power_save off ===')
r = sudo(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'], timeout=5)
print(f'  iw power_save off: rc={r.returncode}')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                   capture_output=True, text=True, timeout=5)
print(f'  Current: {r.stdout.strip()}')

# 5. Verify deployed sidecar matches local copy
print()
print('=== 5. Verify deployed sidecar ===')
r = subprocess.run(['md5sum', '/home/raspberry/homephone-sidecar.py'],
                   capture_output=True, text=True, timeout=5)
print(f'  Deployed: {r.stdout.strip()}')

# Check key markers in deployed sidecar
r = subprocess.run(['curl', '-s', 'http://localhost:8123/settings'],
                   capture_output=True, text=True, timeout=5)
markers = {
    'Wireless Android Auto': 'BT info card',
    'Paired Audio Devices': 'Audio devices label',
    'in-iframe': 'iframe detection',
    'btPollTimer': 'BT polling',
    'Cache-Control': 'will check headers',
}
for marker, desc in markers.items():
    found = marker in r.stdout
    status = 'PASS' if found else 'FAIL'
    print(f'  {status}: {desc}')
    if not found:
        results.append(f'FAIL: {desc} not in deployed sidecar')

r2 = subprocess.run(['curl', '-s', '-D', '-', '-o', '/dev/null', 'http://localhost:8123/settings'],
                    capture_output=True, text=True, timeout=5)
has_no_store = 'no-store' in r2.stdout
print(f'  {"PASS" if has_no_store else "FAIL"}: Cache-Control no-store header')

# 6. Verify BT API
print()
print('=== 6. BT API verification ===')
r = subprocess.run(['curl', '-s', 'http://localhost:8123/api/bluetooth/devices'],
                   capture_output=True, text=True, timeout=5)
try:
    d = json.loads(r.stdout)
    for dev in d.get('devices', []):
        print(f'  {dev["name"]} | is_phone={dev.get("is_phone")} | connected={dev.get("connected")}')
    adp = d.get('adapter', {})
    print(f'  Adapter: {adp.get("name")} | powered={adp.get("powered")} | discoverable={adp.get("discoverable")}')
except:
    print(f'  Error: {r.stdout[:200]}')

# 7. Verify LIVI config
print()
print('=== 7. LIVI config ===')
with open('/home/raspberry/.config/LIVI/config.json') as f:
    cfg = json.load(f)
print(f'  wirelessAaEnabled: {cfg.get("wirelessAaEnabled")}')
print(f'  autoConn: {cfg.get("autoConn")}')
print(f'  lastConnectedAaBtMac: "{cfg.get("lastConnectedAaBtMac")}"')

# 8. Verify all services
print()
print('=== 8. All services ===')
for svc in ['livi.service', 'homephone-sidecar.service', 'hfp-call-monitor.service',
            'wlan0-watchdog.service', 'usb-autosuspend-fix.service']:
    r = subprocess.run(['systemctl', '--user', 'is-active', svc],
                       capture_output=True, text=True, timeout=5)
    status = r.stdout.strip()
    print(f'  {svc}: {status}')
    if status != 'active' and svc != 'usb-autosuspend-fix.service':
        results.append(f'{svc}: {status}')

# 9. Run onAaPresence analyzer
print()
print('=== 9. onAaPresence analyzer ===')
if os.path.exists('/home/raspberry/analyze_aapresence.py'):
    r = subprocess.run(['python3', '/home/raspberry/analyze_aapresence.py'],
                       capture_output=True, text=True, timeout=15)
    # Print last 2000 chars (the important context dumps)
    output = r.stdout
    if len(output) > 3000:
        print(output[:500])
        print('...')
        print(output[-2500:])
    else:
        print(output)
else:
    print('  analyze_aapresence.py not deployed yet')

# 10. Final state
print()
print('=== 10. Final state ===')
r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
print(f'  BT devices: {r.stdout.strip() or "none"}')
r = subprocess.run(['cat', '/sys/module/usbcore/parameters/autosuspend'],
                   capture_output=True, text=True, timeout=5)
print(f'  USB autosuspend: {r.stdout.strip()}')
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                   capture_output=True, text=True, timeout=5)
print(f'  wlan0 power_save: {r.stdout.strip()}')

# Check wlan0 link
r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'link'],
                   capture_output=True, text=True, timeout=5)
for line in r.stdout.split('\n'):
    if 'SSID' in line or 'signal' in line:
        print(f'  {line.strip()}')

print()
print('=== SUMMARY ===')
for r in results:
    print(f'  - {r}')
print()
print('Done. Key items to check:')
print('  1. wlan0-watchdog service is active (will auto-recover network drops)')
print('  2. Rogue BT scripts deleted')
print('  3. mpris-proxy disabled')
print('  4. onAaPresence analyzer output above (for fixing caller ID regex)')
print('  5. Wireless AA disabled until dongle driver is fixed')

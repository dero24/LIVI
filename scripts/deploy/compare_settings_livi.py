#!/usr/bin/env python3
"""Compare our sidecar settings page against LIVI's native settings capabilities."""
import struct, json, re

ASAR = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(ASAR, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    header = json.loads(f.read(vals[3]).decode('utf-8'))
    data_offset = 16 + vals[3]
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

def collect(node, path=''):
    r = []
    if 'files' in node:
        for name, child in node['files'].items():
            full = path + '/' + name
            if 'files' in child: r.extend(collect(child, full))
            else: r.append((full, int(child.get('offset', 0)), int(child.get('size', 0))))
    return r

files = collect(header)
renderer = main = None
for path, offset, size in files:
    if path == '/out/renderer/index.js':
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset); renderer = f.read(size).decode('utf-8', errors='ignore')
    elif path == '/out/main/main.js':
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset); main = f.read(size).decode('utf-8', errors='ignore')

# Strip our overlay so we only look at LIVI's own renderer
idx = renderer.find('// ===== HOME PHONE HUB')
livi_renderer = renderer[:idx] if idx != -1 else renderer
print(f'LIVI renderer (our overlay stripped): {len(livi_renderer)} chars\n')

print('=== 1. DOES LIVI HAVE AUDIO DEVICE SELECTION? ===')
for pat in [r'audioOutputDevice', r'audioInputDevice', r'audioDevicesChanged',
            r'listAudioDevices', r'getAudioDevices', r'audioDeviceSystemDefault']:
    n_r = len(re.findall(pat, livi_renderer)); n_m = len(re.findall(pat, main))
    print(f'  {pat}: renderer={n_r} main={n_m}')

print('\n=== 2. DOES LIVI HAVE BLUETOOTH PAIRING UI? ===')
for pat in [r'bluetoothPairedList', r'forgetDevice', r'btAdapter', r'pairDevice',
            r'discoverable', r'bluetoothScan', r'connectDevice']:
    n_r = len(re.findall(pat, livi_renderer)); n_m = len(re.findall(pat, main))
    print(f'  {pat}: renderer={n_r} main={n_m}')

print('\n=== 3. DOES LIVI HAVE WIFI CLIENT (home network) MANAGEMENT? ===')
# LIVI's wifi is for the AP, not client. Check for client-side wifi.
for pat in [r'wifiScan', r'wifiConnect', r'savedNetworks', r'nmcli', r'wpa_supplicant',
            r'wifiInterface', r'wifiChannel', r'wifiPassword', r'wifiType', r'hostapd']:
    n_r = len(re.findall(pat, livi_renderer)); n_m = len(re.findall(pat, main))
    print(f'  {pat}: renderer={n_r} main={n_m}')

print('\n=== 4. DOES LIVI HAVE SYSTEM INFO / RESTART / LOGS? ===')
for pat in [r'cpuTemp', r'CPU Temp', r'poweroff', r'restart', r'systemInfo', r'uptime']:
    n_r = len(re.findall(pat, livi_renderer)); n_m = len(re.findall(pat, main))
    print(f'  {pat}: renderer={n_r} main={n_m}')

print('\n=== 5. DOES LIVI HAVE BRIGHTNESS / NIGHT MODE UI? ===')
for pat in [r'displayGamma', r'displayContrast', r'displayColorR', r'nightMode',
            r'darkMode', r'appearanceMode', r'brightness']:
    n_r = len(re.findall(pat, livi_renderer)); n_m = len(re.findall(pat, main))
    print(f'  {pat}: renderer={n_r} main={n_m}')

print('\n=== 6. HOW DOES OUR OVERLAY REACH LIVI SETTINGS? ===')
our = renderer[idx:] if idx != -1 else ''
for pat in [r'settings\.get', r'settings\.save', r'window\.app', r'ipc\.settings',
            r'projection\.ipc\.\w+', r'navigateToApp', r'showSettings']:
    hits = re.findall(pat, our)
    print(f'  {pat}: {len(hits)} -> {sorted(set(hits))[:12]}')

print('\n=== 7. WHAT window.app / window.projection METHODS EXIST? ===')
for pat in [r'exposeInMainWorld\([`\'"](\w+)[`\'"]']:
    print(f'  main.js: {sorted(set(re.findall(pat, main)))}')
# preload
for path, offset, size in files:
    if 'preload' in path and path.endswith('.js'):
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset); pre = f.read(size).decode('utf-8', errors='ignore')
        print(f'\n  --- {path} ({len(pre)} chars) ---')
        for m in re.finditer(r'exposeInMainWorld\(\s*[`\'"](\w+)[`\'"]', pre):
            print(f'    exposeInMainWorld: {m.group(1)}')
        # Top-level keys of the exposed objects
        for m in re.finditer(r'(\w+)\s*:\s*(?:\([^)]*\)\s*=>|function|async)', pre):
            print(f'      method: {m.group(1)}')

print('\n=== 8. LIVI SETTINGS ROUTES (full list) ===')
routes = sorted(set(re.findall(r'route:\s*[`\'"]([\w-]+)[`\'"]', livi_renderer)))
print(f'  {routes}')

print('\n=== 9. LIVI SETTINGS labelKeys (what each route configures) ===')
lks = sorted(set(re.findall(r'labelKey:\s*[`\'"]settings\.([\w.]+)[`\'"]', livi_renderer)))
for lk in lks: print(f'  {lk}')

print('\n=== 10. IS THERE A "poweroff"/"restart" IPC WE CAN CALL? ===')
for pat in [r'poweroff', r'shutdown', r'app\.relaunch', r'app\.quit', r'reboot']:
    n_m = len(re.findall(pat, main))
    if n_m:
        i = main.find(pat)
        print(f'  {pat} ({n_m}x): ...{main[max(0,i-80):i+80]}...')

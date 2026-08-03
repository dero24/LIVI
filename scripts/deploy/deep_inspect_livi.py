#!/usr/bin/env python3
"""Deep inspect LIVI's main.js and renderer for ALL features/capabilities."""
import struct, json, re

ASAR = '/home/raspberry/LIVI/extracted/resources/app.asar'

with open(ASAR, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    header = json.loads(f.read(vals[3]).decode('utf-8'))
    data_offset = 16 + vals[3]
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

def collect(node, path=''):
    result = []
    if 'files' in node:
        for name, child in node['files'].items():
            full = path + '/' + name
            if 'files' in child:
                result.extend(collect(child, full))
            else:
                result.append((full, int(child.get('offset', 0)), int(child.get('size', 0))))
    return result

files = collect(header)

# Read main.js and renderer
main_js = None
renderer_js = None
for path, offset, size in files:
    if path == '/out/main/main.js':
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset)
            main_js = f.read(size).decode('utf-8', errors='ignore')
    elif path == '/out/renderer/index.js':
        with open(ASAR, 'rb') as f:
            f.seek(data_offset + offset)
            renderer_js = f.read(size).decode('utf-8', errors='ignore')

print(f'main.js: {len(main_js)} chars')
print(f'renderer.js: {len(renderer_js)} chars')

# 1. Find ALL config keys (the default config object)
print('\n=== ALL CONFIG KEYS (from default config in main.js) ===')
# Look for the config object pattern
config_match = re.search(r'(?:defaultConfig|DEFAULT_CONFIG|getDefaultConfig|configDefaults)\s*[=:]\s*\{([^}]+)\}', main_js)
if config_match:
    print(config_match.group(0)[:3000])
else:
    # Try to find the config object by looking for known keys
    # Search for a block containing multiple known config keys
    for m in re.finditer(r"(\w+):\s*([`'\"][^`'\"]*[`'\"]|\d+|true|false|\[\]|\{\})\s*[,}]", main_js[:50000]):
        key = m.group(1)
        val = m.group(2)
        if key in ['projectionWidth','projectionHeight','carName','wirelessAaEnabled','wifiInterface',
                    'wifiChannel','wifiPassword','btAdapter','darkMode','nightMode','autoConn',
                    'gps','gnssGps','callQuality','samplingFrequency','micType','carType',
                    'displayMode','displayGamma','displayContrast','displayColorR',
                    'audioOutputDevice','audioInputDevice','huVolume','audioVolume',
                    'navVolume','voiceAssistantVolume','callVolume','systemSoundsVolume',
                    'cameraId','cameraMirror','autoSwitchOnReverse',
                    'clusterWidth','clusterHeight','clusterFps',
                    'carPlayMfiI2cBus','carPlayMfiPowerGpio','carPlaySourceVersion',
                    'projectionFps','projectionDpi','projectionViewAreaTop',
                    'wifiType','phoneConfig','evConnectorTypes',
                    'UseBTPhone','disableAudioOutput','dashboardMediaInfo',
                    'dashboardVehicleInfo','dashboardRouteInfo','mediaDelay',
                    'oemName','apkVer','hand','darkMode','nightMode',
                    'startPage','language','appearanceMode',
                    'visualAudioDelayMs','huVolumeLinkSystem',
                    'dongleToolsIp','dongleIcon120','dongleIcon180','dongleIcon256']:
            print(f'  {key}: {val}')

# 2. Find ALL IPC methods exposed to renderer
print('\n=== ALL IPC METHODS (preload bridge) ===')
# Look for ipcMain.handle or contextBridge.exposeInMainWorld patterns
for pattern in [r'ipcMain\.handle\(["`\']([^"`\']+)["`\']',
                r'exposeInMainWorld\(["`\']([^"`\']+)["`\']',
                r'ipcRenderer\.invoke\(["`\']([^"`\']+)["`\']',
                r'ipcRenderer\.send\(["`\']([^"`\']+)["`\']',
                r'ipc\.send\(["`\']([^"`\']+)["`\']',
                r'ipc\.invoke\(["`\']([^"`\']+)["`\']']:
    matches = set(re.findall(pattern, main_js))
    if matches:
        for m in sorted(matches):
            print(f'  {m}')

# 3. Find ALL projection event types
print('\n=== ALL PROJECTION EVENT TYPES ===')
for pattern in [r'type:["`\']([a-zA-Z_-]+)["`\']',
                r'type:\s*["`\']([a-zA-Z_-]+)["`\']',
                r'emitProjectionEvent\(\{type:["`\']([a-zA-Z_-]+)["`\']']:
    matches = set(re.findall(pattern, main_js))
    if matches:
        for m in sorted(matches):
            print(f'  {m}')

# 4. Find ALL command keys (sendCommand)
print('\n=== ALL COMMAND KEYS (sendCommand) ===')
for pattern in [r'CommandMapping\[["`\']([^"`\']+)["`\']',
                r'sendCommand\(["`\']([^"`\']+)["`\']',
                r'command:["`\']([^"`\']+)["`\']']:
    matches = set(re.findall(pattern, main_js + renderer_js))
    if matches:
        for m in sorted(matches):
            print(f'  {m}')

# 5. Find ALL settings page sections/tabs in renderer
print('\n=== SETTINGS PAGE SECTIONS (renderer) ===')
# Look for route/section/tab definitions
for pattern in [r'(?:route|section|tab|page):\s*["`]([^"`]{3,40})["`]',
                r'label:\s*["`]([A-Z][^"`]{2,40})["`]',
                r'labelKey:\s*["`]settings\.([^"`.]+)["`]']:
    matches = set(re.findall(pattern, renderer_js))
    if matches:
        for m in sorted(matches)[:50]:
            print(f'  {m}')

# 6. Find features we might not know about
print('\n=== POTENTIAL HIDDEN FEATURES ===')
feature_keywords = [
    'camera', 'screenshot', 'recording', 'dashcam', 'dvr',
    'voiceAssistant', 'voice', 'siri', 'googleAssistant',
    'gps', 'gnss', 'location', 'latitude', 'longitude',
    'cluster', 'dashboard', 'secondary', 'multiDisplay',
    'nightMode', 'dayMode', 'autoNight',
    'phonebook', 'contacts', 'callLog', 'missedCall',
    'sms', 'message', 'textMessage',
    'notification', 'notif',
    'weather', 'temperature',
    'firmware', 'update', 'ota',
    'diagnostic', 'debug', 'log',
    'keyBinding', 'remoteControl', 'steeringWheel',
    'volume', 'audio', 'equalizer', 'balance', 'fade',
    'brightness', 'backlight', 'dimming',
    'screensaver', 'sleep', 'idle', 'standby',
    'reverse', 'backupCamera', 'rearCamera',
    'ev', 'electric', 'charging',
    'tire', 'pressure', 'obd', 'vehicle',
    'radio', 'fm', 'am', 'dab',
    'wifi', 'bluetooth', 'hotspot', 'tethering',
    'vpn', 'proxy',
    'mirror', 'cast', 'airplay',
    'splitScreen', 'pictureInPicture', 'pip',
    'theme', 'wallpaper', 'skin',
    'language', 'locale', 'i18n',
    'accessibility', 'largeText', 'highContrast',
    'parental', 'lock', 'pin', 'password',
    'guest', 'profile', 'user',
]

for kw in feature_keywords:
    # Check if it appears in meaningful context (not just node_modules)
    count_main = main_js.lower().count(kw.lower())
    count_renderer = renderer_js.lower().count(kw.lower())
    if count_main > 0 or count_renderer > 0:
        # Get context from main.js
        idx = main_js.lower().find(kw.lower())
        if idx >= 0:
            ctx = main_js[max(0,idx-30):idx+50].replace('\n',' ')
            print(f'  [{kw}] main.js({count_main}x): ...{ctx}...')
        idx = renderer_js.lower().find(kw.lower())
        if idx >= 0:
            ctx = renderer_js[max(0,idx-30):idx+50].replace('\n',' ')
            print(f'  [{kw}] renderer({count_renderer}x): ...{ctx}...')

# 7. Find ALL Socket.IO events
print('\n=== SOCKET.IO EVENTS ===')
for pattern in [r'io\.emit\(["`\']([^"`\']+)["`\']',
                r'socket\.emit\(["`\']([^"`\']+)["`\']',
                r'socket\.on\(["`\']([^"`\']+)["`\']',
                r'io\.on\(["`\']([^"`\']+)["`\']']:
    matches = set(re.findall(pattern, main_js))
    if matches:
        for m in sorted(matches):
            print(f'  {m}')

# 8. Find config keys that are NOT in our known list
print('\n=== UNKNOWN CONFIG KEYS (might be new features) ===')
known_keys = {
    'projectionWidth','projectionHeight','projectionFps','projectionDpi',
    'projectionViewAreaTop','projectionViewAreaBottom','projectionViewAreaLeft','projectionViewAreaRight',
    'projectionSafeAreaTop','projectionSafeAreaBottom','projectionSafeAreaLeft','projectionSafeAreaRight',
    'projectionSafeAreaDrawOutside',
    'clusterWidth','clusterHeight','clusterFps','clusterDpi',
    'clusterViewAreaTop','clusterViewAreaBottom','clusterViewAreaLeft','clusterViewAreaRight',
    'clusterSafeAreaTop','clusterSafeAreaBottom','clusterSafeAreaLeft','clusterSafeAreaRight',
    'lastConnectedAaBtMac','lastPhoneWorkMode','apkVer','carName','oemName',
    'darkMode','nightMode','hand','mediaDelay','samplingFrequency','callQuality',
    'autoConn','UseBTPhone','disableAudioOutput',
    'dashboardMediaInfo','dashboardVehicleInfo','dashboardRouteInfo',
    'gps','gnssGps','gnssGlonass','gnssGalileo','gnssBeiDou',
    'wifiType','wifiChannel','micType','phoneConfig','carType',
    'evConnectorTypes','wirelessAaEnabled','wirelessCpEnabled',
    'wifiPassword','btAdapter','wifiInterface',
    'carPlaySourceVersion','carPlayMfiI2cBus','carPlayMfiPowerGpio',
    'appearanceMode','displayMode','displayGamma','displayContrast',
    'displayColorR','displayColorG','displayColorB',
    'startPage','language',
    'kiosk','uiZoomPercent','cameraId','camera','cameraMirror',
    'autoSwitchOnReverse','dongleToolsIp','visualAudioDelayMs',
    'huVolume','huVolumeLinkSystem','audioVolume','navVolume',
    'voiceAssistantVolume','callVolume','systemSoundsVolume',
    'audioOutputDevice','audioOutputDeviceLabel','audioInputDevice','audioInputDeviceLabel',
    'primaryColorDark','highlightColorDark','primaryColorLight','highlightColorLight',
    'backgroundColorDark','backgroundColorLight',
    'mainScreenWidth','mainScreenHeight','dashScreenActive','dashScreenWidth','dashScreenHeight',
    'auxScreenActive','auxScreenWidth','auxScreenHeight',
    'mainScreenBounds','dashScreenBounds','auxScreenBounds',
    'dashboards','media','bindings',
    'dongleIcon120','dongleIcon180','dongleIcon256',
    'dismissedPackages','updateNightly',
}

# Find config-like patterns: key:value where value is a primitive
for m in re.finditer(r"(\w+):\s*(?:[`'\"][^`'\"]{0,60}[`'\"]|\d+|true|false|\[\]|\{[^}]{0,100}\})\s*[,}]", main_js[:80000]):
    key = m.group(1)
    if key not in known_keys and not key.startswith('_') and len(key) > 3 and key[0].islower():
        val = m.group(0).split(':',1)[1].strip().rstrip(',}')
        if len(val) < 80:
            print(f'  {key}: {val}')

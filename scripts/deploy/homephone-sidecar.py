#!/usr/bin/env python3
"""
Home Phone Hub — Ring Detection Sidecar

Listens for HTTP POSTs from Tasker/companion apps on phones.
When a phone rings, plays a ringtone and notifies LIVI via Socket.IO.

Endpoints:
  POST /ring?slot=1&caller=...&phone=...   — phone is ringing
  POST /hangup?slot=1                       — call ended
  POST /notify?slot=1&app=...&title=...    — notification
  GET  /status                              — health check

Integration with LIVI:
  - Connects to LIVI's Socket.IO telemetry server on port 4000
  - Pushes 'telemetry:push' events with ring/notification data
  - The Home UI (patched) listens for these and shows banners

Runs as a systemd user service on port 8123.
"""
import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Socket.IO client
try:
    import socketio
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--break-system-packages', 'python-socketio'])
    import socketio

LIVI_SOCKETIO_URL = 'http://localhost:4000'
RINGTONE_PATH = '/home/raspberry/ringtone.wav'
LISTEN_PORT = 8123
MAX_RING_SECONDS = 30  # Auto-stop ringing after 30s
PHOTOS_DIR = '/home/raspberry/photos'
SCREENSAVER_IDLE_MS = 120000  # 2 minutes before screensaver kicks in

# State
ring_state = {}  # slot -> {caller, phone, started_at}
sio = socketio.Client()
sio_connected = False
weather_cache = {'data': None, 'fetched_at': 0}
WEATHER_CACHE_TTL = 1800  # 30 minutes
WEATHER_LAT = None  # Set via IP geolocation
WEATHER_LON = None

# ===== Companion App State (v0.4 — unified endpoints) =====
# media_state: last media snapshot reported by the Android companion app.
# Overlay prefers this over LIVI readMedia() when fresh (within MEDIA_TTL_SECONDS).
# Shape: {title, artist, album, app, playing, duration_ms, position_ms, source, reported_at}
#   or None when no companion app has reported (or it has gone stale).
media_state = None
media_lock = threading.Lock()
MEDIA_TTL_SECONDS = 15  # companion media is stale after 15s without an update

# notifications: active notifications from Android companion app OR ANCS listener (iPhone).
# Each entry: {id, title, text, app, platform, posted_at}
notifications = []
notif_lock = threading.Lock()
NOTIF_MAX_AGE_SECONDS = 1800  # 30 min — auto-expire stale notifications
NOTIF_MAX_COUNT = 20  # cap to prevent unbounded growth

# dock_state: phones currently docked (reported by companion app / Shortcuts).
# mac -> {name, platform, docked_at}
dock_state = {}
dock_lock = threading.Lock()


def get_location():
    """Get approximate location via IP geolocation."""
    global WEATHER_LAT, WEATHER_LON
    if WEATHER_LAT is not None and WEATHER_LON is not None:
        return
    try:
        req = urllib.request.Request('https://ipapi.co/json/', headers={'User-Agent': 'homephone-hub/1.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        WEATHER_LAT = data.get('latitude')
        WEATHER_LON = data.get('longitude')
        city = data.get('city', 'unknown')
        print(f'[sidecar] Location: {city} ({WEATHER_LAT}, {WEATHER_LON})')
    except Exception as e:
        print(f'[sidecar] IP geolocation failed: {e}, using default')
        WEATHER_LAT = 40.0  # Default: US center
        WEATHER_LON = -100.0


def fetch_weather():
    """Fetch current weather from open-meteo (no API key needed)."""
    global weather_cache
    if time.time() - weather_cache['fetched_at'] < WEATHER_CACHE_TTL and weather_cache['data']:
        return weather_cache['data']

    get_location()
    if WEATHER_LAT is None or WEATHER_LON is None:
        return None

    try:
        url = (f'https://api.open-meteo.com/v1/forecast?latitude={WEATHER_LAT}&longitude={WEATHER_LON}'
               f'&current=temperature_2m,apparent_temperature,weathercode,relative_humidity_2m,wind_speed_10m'
               f'&temperature_unit=fahrenheit&timezone=auto')
        req = urllib.request.Request(url, headers={'User-Agent': 'homephone-hub/1.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        weather_cache = {'data': data, 'fetched_at': time.time()}
        current = data.get('current', {})
        temp = current.get('temperature_2m')
        code = current.get('weathercode')
        print(f'[sidecar] Weather: {temp}°F, code={code}')
        return data
    except Exception as e:
        print(f'[sidecar] Weather fetch failed: {e}')
        return weather_cache.get('data')  # Return stale cache if available


def connect_socketio():
    """Connect to LIVI's Socket.IO telemetry server."""
    global sio_connected
    try:
        sio.connect(LIVI_SOCKETIO_URL, transports=['websocket'])
        sio_connected = True
        print(f'[sidecar] Connected to LIVI Socket.IO at {LIVI_SOCKETIO_URL}')
    except Exception as e:
        print(f'[sidecar] Could not connect to LIVI Socket.IO: {e}')
        print('[sidecar] Will retry in background...')


def push_telemetry(payload):
    """Push a telemetry event to LIVI."""
    global sio_connected
    if not sio_connected:
        try:
            connect_socketio()
        except Exception:
            pass
    if sio_connected:
        try:
            sio.emit('telemetry:push', payload)
            print(f'[sidecar] Pushed telemetry: {payload}')
        except Exception as e:
            print(f'[sidecar] Failed to push telemetry: {e}')
            sio_connected = False


def play_ringtone():
    """Play the ringtone through the default audio output."""
    if not os.path.exists(RINGTONE_PATH):
        print(f'[sidecar] No ringtone at {RINGTONE_PATH}, skipping audio')
        return
    # Use paplay for PipeWire/PulseAudio
    try:
        subprocess.Popen(
            ['paplay', RINGTONE_PATH, '--property=media.role=phone'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print('[sidecar] Playing ringtone')
    except FileNotFoundError:
        # Fallback to aplay
        try:
            subprocess.Popen(
                ['aplay', RINGTONE_PATH],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print('[sidecar] Playing ringtone (aplay)')
        except Exception as e:
            print(f'[sidecar] Could not play ringtone: {e}')


def stop_ringtone():
    """Stop any playing ringtone."""
    try:
        subprocess.run(['pactl', 'close-playback-client', 'ringtone'],
                      capture_output=True, timeout=2)
    except Exception:
        pass
    try:
        subprocess.run(['pkill', '-f', 'paplay.*ringtone'],
                      capture_output=True, timeout=2)
    except Exception:
        pass
    try:
        subprocess.run(['pkill', '-f', 'aplay.*ringtone'],
                      capture_output=True, timeout=2)
    except Exception:
        pass


def handle_ring(slot, caller, phone):
    """Handle an incoming ring event."""
    print(f'[sidecar] RING slot={slot} caller={caller} phone={phone}')
    ring_state[slot] = {
        'caller': caller or 'Unknown',
        'phone': phone or 'Unknown',
        'started_at': time.time()
    }
    play_ringtone()

    # Push telemetry to LIVI for the Home UI
    push_telemetry({
        'type': 'ring',
        'slot': slot,
        'caller': caller or 'Unknown',
        'phone': phone or 'Unknown',
        'timestamp': time.time()
    })

    # Auto-stop after MAX_RING_SECONDS
    def auto_stop():
        time.sleep(MAX_RING_SECONDS)
        if slot in ring_state:
            print(f'[sidecar] Auto-stopping ring for slot {slot} after {MAX_RING_SECONDS}s')
            handle_hangup(slot)

    threading.Thread(target=auto_stop, daemon=True).start()


def handle_hangup(slot):
    """Handle a call end event."""
    if slot in ring_state:
        print(f'[sidecar] HANGUP slot={slot}')
        del ring_state[slot]
    stop_ringtone()
    push_telemetry({
        'type': 'hangup',
        'slot': slot,
        'timestamp': time.time()
    })


def handle_notify(slot, app, title, text):
    """Handle a notification event."""
    print(f'[sidecar] NOTIFY slot={slot} app={app} title={title}')
    push_telemetry({
        'type': 'notification',
        'slot': slot,
        'app': app or 'Unknown',
        'title': title or '',
        'text': text or '',
        'timestamp': time.time()
    })


# ===== Companion App handlers (v0.4 — unified endpoints) =====

def handle_media_post(body):
    """Store media state reported by the Android companion app.

    Body shape (all fields optional except nothing — empty body clears state):
      { title, artist, album, app, playing, duration_ms, position_ms }
    An empty body or {"playing": false, "clear": true} clears the state so the
    overlay falls back to LIVI readMedia().
    """
    global media_state
    if not body or body.get('clear'):
        with media_lock:
            if media_state is not None:
                print('[sidecar] MEDIA cleared (companion)')
            media_state = None
        push_telemetry({'type': 'media-reset', 'source': 'companion', 'timestamp': time.time()})
        return {'status': 'ok', 'media': None}

    with media_lock:
        media_state = {
            'title': body.get('title', ''),
            'artist': body.get('artist', ''),
            'album': body.get('album', ''),
            'app': body.get('app', ''),
            'playing': bool(body.get('playing', False)),
            'duration_ms': body.get('duration_ms'),
            'position_ms': body.get('position_ms'),
            'source': 'companion',
            'reported_at': time.time(),
        }
    print(f'[sidecar] MEDIA {media_state["app"]}: {media_state["title"]} — {media_state["artist"]} (playing={media_state["playing"]})')
    push_telemetry({
        'type': 'media',
        'source': 'companion',
        'payload': {k: v for k, v in media_state.items() if k != 'reported_at'},
        'timestamp': time.time(),
    })
    return {'status': 'ok', 'media': {k: v for k, v in media_state.items() if k != 'reported_at'}}


def get_companion_media():
    """Return fresh companion media state, or None if stale/absent.

    The overlay should call this via /status and prefer it over LIVI readMedia()
    when non-None. Stale = no companion update within MEDIA_TTL_SECONDS.
    """
    with media_lock:
        if media_state is None:
            return None
        age = time.time() - media_state.get('reported_at', 0)
        if age > MEDIA_TTL_SECONDS:
            return None
        return {k: v for k, v in media_state.items() if k != 'reported_at'}


def prune_notifications():
    """Remove expired notifications and enforce the max count. Called under notif_lock."""
    now = time.time()
    # Drop expired
    fresh = [n for n in notifications if (now - n.get('posted_at', 0)) < NOTIF_MAX_AGE_SECONDS]
    # Enforce max count (keep most recent)
    if len(fresh) > NOTIF_MAX_COUNT:
        fresh = sorted(fresh, key=lambda n: n.get('posted_at', 0), reverse=True)[:NOTIF_MAX_COUNT]
    notifications[:] = fresh


def handle_notif_post(body):
    """Add / update / remove / clear notifications from companion app or ANCS.

    Body shapes:
      {"action": "add", "id": "...", "title": "...", "text": "...", "app": "...", "platform": "android|iphone"}
      {"action": "remove", "id": "..."}
      {"action": "clear", "platform": "android"}  (platform optional)
    Default action is "add" for backward compatibility.
    """
    if not body:
        return {'error': 'body required'}, 400

    action = body.get('action', 'add')
    platform = body.get('platform', 'android')

    if action == 'clear':
        with notif_lock:
            if body.get('platform'):
                before = len(notifications)
                notifications[:] = [n for n in notifications if n.get('platform') != platform]
                pruned = before - len(notifications)
            else:
                pruned = len(notifications)
                notifications.clear()
        print(f'[sidecar] NOTIFS cleared ({pruned} removed, platform={platform if body.get("platform") else "all"})')
        push_telemetry({'type': 'notifs-clear', 'platform': platform if body.get('platform') else 'all', 'timestamp': time.time()})
        return {'status': 'ok', 'cleared': pruned}

    if action == 'remove':
        nid = body.get('id')
        if not nid:
            return {'error': 'id required for remove'}, 400
        with notif_lock:
            before = len(notifications)
            notifications[:] = [n for n in notifications if n.get('id') != nid]
            removed = before - len(notifications)
        if removed:
            print(f'[sidecar] NOTIF removed id={nid}')
            push_telemetry({'type': 'notif-remove', 'id': nid, 'timestamp': time.time()})
        return {'status': 'ok', 'removed': removed}

    # action == "add" (default)
    nid = body.get('id') or f'{body.get("app", "unknown")}:{body.get("title", "")}:{int(time.time()*1000)}'
    entry = {
        'id': nid,
        'title': body.get('title', ''),
        'text': body.get('text', ''),
        'app': body.get('app', ''),
        'platform': platform,
        'posted_at': time.time(),
    }
    with notif_lock:
        # Update if same id exists, else append
        for i, n in enumerate(notifications):
            if n.get('id') == nid:
                entry['posted_at'] = n.get('posted_at', entry['posted_at'])
                notifications[i] = entry
                break
        else:
            notifications.append(entry)
        prune_notifications()
        count = len(notifications)
    print(f'[sidecar] NOTIF [{platform}] {entry["app"]}: {entry["title"]} (total={count})')
    push_telemetry({
        'type': 'notif',
        'id': nid,
        'title': entry['title'],
        'text': entry['text'],
        'app': entry['app'],
        'platform': platform,
        'timestamp': entry['posted_at'],
    })
    return {'status': 'ok', 'notification': {k: v for k, v in entry.items()}}


def get_notifications():
    """Return a snapshot of active notifications (newest first)."""
    with notif_lock:
        prune_notifications()
        # Return a copy, newest first
        return sorted(
            [{k: v for k, v in n.items()} for n in notifications],
            key=lambda n: n.get('posted_at', 0),
            reverse=True,
        )


def handle_dock_post(body):
    """Phone docking — record state and trigger BT connect.

    Body: {"mac": "xx:xx:xx:xx", "name": "S22 Ultra", "platform": "android|iphone"}
    """
    if not body or not body.get('mac'):
        return {'error': 'mac required'}, 400
    mac = body['mac']
    name = body.get('name', 'Unknown')
    platform = body.get('platform', 'android')
    with dock_lock:
        dock_state[mac] = {'name': name, 'platform': platform, 'docked_at': time.time()}
    print(f'[sidecar] DOCK {name} ({mac}) platform={platform}')
    # Trigger BT connect (reuses existing helper)
    result = bt_connect(mac)
    push_telemetry({
        'type': 'dock',
        'mac': mac,
        'name': name,
        'platform': platform,
        'bt_result': result,
        'timestamp': time.time(),
    })
    return {'status': 'ok', 'mac': mac, 'name': name, 'bt_result': result}


def handle_undock_post(body):
    """Phone undocking — record state and disconnect BT.

    Body: {"mac": "xx:xx:xx:xx", "platform": "android|iphone"}
    """
    if not body or not body.get('mac'):
        return {'error': 'mac required'}, 400
    mac = body['mac']
    with dock_lock:
        info = dock_state.pop(mac, None)
    name = info.get('name', 'Unknown') if info else 'Unknown'
    platform = body.get('platform', info.get('platform', 'android') if info else 'android')
    print(f'[sidecar] UNDOCK {name} ({mac}) platform={platform}')
    result = bt_disconnect(mac)
    push_telemetry({
        'type': 'undock',
        'mac': mac,
        'name': name,
        'platform': platform,
        'bt_result': result,
        'timestamp': time.time(),
    })
    return {'status': 'ok', 'mac': mac, 'name': name, 'bt_result': result}


def get_dock_state():
    """Return a snapshot of docked phones."""
    with dock_lock:
        return {mac: {k: v for k, v in info.items()} for mac, info in dock_state.items()}


# ===== Settings API helper functions =====

def test_mic(source_name):
    """Record 3 seconds from the given source and play it back."""
    tmp_rec = '/tmp/homehub_mic_test.wav'
    try:
        # Remove old recording if exists
        try:
            os.remove(tmp_rec)
        except OSError:
            pass
        # Record 3 seconds from the specified source using parecord with timeout
        proc = subprocess.Popen(
            ['parecord', '--device=' + source_name, tmp_rec],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if not os.path.exists(tmp_rec) or os.path.getsize(tmp_rec) < 100:
            stderr = proc.stderr.read().decode() if proc.stderr else ''
            return {'status': 'error', 'message': 'Recording failed — ' + stderr[:100] if stderr else 'mic may not be available'}
        # Play it back through the default sink
        subprocess.Popen(
            ['paplay', tmp_rec],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print(f'[sidecar] Mic test: recorded from {source_name}, playing back')
        # Clean up
        def cleanup():
            time.sleep(5)
            try:
                os.remove(tmp_rec)
            except OSError:
                pass
        threading.Thread(target=cleanup, daemon=True).start()
        return {'status': 'ok'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def get_audio_devices():
    """List audio output (sinks) and input (sources) devices via pactl/pipewire."""
    sinks = []
    sources = []
    default_sink = None
    default_source = None
    try:
        r = subprocess.run(['pactl', 'get-default-sink'], capture_output=True, text=True, timeout=5)
        default_sink = r.stdout.strip()
    except Exception:
        pass
    try:
        r = subprocess.run(['pactl', 'get-default-source'], capture_output=True, text=True, timeout=5)
        default_source = r.stdout.strip()
    except Exception:
        pass
    # Parse sinks
    try:
        r = subprocess.run(['pactl', 'list', 'sinks'], capture_output=True, text=True, timeout=5)
        for block in r.stdout.split('\n\n'):
            if 'Sink #' not in block:
                continue
            name = _extract_field(block, 'Name:')
            desc = _extract_field(block, 'Description:')
            driver = _extract_field(block, 'Driver:')
            state = _extract_field(block, 'State:')
            vol_line = _extract_field(block, 'Volume:')
            vol_pct = 0
            if vol_line:
                for part in vol_line.split():
                    if part.endswith('%'):
                        try:
                            vol_pct = int(part.rstrip('%'))
                        except ValueError:
                            pass
            sink_id = block.split('Sink #')[1].split('\n')[0].strip() if 'Sink #' in block else ''
            sinks.append({
                'id': sink_id,
                'name': name,
                'description': desc,
                'driver': driver,
                'state': state,
                'volume': vol_pct,
                'is_default': name == default_sink
            })
    except Exception as e:
        print(f'[sidecar] Error listing sinks: {e}')
    # Parse sources
    try:
        r = subprocess.run(['pactl', 'list', 'sources'], capture_output=True, text=True, timeout=5)
        for block in r.stdout.split('\n\n'):
            if 'Source #' not in block:
                continue
            name = _extract_field(block, 'Name:')
            desc = _extract_field(block, 'Description:')
            driver = _extract_field(block, 'Driver:')
            state = _extract_field(block, 'State:')
            vol_line = _extract_field(block, 'Volume:')
            vol_pct = 0
            if vol_line:
                for part in vol_line.split():
                    if part.endswith('%'):
                        try:
                            vol_pct = int(part.rstrip('%'))
                        except ValueError:
                            pass
            src_id = block.split('Source #')[1].split('\n')[0].strip() if 'Source #' in block else ''
            # Skip monitor sources (they're not real inputs)
            is_monitor = '.monitor' in name
            sources.append({
                'id': src_id,
                'name': name,
                'description': desc,
                'driver': driver,
                'state': state,
                'volume': vol_pct,
                'is_default': name == default_source,
                'is_monitor': is_monitor
            })
    except Exception as e:
        print(f'[sidecar] Error listing sources: {e}')
    return {'sinks': sinks, 'sources': sources, 'default_sink': default_sink, 'default_source': default_source}


def _extract_field(block, field):
    """Extract a field value from a pactl list block."""
    for line in block.split('\n'):
        stripped = line.strip()
        if stripped.startswith(field):
            return stripped[len(field):].strip()
    return ''


def play_test_tone():
    """Play a short 440Hz sine wave test tone on the default sink."""
    # Use ffmpeg to generate a 2-second WAV tone to a temp file, then play it with paplay.
    # This works reliably with PipeWire/PulseAudio and routes to the default sink.
    tmp_wav = '/tmp/homehub_test_tone.wav'
    try:
        # Generate a 2-second 440Hz sine wave WAV file
        subprocess.run(
            ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
             '-ar', '44100', '-ac', '2', tmp_wav],
            capture_output=True, timeout=10
        )
        if not os.path.exists(tmp_wav):
            print('[sidecar] Test tone: ffmpeg did not produce output file')
            return
        # Play it through the default sink via paplay (PipeWire/PulseAudio)
        subprocess.Popen(
            ['paplay', tmp_wav],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print('[sidecar] Playing test tone (440Hz, 2s)')
        # Clean up the temp file after playback finishes
        def cleanup():
            time.sleep(4)
            try:
                os.remove(tmp_wav)
            except OSError:
                pass
        threading.Thread(target=cleanup, daemon=True).start()
    except Exception as e:
        print(f'[sidecar] Test tone failed: {e}')
        # Fallback: speaker-test (generates tone directly via ALSA)
        try:
            subprocess.Popen(
                ['speaker-test', '-t', 'sine', '-f', '440', '-l', '1'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e2:
            print(f'[sidecar] speaker-test fallback also failed: {e2}')


def get_bluetooth_devices():
    """List paired Bluetooth devices and adapter status."""
    devices = []
    adapter = {}
    try:
        r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.strip().split('\n'):
            if line.startswith('Device '):
                parts = line.split(' ', 2)
                if len(parts) >= 3:
                    mac = parts[1]
                    name = parts[2]
                    # Check if connected
                    connected = False
                    try:
                        rc = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=5)
                        connected = 'Connected: yes' in rc.stdout
                    except Exception:
                        pass
                    devices.append({'mac': mac, 'name': name, 'connected': connected})
    except Exception as e:
        print(f'[sidecar] BT devices error: {e}')
    try:
        r = subprocess.run(['bluetoothctl', 'show'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            stripped = line.strip()
            if stripped.startswith('Controller '):
                adapter['address'] = stripped.split()[1]
            elif stripped.startswith('Name:'):
                adapter['name'] = stripped[5:].strip()
            elif stripped.startswith('Alias:'):
                adapter['alias'] = stripped[6:].strip()
            elif stripped.startswith('Powered:'):
                adapter['powered'] = 'yes' in stripped
            elif stripped.startswith('Discoverable:'):
                adapter['discoverable'] = 'yes' in stripped
    except Exception as e:
        print(f'[sidecar] BT adapter error: {e}')
    return {'devices': devices, 'adapter': adapter}


def bt_scan():
    """Scan for Bluetooth devices for 10 seconds."""
    try:
        proc = subprocess.Popen(['bluetoothctl', '--timeout', '10', 'scan', 'on'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait(timeout=15)
        subprocess.run(['bluetoothctl', 'scan', 'off'], capture_output=True, timeout=5)
    except Exception as e:
        print(f'[sidecar] BT scan error: {e}')


def bt_pair(mac):
    """Pair a Bluetooth device."""
    try:
        r = subprocess.run(['bluetoothctl', 'pair', mac], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 or 'Pairing successful' in (r.stdout + r.stderr):
            return {'status': 'ok', 'mac': mac}
        return {'status': 'error', 'mac': mac, 'message': (r.stdout + r.stderr).strip()[-200:]}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'mac': mac, 'message': 'Pairing timed out'}
    except Exception as e:
        return {'status': 'error', 'mac': mac, 'message': str(e)}


def bt_connect(mac):
    """Connect a paired Bluetooth device."""
    try:
        r = subprocess.run(['bluetoothctl', 'connect', mac], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 or 'Connection successful' in (r.stdout + r.stderr):
            return {'status': 'ok', 'mac': mac}
        return {'status': 'error', 'mac': mac, 'message': (r.stdout + r.stderr).strip()[-200:]}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'mac': mac, 'message': 'Connection timed out'}
    except Exception as e:
        return {'status': 'error', 'mac': mac, 'message': str(e)}


def bt_disconnect(mac):
    """Disconnect a Bluetooth device."""
    try:
        subprocess.run(['bluetoothctl', 'disconnect', mac], capture_output=True, text=True, timeout=10)
        return {'status': 'ok', 'mac': mac}
    except Exception as e:
        return {'status': 'error', 'mac': mac, 'message': str(e)}


def bt_remove(mac):
    """Remove a paired Bluetooth device."""
    try:
        subprocess.run(['bluetoothctl', 'remove', mac], capture_output=True, text=True, timeout=10)
        return {'status': 'ok', 'mac': mac}
    except Exception as e:
        return {'status': 'error', 'mac': mac, 'message': str(e)}


# ===== WiFi helper functions =====

def get_wifi_status():
    """Get current WiFi connection status."""
    info = {'connected': False, 'ssid': None, 'signal': None, 'ip': None,
            'mac': None, 'device': None, 'saved_networks': []}
    try:
        r = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SIGNAL,DEVICE,SSID', 'dev', 'wifi', 'list'],
                          capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split(':', 3)
            if len(parts) >= 4 and parts[0] == 'yes':
                info['connected'] = True
                info['signal'] = int(parts[1]) if parts[1].isdigit() else None
                info['device'] = parts[2]
                info['ssid'] = parts[3]
                break
    except Exception as e:
        print(f'[sidecar] WiFi status error: {e}')
    # Get IP address
    try:
        r = subprocess.run(['nmcli', '-t', '-f', 'IP4.ADDRESS', 'dev', 'show', info.get('device') or 'wlan0'],
                          capture_output=True, text=True, timeout=5)
        ip_line = r.stdout.strip()
        if ip_line:
            info['ip'] = ip_line.split(':')[1] if ':' in ip_line else ip_line
    except Exception:
        pass
    # Get MAC address
    try:
        r = subprocess.run(['nmcli', '-t', '-f', 'GENERAL.HWADDR', 'dev', 'show', info.get('device') or 'wlan0'],
                          capture_output=True, text=True, timeout=5)
        mac_line = r.stdout.strip()
        if mac_line:
            # Format: GENERAL.HWADDR:XX:XX:XX:XX:XX:XX — split on first : only
            info['mac'] = mac_line.split(':', 1)[1] if ':' in mac_line else mac_line
    except Exception:
        pass
    # List saved networks
    try:
        r = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show'],
                          capture_output=True, text=True, timeout=5)
        for line in r.stdout.strip().split('\n'):
            # NAME may contain colons, so split from the right (TYPE and DEVICE don't)
            parts = line.rsplit(':', 2)
            if len(parts) >= 3 and parts[1] in ('wifi', '802-11-wireless'):
                info['saved_networks'].append({
                    'name': parts[0],
                    'active': parts[2] != '--'
                })
    except Exception:
        pass
    return info


def get_wifi_scan():
    """Scan for available WiFi networks."""
    networks = []
    try:
        # Force a rescan
        subprocess.run(['nmcli', 'dev', 'wifi', 'rescan'], capture_output=True, text=True, timeout=10)
        # Put SSID last so colons in SSID don't break parsing
        r = subprocess.run(['nmcli', '-t', '-f', 'IN-USE,SIGNAL,SECURITY,FREQ,SSID', 'dev', 'wifi', 'list'],
                          capture_output=True, text=True, timeout=15)
        seen = set()
        for line in r.stdout.strip().split('\n'):
            if not line:
                continue
            # IN-USE is first char: '*' (in use), ' ' (not in use), or empty
            in_use = line.startswith('*')
            # Remove first char (the IN-USE field) and the following ':'
            if len(line) > 1 and line[1] == ':':
                line = line[2:]
            else:
                line = line[1:] if line else ''
            # Now split: SIGNAL:SECURITY:FREQ:SSID (SSID may contain colons)
            parts = line.split(':', 3)
            if len(parts) < 4:
                continue
            signal = int(parts[0]) if parts[0].isdigit() else 0
            security = parts[1] if parts[1] else 'Open'
            freq = parts[2]
            ssid = parts[3]
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append({
                'ssid': ssid,
                'signal': signal,
                'security': security,
                'freq': freq,
                'in_use': in_use
            })
        # Sort by signal strength (descending)
        networks.sort(key=lambda n: n['signal'], reverse=True)
    except Exception as e:
        print(f'[sidecar] WiFi scan error: {e}')
    return {'networks': networks}


def wifi_connect(ssid, password):
    """Connect to a WiFi network."""
    try:
        cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
        if password:
            cmd.extend(['password', password])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return {'status': 'ok', 'ssid': ssid}
        return {'status': 'error', 'ssid': ssid, 'message': r.stderr.strip()[-200:] or r.stdout.strip()[-200:]}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'ssid': ssid, 'message': 'Connection timed out'}
    except Exception as e:
        return {'status': 'error', 'ssid': ssid, 'message': str(e)}


def wifi_disconnect():
    """Disconnect from current WiFi."""
    try:
        r = subprocess.run(['nmcli', 'dev', 'disconnect', 'wlan0'],
                          capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return {'status': 'ok'}
        return {'status': 'error', 'message': r.stderr.strip()[-200:]}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def wifi_forget(name):
    """Delete a saved WiFi connection."""
    try:
        r = subprocess.run(['nmcli', 'connection', 'delete', name],
                          capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return {'status': 'ok', 'name': name}
        return {'status': 'error', 'name': name, 'message': r.stderr.strip()[-200:]}
    except Exception as e:
        return {'status': 'error', 'name': name, 'message': str(e)}


def get_system_info():
    """Get Pi system info: temperature, RAM, uptime, disk."""
    info = {}
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            info['temp_c'] = int(f.read().strip()) / 1000.0
    except Exception:
        info['temp_c'] = None
    try:
        with open('/proc/meminfo') as f:
            mem = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(':')] = int(parts[1])
            total = mem.get('MemTotal', 0)
            avail = mem.get('MemAvailable', 0)
            info['ram_total_mb'] = total // 1024
            info['ram_used_mb'] = (total - avail) // 1024
            info['ram_avail_mb'] = avail // 1024
    except Exception:
        pass
    try:
        with open('/proc/uptime') as f:
            uptime_s = float(f.read().split()[0])
            info['uptime_hours'] = round(uptime_s / 3600, 1)
    except Exception:
        pass
    try:
        r = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split('\n')
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                info['disk_total'] = parts[1]
                info['disk_used'] = parts[2]
                info['disk_avail'] = parts[3]
                info['disk_pct'] = parts[4]
    except Exception:
        pass
    try:
        r = subprocess.run(['systemctl', '--user', 'is-active', 'livi.service'], capture_output=True, text=True, timeout=5)
        info['livi_status'] = r.stdout.strip()
    except Exception:
        info['livi_status'] = 'unknown'
    try:
        r = subprocess.run(['systemctl', '--user', 'is-active', 'homephone-sidecar.service'], capture_output=True, text=True, timeout=5)
        info['sidecar_status'] = r.stdout.strip()
    except Exception:
        info['sidecar_status'] = 'unknown'
    return info


def get_livi_logs(count=50):
    """Get recent LIVI logs."""
    try:
        r = subprocess.run(['journalctl', '--user', '-u', 'livi.service', '-n', str(count), '--no-pager'],
                          capture_output=True, text=True, timeout=10)
        return {'logs': r.stdout}
    except Exception as e:
        return {'logs': f'Error: {e}'}


def restart_livi():
    """Restart LIVI service."""
    time.sleep(1)
    subprocess.run(['systemctl', '--user', 'restart', 'livi.service'], capture_output=True, timeout=15)


class RingHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def _set_cors_headers(self):
        """Set CORS and CORP headers so LIVI's renderer can fetch from us despite COEP."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cross-Origin-Resource-Policy', 'cross-origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, html, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(html.encode())

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode('utf-8')
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return urllib.parse.parse_qs(body)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/status':
            self._send_json({
                'status': 'ok',
                'ringing': ring_state,
                'livi_connected': sio_connected,
                # v0.4 — companion app / ANCS fields
                'media': get_companion_media(),  # None when stale/absent → overlay falls back to LIVI
                'notifications': get_notifications(),  # newest first
                'dock': get_dock_state(),
            })
        elif parsed.path == '/weather':
            weather = fetch_weather()
            if weather:
                self._send_json(weather)
            else:
                self._send_json({'error': 'weather unavailable'})
        elif parsed.path == '/photos':
            # List available photos
            photos = []
            if os.path.isdir(PHOTOS_DIR):
                for f in sorted(os.listdir(PHOTOS_DIR)):
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
                        photos.append(f)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'photos': photos}).encode())
        elif parsed.path.startswith('/photo/'):
            # Serve a specific photo file
            filename = urllib.parse.unquote(parsed.path[7:])  # Remove '/photo/'
            # Prevent path traversal
            filename = os.path.basename(filename)
            filepath = os.path.join(PHOTOS_DIR, filename)
            if os.path.isfile(filepath) and filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
                try:
                    with open(filepath, 'rb') as f:
                        data = f.read()
                    content_type = 'image/jpeg'
                    if filename.lower().endswith('.png'):
                        content_type = 'image/png'
                    elif filename.lower().endswith('.gif'):
                        content_type = 'image/gif'
                    elif filename.lower().endswith('.webp'):
                        content_type = 'image/webp'
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(data)))
                    self._set_cors_headers()
                    self.send_header('Cache-Control', 'public, max-age=3600')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        elif parsed.path == '/settings':
            self._send_html(SETTINGS_PAGE_HTML)
        elif parsed.path == '/api/audio/devices':
            self._send_json(get_audio_devices())
        elif parsed.path == '/api/bluetooth/devices':
            self._send_json(get_bluetooth_devices())
        elif parsed.path == '/api/bluetooth/scan':
            # Start scanning in background
            threading.Thread(target=bt_scan, daemon=True).start()
            self._send_json({'status': 'scanning'})
        elif parsed.path == '/api/system/info':
            self._send_json(get_system_info())
        elif parsed.path == '/api/system/logs':
            count = int(urllib.parse.parse_qs(parsed.query).get('count', ['50'])[0])
            self._send_json(get_livi_logs(count))
        elif parsed.path == '/api/wifi/status':
            self._send_json(get_wifi_status())
        elif parsed.path == '/api/wifi/scan':
            self._send_json(get_wifi_scan())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        slot = int(params.get('slot', ['1'])[0])

        if parsed.path == '/ring':
            caller = params.get('caller', [None])[0]
            phone = params.get('phone', [None])[0]
            handle_ring(slot, caller, phone)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ringing', 'slot': slot}).encode())

        elif parsed.path == '/hangup':
            handle_hangup(slot)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'hungup', 'slot': slot}).encode())

        elif parsed.path == '/notify':
            app = params.get('app', [None])[0]
            title = params.get('title', [None])[0]
            text = params.get('text', [None])[0]
            handle_notify(slot, app, title, text)
            self._send_json({'status': 'notified', 'slot': slot})

        # ===== v0.4 — Companion App / ANCS unified endpoints =====
        elif parsed.path == '/media':
            # Companion app (Android) reports media state.
            # Body: { title, artist, album, app, playing, duration_ms, position_ms }
            # Empty body or {"clear": true} clears companion media (fall back to LIVI).
            body = self._read_body()
            self._send_json(handle_media_post(body))

        elif parsed.path == '/notifs':
            # Companion app (Android) OR ANCS listener (iPhone) reports notifications.
            # Body: { action: "add"|"remove"|"clear", id, title, text, app, platform }
            body = self._read_body()
            ret = handle_notif_post(body)
            if isinstance(ret, tuple):
                result, code = ret
            else:
                result, code = ret, 200
            self._send_json(result, code)

        elif parsed.path == '/dock':
            # Companion app (Android) OR Shortcuts (iPhone) says "dock".
            # Body: { mac, name, platform }
            body = self._read_body()
            ret = handle_dock_post(body)
            if isinstance(ret, tuple):
                result, code = ret
            else:
                result, code = ret, 200
            self._send_json(result, code)

        elif parsed.path == '/undock':
            # Phone undocked.
            # Body: { mac, platform }
            body = self._read_body()
            ret = handle_undock_post(body)
            if isinstance(ret, tuple):
                result, code = ret
            else:
                result, code = ret, 200
            self._send_json(result, code)

        elif parsed.path == '/api/dom-dump':
            # Diagnostic: receive DOM dump from overlay and write to file
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8') if length else ''
            try:
                with open('/tmp/homehub_dom_dump.txt', 'w') as f:
                    f.write(body)
            except Exception as e:
                print(f'[sidecar] DOM dump write error: {e}')
            self._send_json({'status': 'ok'})

        # ===== Settings API =====
        elif parsed.path == '/api/audio/default':
            body = self._read_body()
            sink = body.get('sink')
            if sink:
                subprocess.run(['pactl', 'set-default-sink', sink], capture_output=True, timeout=5)
                self._send_json({'status': 'ok', 'default_sink': sink})
            else:
                self._send_json({'error': 'sink required'}, 400)

        elif parsed.path == '/api/audio/volume':
            body = self._read_body()
            sink = body.get('sink', '@DEFAULT_SINK@')
            vol = body.get('volume')
            if vol is not None:
                subprocess.run(['pactl', 'set-sink-volume', sink, str(int(vol)) + '%'], capture_output=True, timeout=5)
                self._send_json({'status': 'ok', 'volume': int(vol)})
            else:
                self._send_json({'error': 'volume required'}, 400)

        elif parsed.path == '/api/audio/test':
            threading.Thread(target=play_test_tone, daemon=True).start()
            self._send_json({'status': 'playing test tone'})

        elif parsed.path == '/api/audio/test-mic':
            body = self._read_body()
            source = body.get('source')
            if source:
                # Run in background so the HTTP response is immediate
                threading.Thread(target=test_mic, args=(source,), daemon=True).start()
                self._send_json({'status': 'recording 3 seconds, will play back automatically'})
            else:
                self._send_json({'error': 'source required'}, 400)

        elif parsed.path == '/api/bluetooth/pair':
            body = self._read_body()
            mac = body.get('mac')
            if mac:
                result = bt_pair(mac)
                self._send_json(result, 200 if result.get('status') == 'ok' else 400)
            else:
                self._send_json({'error': 'mac required'}, 400)

        elif parsed.path == '/api/bluetooth/connect':
            body = self._read_body()
            mac = body.get('mac')
            if mac:
                result = bt_connect(mac)
                self._send_json(result, 200 if result.get('status') == 'ok' else 400)
            else:
                self._send_json({'error': 'mac required'}, 400)

        elif parsed.path == '/api/bluetooth/disconnect':
            body = self._read_body()
            mac = body.get('mac')
            if mac:
                result = bt_disconnect(mac)
                self._send_json(result)
            else:
                self._send_json({'error': 'mac required'}, 400)

        elif parsed.path == '/api/bluetooth/remove':
            body = self._read_body()
            mac = body.get('mac')
            if mac:
                result = bt_remove(mac)
                self._send_json(result)
            else:
                self._send_json({'error': 'mac required'}, 400)

        elif parsed.path == '/api/bluetooth/discoverable':
            body = self._read_body()
            on = body.get('on', True)
            subprocess.run(['bluetoothctl', 'discoverable', 'on' if on else 'off'], capture_output=True, timeout=5)
            self._send_json({'status': 'ok', 'discoverable': bool(on)})

        elif parsed.path == '/api/system/restart-livi':
            threading.Thread(target=restart_livi, daemon=True).start()
            self._send_json({'status': 'restarting LIVI'})

        elif parsed.path == '/api/system/restart-sidecar':
            threading.Thread(target=lambda: (time.sleep(1), os.kill(os.getpid(), signal.SIGTERM)), daemon=True).start()
            self._send_json({'status': 'restarting sidecar'})

        elif parsed.path == '/api/wifi/connect':
            body = self._read_body()
            ssid = body.get('ssid')
            password = body.get('password', '')
            if ssid:
                result = wifi_connect(ssid, password)
                self._send_json(result, 200 if result.get('status') == 'ok' else 400)
            else:
                self._send_json({'error': 'ssid required'}, 400)

        elif parsed.path == '/api/wifi/disconnect':
            result = wifi_disconnect()
            self._send_json(result, 200 if result.get('status') == 'ok' else 400)

        elif parsed.path == '/api/wifi/forget':
            body = self._read_body()
            name = body.get('name')
            if name:
                result = wifi_forget(name)
                self._send_json(result)
            else:
                self._send_json({'error': 'name required'}, 400)

        else:
            self.send_response(404)
            self.end_headers()


# ===== Settings Page HTML =====
SETTINGS_PAGE_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Settings</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow: hidden; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, system-ui, sans-serif;
    background: linear-gradient(180deg, #0a0e14 0%, #0d1117 100%);
    color: #e6edf3;
    -webkit-user-select: none; user-select: none;
  }
  .app { display: flex; flex-direction: column; height: 100vh; max-width: 720px; margin: 0 auto; }

  /* Header */
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 20px 28px 16px; flex-shrink: 0;
  }
  .header-title { font-size: 22px; font-weight: 300; letter-spacing: -0.5px; color: #f0f6fc; }
  .header-back {
    width: 40px; height: 40px; border-radius: 12px; border: 1px solid #21262d;
    background: #161b22; color: #8b949e; font-size: 20px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; transition: all 0.15s;
  }
  .header-back:hover { background: #21262d; color: #e6edf3; }
  .header-back:active { transform: scale(0.93); }

  /* Tab bar */
  .tabs {
    display: flex; gap: 0; padding: 0 16px; flex-shrink: 0;
    border-bottom: 1px solid #1a1f2e;
  }
  .tab {
    flex: 1; padding: 14px 8px; cursor: pointer; border: none; background: none;
    color: #484f58; font-size: 14px; font-weight: 500; text-align: center;
    border-bottom: 2px solid transparent; transition: all 0.2s;
    display: flex; flex-direction: column; align-items: center; gap: 4px;
  }
  .tab svg { width: 22px; height: 22px; opacity: 0.6; transition: opacity 0.2s; }
  .tab:hover { color: #8b949e; }
  .tab:hover svg { opacity: 0.8; }
  .tab.active { color: #58a6ff; border-bottom-color: #58a6ff; }
  .tab.active svg { opacity: 1; }

  /* Tab panels — only the active panel is visible */
  .panel { display: none; }
  .panel.active { display: block; }

  /* Scroll area */
  .content { flex: 1; overflow-y: auto; padding: 20px 28px 120px; -webkit-overflow-scrolling: touch; }
  .content::-webkit-scrollbar { width: 4px; }
  .content::-webkit-scrollbar-track { background: transparent; }
  .content::-webkit-scrollbar-thumb { background: #21262d; border-radius: 2px; }

  /* Cards */
  .card {
    background: rgba(22,27,34,0.8); border: 1px solid #1a1f2e; border-radius: 16px;
    padding: 20px; margin-bottom: 14px; backdrop-filter: blur(10px);
  }
  .card-title {
    font-size: 13px; font-weight: 600; color: #8b949e; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 14px;
  }

  /* Device rows */
  .device-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 0; border-bottom: 1px solid rgba(33,38,45,0.5);
  }
  .device-row:last-child { border-bottom: none; }
  .device-info { flex: 1; min-width: 0; }
  .device-name { font-size: 16px; color: #e6edf3; font-weight: 400; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
  .device-sub { font-size: 13px; color: #6e7681; margin-top: 3px; }

  /* Badges */
  .badge { font-size: 11px; padding: 3px 10px; border-radius: 10px; font-weight: 600; white-space: nowrap; }
  .b-default { background: rgba(191,135,0,0.2); color: #d29922; border: 1px solid rgba(191,135,0,0.3); }
  .b-connected { background: rgba(31,111,235,0.2); color: #58a6ff; border: 1px solid rgba(31,111,235,0.3); }
  .b-disconnected { background: rgba(110,118,129,0.15); color: #6e7681; border: 1px solid rgba(110,118,129,0.2); }
  .b-on { background: rgba(26,127,55,0.2); color: #3fb950; border: 1px solid rgba(26,127,55,0.3); }
  .b-off { background: rgba(110,118,129,0.15); color: #6e7681; border: 1px solid rgba(110,118,129,0.2); }
  .b-secure { background: rgba(110,118,129,0.15); color: #6e7681; border: 1px solid rgba(110,118,129,0.2); }
  .b-open { background: rgba(26,127,55,0.15); color: #3fb950; border: 1px solid rgba(26,127,55,0.2); }

  /* Buttons */
  .btn {
    padding: 10px 18px; border: 1px solid #21262d; border-radius: 10px;
    background: #161b22; color: #e6edf3; font-size: 14px; font-weight: 500;
    cursor: pointer; transition: all 0.15s; white-space: nowrap;
  }
  .btn:hover { background: #21262d; }
  .btn:active { transform: scale(0.96); }
  .btn-primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  .btn-primary:hover { background: #388bfd; }
  .btn-danger { background: rgba(218,54,51,0.15); border-color: rgba(218,54,51,0.3); color: #f85149; }
  .btn-danger:hover { background: rgba(218,54,51,0.25); }
  .btn-sm { padding: 8px 14px; font-size: 13px; }
  .btn-row { display: flex; gap: 8px; flex-wrap: wrap; }

  /* Signal bars */
  .signal { display: inline-flex; align-items: flex-end; gap: 2px; }
  .signal span { width: 4px; border-radius: 1px; }

  /* Volume slider */
  .slider-row { display: flex; align-items: center; gap: 14px; }
  .slider-row label { font-size: 14px; color: #8b949e; min-width: 100px; }
  input[type="range"] {
    flex: 1; height: 6px; -webkit-appearance: none; appearance: none;
    background: #21262d; border-radius: 3px; outline: none;
  }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none; width: 24px; height: 24px;
    background: #58a6ff; border-radius: 50%; cursor: pointer;
    box-shadow: 0 0 10px rgba(88,166,255,0.3);
  }
  .vol-value { min-width: 50px; text-align: right; font-size: 15px; color: #e6edf3; font-weight: 500; }

  /* Text inputs */
  .input-row { display: flex; gap: 8px; margin-top: 14px; }
  .input-row input {
    flex: 1; padding: 12px 16px; background: #0d1117; border: 1px solid #21262d;
    border-radius: 10px; color: #e6edf3; font-size: 16px; outline: none; transition: border-color 0.2s;
  }
  .input-row input:focus { border-color: #58a6ff; }
  .input-row input::placeholder { color: #484f58; }

  /* Info grid */
  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .info-item { background: #0d1117; border: 1px solid #1a1f2e; border-radius: 12px; padding: 14px; }
  .info-label { font-size: 11px; color: #6e7681; text-transform: uppercase; letter-spacing: 0.8px; }
  .info-value { font-size: 22px; font-weight: 400; color: #e6edf3; margin-top: 4px; }

  /* Log box */
  .log-box {
    background: #0d1117; border: 1px solid #1a1f2e; border-radius: 10px; padding: 14px;
    max-height: 300px; overflow-y: auto; font-family: 'SF Mono', Consolas, monospace;
    font-size: 12px; line-height: 1.6; white-space: pre-wrap; color: #6e7681;
  }

  /* Toast */
  .toast {
    position: fixed; bottom: 100px; left: 50%; transform: translateX(-50%);
    padding: 14px 24px; border-radius: 12px; font-size: 15px; z-index: 10000;
    opacity: 0; transition: opacity 0.3s, transform 0.3s; pointer-events: none;
    backdrop-filter: blur(10px);
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(-10px); }
  .toast-success { background: rgba(26,127,55,0.9); color: #fff; }
  .toast-error { background: rgba(218,54,51,0.9); color: #fff; }

  /* Spinner */
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #21262d; border-top-color: #58a6ff; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty-state { text-align: center; padding: 32px 20px; color: #484f58; font-size: 15px; line-height: 1.6; }
  .hint { font-size: 14px; color: #6e7681; margin-bottom: 14px; line-height: 1.5; }

  /* On-screen keyboard */
  .keyboard {
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 10001;
    background: rgba(13,17,23,0.95); backdrop-filter: blur(20px);
    border-top: 1px solid #21262d; padding: 8px 4px 12px;
    display: none; flex-direction: column; gap: 6px;
    max-width: 720px; margin: 0 auto;
  }
  .keyboard.show { display: flex; }
  .kb-row { display: flex; justify-content: center; gap: 4px; }
  .kb-key {
    min-width: 32px; height: 44px; border: 1px solid #21262d; border-radius: 8px;
    background: #161b22; color: #e6edf3; font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; transition: all 0.1s;
    flex: 1; max-width: 48px;
  }
  .kb-key:active { background: #58a6ff; color: #fff; transform: scale(0.92); }
  .kb-key.wide { max-width: 80px; flex: 2; }
  .kb-key.extra-wide { max-width: 120px; flex: 4; }
  .kb-key.special { background: #21262d; font-size: 14px; }
  .kb-space { flex: 6; max-width: 200px; }
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="header-title">Settings</div>
    <button class="header-back" onclick="goBack()">&#x2190;</button>
  </div>

  <div class="tabs">
    <button class="tab active" data-tab="audio" onclick="showTab('audio', this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 10v4M7 6v12M11 3v18M15 8v8M19 5v14"/></svg>
      Audio
    </button>
    <button class="tab" data-tab="bluetooth" onclick="showTab('bluetooth', this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 7l10 10-5 5V2l5 5L7 17"/></svg>
      Bluetooth
    </button>
    <button class="tab" data-tab="wifi" onclick="showTab('wifi', this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0 1 14 0M8.5 16.05a6 6 0 0 1 7 0M2 8.82a15 15 0 0 1 20 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/></svg>
      WiFi
    </button>
    <button class="tab" data-tab="system" onclick="showTab('system', this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 10v6m11-11h-6M7 12H1m17.4-7.4l-4.2 4.2M9.8 14.2l-4.2 4.2m12.8 0l-4.2-4.2M9.8 9.8L5.6 5.6"/></svg>
      System
    </button>
  </div>

  <div class="content">
    <!-- Audio Tab -->
    <div id="tab-audio" class="panel active">
      <div class="card">
        <div class="card-title">Audio Output</div>
        <div id="audio-sinks"><div class="empty-state">Loading...</div></div>
      </div>
      <div class="card">
        <div class="card-title">Volume</div>
        <div class="slider-row">
          <label>Output</label>
          <input type="range" id="vol-slider" min="0" max="150" value="100" oninput="updateVolLabel(this.value)">
          <span class="vol-value" id="vol-label">100%</span>
        </div>
        <div style="margin-top:16px">
          <button class="btn btn-primary" onclick="testTone()">Play Test Tone</button>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Microphone</div>
        <div id="audio-sources"><div class="empty-state">Loading...</div></div>
      </div>
    </div>

    <!-- Bluetooth Tab -->
    <div id="tab-bluetooth" class="panel">
      <div class="card">
        <div class="card-title">Adapter</div>
        <div id="bt-adapter" class="device-sub" style="margin-bottom:14px">Loading...</div>
        <div class="btn-row">
          <button class="btn btn-sm" onclick="btToggleDiscoverable(true)">Make Discoverable</button>
          <button class="btn btn-sm" onclick="btToggleDiscoverable(false)">Hide</button>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Paired Devices</div>
        <div id="bt-devices"><div class="empty-state">Loading...</div></div>
      </div>
      <div class="card">
        <div class="card-title">Pair New Device</div>
        <div class="hint">Put your device in pairing mode, then scan or enter its MAC address.</div>
        <div class="btn-row" style="margin-bottom:14px">
          <button class="btn btn-primary" onclick="btScan()" id="scan-btn">Scan for Devices (10s)</button>
        </div>
        <div class="input-row">
          <input type="text" id="mac-input" placeholder="XX:XX:XX:XX:XX:XX" data-kb="mac">
          <button class="btn btn-primary" onclick="btPairManual()">Pair</button>
        </div>
        <div id="scan-status" style="margin-top:12px;font-size:13px;color:#6e7681"></div>
      </div>
    </div>

    <!-- WiFi Tab -->
    <div id="tab-wifi" class="panel">
      <div class="card">
        <div class="card-title">Current Connection</div>
        <div id="wifi-status"><div class="empty-state">Loading...</div></div>
      </div>
      <div class="card">
        <div class="card-title">Saved Networks</div>
        <div id="wifi-saved"><div class="empty-state">Loading...</div></div>
      </div>
      <div class="card">
        <div class="card-title">Available Networks</div>
        <div class="btn-row" style="margin-bottom:14px">
          <button class="btn btn-primary" onclick="wifiScan()" id="wifi-scan-btn">Scan for Networks</button>
        </div>
        <div id="wifi-networks"><div class="empty-state">Tap "Scan for Networks" to see nearby WiFi.</div></div>
      </div>
      <div class="card" id="wifi-connect-card" style="display:none">
        <div class="card-title">Connect to Network</div>
        <div id="wifi-connect-ssid" style="font-size:16px;font-weight:500;margin-bottom:14px"></div>
        <div class="input-row">
          <input type="password" id="wifi-password" placeholder="Password (leave empty if open)" data-kb="text">
          <button class="btn btn-primary" onclick="wifiDoConnect()">Connect</button>
        </div>
        <div id="wifi-connect-status" style="margin-top:12px;font-size:13px;color:#6e7681"></div>
      </div>
    </div>

    <!-- System Tab -->
    <div id="tab-system" class="panel">
      <div class="card">
        <div class="card-title">System Info</div>
        <div id="sys-info" class="info-grid"><div class="empty-state">Loading...</div></div>
      </div>
      <div class="card">
        <div class="card-title">Services</div>
        <div class="btn-row">
          <button class="btn btn-primary" onclick="restartLivi()">Restart Display</button>
          <button class="btn" onclick="loadLogs()">View Logs</button>
        </div>
      </div>
      <div class="card" id="logs-card" style="display:none">
        <div class="card-title">Logs (last 50 lines)</div>
        <div class="log-box" id="log-box">Loading...</div>
      </div>
    </div>
  </div>
</div>

<!-- On-screen keyboard -->
<div class="keyboard" id="keyboard">
  <div class="kb-row" id="kb-row-1"></div>
  <div class="kb-row" id="kb-row-2"></div>
  <div class="kb-row" id="kb-row-3"></div>
  <div class="kb-row" id="kb-row-4"></div>
</div>

<div class="toast" id="toast"></div>

<script>
// ===== Tab switching =====
function showTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'audio') loadAudio();
  if (name === 'bluetooth') loadBluetooth();
  if (name === 'wifi') loadWifi();
  if (name === 'system') loadSystem();
  hideKeyboard();
}

function goBack() {
  // If we're in an iframe (loaded from the hub overlay), tell parent to close
  if (window.parent && window.parent !== window) {
    window.parent.postMessage('close-settings', '*');
  } else {
    history.back();
  }
}

function toast(msg, type) {
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show toast-' + (type || 'success');
  setTimeout(function() { el.classList.remove('show'); }, 3000);
}

async function api(path, method, body) {
  // Use XHR (not fetch) — fetch() can hang under LIVI's COEP restrictions.
  // XHR is the same mechanism the overlay uses for weather/ring polling.
  return new Promise(function(resolve, reject) {
    var x = new XMLHttpRequest();
    x.open(method || 'GET', path, true);
    x.timeout = 10000;
    x.setRequestHeader('Content-Type', 'application/json');
    x.onreadystatechange = function() {
      if (x.readyState !== 4) return;
      if (x.status >= 200 && x.status < 300) {
        try { resolve(JSON.parse(x.responseText)); }
        catch(e) { resolve({}); }
      } else {
        resolve({ status: 'error', message: 'HTTP ' + x.status });
      }
    };
    x.onerror = function() { resolve({ status: 'error', message: 'network error' }); };
    x.ontimeout = function() { resolve({ status: 'error', message: 'timeout' }); };
    x.send(body ? JSON.stringify(body) : null);
  });
}

// ===== On-screen keyboard =====
var kbTarget = null;
var kbShifted = false;
var kbLayout = {
  1: '1234567890',
  2: 'qwertyuiop',
  3: 'asdfghjkl',
  4: 'zxcvbnm'
};

function buildKeyboard() {
  var rows = [
    ['1','2','3','4','5','6','7','8','9','0'],
    ['q','w','e','r','t','y','u','i','o','p'],
    ['a','s','d','f','g','h','j','k','l'],
    ['z','x','c','v','b','n','m']
  ];
  rows.forEach(function(keys, i) {
    var rowEl = document.getElementById('kb-row-' + (i + 1));
    rowEl.innerHTML = '';
    keys.forEach(function(k) {
      var btn = document.createElement('button');
      btn.className = 'kb-key';
      btn.textContent = k;
      btn.onclick = function() { kbPress(k); };
      rowEl.appendChild(btn);
    });
    // Add special keys
    if (i === 2) {
      var shift = document.createElement('button');
      shift.className = 'kb-key special wide';
      shift.innerHTML = '&#x21E7;';
      shift.onclick = function() { kbShift(); };
      rowEl.insertBefore(shift, rowEl.firstChild);
    }
    if (i === 3) {
      var del = document.createElement('button');
      del.className = 'kb-key special wide';
      del.innerHTML = '&#x232B;';
      del.onclick = function() { kbDelete(); };
      rowEl.appendChild(del);
    }
  });
  // Bottom row: @ . - _ space Enter
  var row4 = document.getElementById('kb-row-4');
  var specials = ['@', '.', '-', '_', ':'];
  specials.forEach(function(k) {
    var btn = document.createElement('button');
    btn.className = 'kb-key special';
    btn.textContent = k;
    btn.onclick = function() { kbPress(k); };
    row4.insertBefore(btn, row4.lastChild);
  });
  var space = document.createElement('button');
  space.className = 'kb-key kb-space';
  space.textContent = 'space';
  space.onclick = function() { kbPress(' '); };
  row4.insertBefore(space, row4.lastChild);
  var enter = document.createElement('button');
  enter.className = 'kb-key special wide';
  enter.innerHTML = '&#x23CE;';
  enter.onclick = function() { hideKeyboard(); };
  row4.appendChild(enter);
}

function kbPress(k) {
  if (!kbTarget) return;
  var ch = kbShifted ? k.toUpperCase() : k;
  kbTarget.value += ch;
  if (kbShifted) { kbShift(); }
  kbTarget.focus();
}

function kbShift() {
  kbShifted = !kbShifted;
  document.querySelectorAll('.kb-key').forEach(function(btn) {
    if (btn.textContent.length === 1 && /[a-z]/.test(btn.textContent)) {
      btn.textContent = kbShifted ? btn.textContent.toUpperCase() : btn.textContent.toLowerCase();
    }
  });
}

function kbDelete() {
  if (!kbTarget) return;
  kbTarget.value = kbTarget.value.slice(0, -1);
  kbTarget.focus();
}

function showKeyboard(input) {
  kbTarget = input;
  document.getElementById('keyboard').classList.add('show');
}

function hideKeyboard() {
  document.getElementById('keyboard').classList.remove('show');
  kbTarget = null;
}

// Attach keyboard to all inputs with data-kb
document.addEventListener('focusin', function(e) {
  if (e.target.tagName === 'INPUT' && e.target.hasAttribute('data-kb')) {
    showKeyboard(e.target);
  }
});

// ===== Audio =====
function signalBars(sig) {
  var bars = sig > 75 ? 4 : sig > 50 ? 3 : sig > 25 ? 2 : 1;
  var html = '<span class="signal">';
  for (var i = 0; i < 4; i++) {
    var h = 6 + i * 4;
    html += '<span style="height:' + h + 'px;background:' + (i < bars ? '#58a6ff' : '#30363d') + '"></span>';
  }
  return html + '</span>';
}

async function loadAudio() {
  var data = await api('/api/audio/devices');
  var sinksHtml = '';
  if (data.sinks.length === 0) {
    sinksHtml = '<div class="empty-state">No audio output devices.<br>Connect a Bluetooth speaker or headphones.</div>';
  } else {
    data.sinks.forEach(function(s) {
      var badge = s.is_default ? ' <span class="badge b-default">Default</span>' : '';
      var state = s.state === 'SUSPENDED' ? 'Ready' : s.state;
      sinksHtml += '<div class="device-row"><div class="device-info"><div class="device-name">' + (s.description || s.name) + badge + '</div><div class="device-sub">' + state + ' &middot; ' + s.volume + '%</div></div><button class="btn btn-sm" onclick="setDefaultSink(\'' + s.name + '\')">Set Default</button></div>';
    });
  }
  document.getElementById('audio-sinks').innerHTML = sinksHtml;

  var realSources = data.sources.filter(function(s) { return !s.is_monitor; });
  var srcHtml = '';
  if (realSources.length === 0) {
    srcHtml = '<div class="empty-state">No microphones found.<br>Connect a Bluetooth headset or USB mic.</div>';
  } else {
    realSources.forEach(function(s) {
      var badge = s.is_default ? ' <span class="badge b-default">Default</span>' : '';
      var state = s.state === 'SUSPENDED' ? 'Ready' : s.state;
      srcHtml += '<div class="device-row"><div class="device-info"><div class="device-name">' + (s.description || s.name) + badge + '</div><div class="device-sub">' + state + '</div></div><button class="btn btn-sm" onclick="testMic(\'' + s.name + '\')">Test Mic</button></div>';
    });
  }
  document.getElementById('audio-sources').innerHTML = srcHtml;

  var def = data.sinks.find(function(s) { return s.is_default; });
  if (def) {
    document.getElementById('vol-slider').value = def.volume;
    document.getElementById('vol-label').textContent = def.volume + '%';
  }
}

function updateVolLabel(v) { document.getElementById('vol-label').textContent = v + '%'; }

async function setDefaultSink(name) {
  await api('/api/audio/default', 'POST', { sink: name });
  toast('Default output set');
  loadAudio();
}

async function testTone() {
  toast('Playing test tone...');
  await api('/api/audio/test', 'POST');
}

async function testMic(sourceName) {
  toast('Recording 3 seconds... speak now!');
  await api('/api/audio/test-mic', 'POST', { source: sourceName });
  setTimeout(function() { toast('Playing back...'); }, 3500);
}

// ===== Bluetooth =====
async function loadBluetooth() {
  var data = await api('/api/bluetooth/devices');
  var adp = data.adapter || {};
  document.getElementById('bt-adapter').innerHTML =
    '<strong style="color:#e6edf3">' + (adp.name || 'Unknown') + '</strong> &middot; ' + (adp.address || '') + '<br>' +
    'Powered: <span class="badge ' + (adp.powered ? 'b-on' : 'b-off') + '">' + (adp.powered ? 'ON' : 'OFF') + '</span> ' +
    'Discoverable: <span class="badge ' + (adp.discoverable ? 'b-on' : 'b-off') + '">' + (adp.discoverable ? 'ON' : 'OFF') + '</span>';
  var devHtml = '';
  if (!data.devices || data.devices.length === 0) {
    devHtml = '<div class="empty-state">No paired devices.<br>Pair a speaker or headphones below.</div>';
  } else {
    data.devices.forEach(function(d) {
      var badge = d.connected ? '<span class="badge b-connected">Connected</span>' : '<span class="badge b-disconnected">Disconnected</span>';
      var btn = d.connected
        ? '<button class="btn btn-sm" onclick="btDisconnect(\'' + d.mac + '\')">Disconnect</button>'
        : '<button class="btn btn-sm btn-primary" onclick="btConnect(\'' + d.mac + '\')">Connect</button>';
      devHtml += '<div class="device-row"><div class="device-info"><div class="device-name">' + d.name + ' ' + badge + '</div><div class="device-sub">' + d.mac + '</div></div><div class="btn-row">' + btn + '<button class="btn btn-sm btn-danger" onclick="btRemove(\'' + d.mac + '\')">Remove</button></div></div>';
    });
  }
  document.getElementById('bt-devices').innerHTML = devHtml;
}

async function btScan() {
  var btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Scanning...';
  document.getElementById('scan-status').textContent = 'Scanning for 10 seconds. Pair from your device\'s Bluetooth menu.';
  await api('/api/bluetooth/scan');
  setTimeout(function() {
    btn.disabled = false;
    btn.textContent = 'Scan for Devices (10s)';
    document.getElementById('scan-status').textContent = 'Scan complete.';
    loadBluetooth();
  }, 10000);
}

async function btPairManual() {
  var mac = document.getElementById('mac-input').value.trim();
  if (!mac) { toast('Enter a MAC address', 'error'); return; }
  toast('Pairing with ' + mac + '...');
  var r = await api('/api/bluetooth/pair', 'POST', { mac: mac });
  if (r.status === 'ok') {
    toast('Paired successfully');
    document.getElementById('mac-input').value = '';
    hideKeyboard();
    loadBluetooth();
  } else {
    toast('Pairing failed: ' + (r.message || 'unknown error'), 'error');
  }
}

async function btConnect(mac) {
  toast('Connecting...');
  var r = await api('/api/bluetooth/connect', 'POST', { mac: mac });
  if (r.status === 'ok') { toast('Connected'); loadBluetooth(); }
  else { toast('Failed: ' + (r.message || ''), 'error'); }
}

async function btDisconnect(mac) {
  await api('/api/bluetooth/disconnect', 'POST', { mac: mac });
  toast('Disconnected');
  loadBluetooth();
}

async function btRemove(mac) {
  if (!confirm('Remove ' + mac + '?')) return;
  await api('/api/bluetooth/remove', 'POST', { mac: mac });
  toast('Removed');
  loadBluetooth();
}

async function btToggleDiscoverable(on) {
  await api('/api/bluetooth/discoverable', 'POST', { on: on });
  toast(on ? 'Discoverable ON' : 'Discoverable OFF');
  loadBluetooth();
}

// ===== WiFi =====
var wifiConnectSSID = null;

async function loadWifi() {
  var data = await api('/api/wifi/status');
  var html = '';
  if (data.connected) {
    html = '<div class="device-row"><div class="device-info"><div class="device-name">' + (data.ssid || 'Unknown') + ' <span class="badge b-connected">Connected</span></div><div class="device-sub">' + (data.ip || 'No IP') + '</div></div><div style="display:flex;align-items:center;gap:8px">' + signalBars(data.signal || 0) + '<span style="font-size:13px;color:#6e7681">' + (data.signal || 0) + '%</span></div></div>';
  } else {
    html = '<div class="empty-state">Not connected to WiFi.</div>';
  }
  document.getElementById('wifi-status').innerHTML = html;

  var savedHtml = '';
  if (data.saved_networks && data.saved_networks.length > 0) {
    data.saved_networks.forEach(function(n) {
      var badge = n.active ? ' <span class="badge b-connected">Active</span>' : '';
      savedHtml += '<div class="device-row"><div class="device-info"><div class="device-name">' + n.name + badge + '</div></div><button class="btn btn-sm btn-danger" onclick="wifiForget(\'' + n.name.replace(/'/g, "\\'") + '\')">Forget</button></div>';
    });
  } else {
    savedHtml = '<div class="empty-state">No saved networks.</div>';
  }
  document.getElementById('wifi-saved').innerHTML = savedHtml;
}

async function wifiScan() {
  var btn = document.getElementById('wifi-scan-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Scanning...';
  document.getElementById('wifi-networks').innerHTML = '<div class="empty-state">Scanning...</div>';
  var data = await api('/api/wifi/scan');
  btn.disabled = false;
  btn.textContent = 'Scan for Networks';
  var html = '';
  if (data.networks && data.networks.length > 0) {
    data.networks.forEach(function(n) {
      var inUse = n.in_use ? ' <span class="badge b-connected">Connected</span>' : '';
      var sec = n.security && n.security !== 'Open' ? '<span class="badge b-secure">Secure</span>' : '<span class="badge b-open">Open</span>';
      var ssidSafe = (n.ssid || '').replace(/'/g, "\\'");
      html += '<div class="device-row"><div class="device-info"><div class="device-name">' + n.ssid + inUse + ' ' + sec + '</div><div class="device-sub">' + n.signal + '% signal</div></div><div style="display:flex;align-items:center;gap:8px">' + signalBars(n.signal) + '<button class="btn btn-sm btn-primary" onclick="wifiShowConnect(\'' + ssidSafe + '\')">Connect</button></div></div>';
    });
  } else {
    html = '<div class="empty-state">No networks found.</div>';
  }
  document.getElementById('wifi-networks').innerHTML = html;
}

function wifiShowConnect(ssid) {
  wifiConnectSSID = ssid;
  document.getElementById('wifi-connect-card').style.display = 'block';
  document.getElementById('wifi-connect-ssid').textContent = ssid;
  document.getElementById('wifi-password').value = '';
  document.getElementById('wifi-connect-status').textContent = '';
  document.getElementById('wifi-password').focus();
}

async function wifiDoConnect() {
  if (!wifiConnectSSID) return;
  var pwd = document.getElementById('wifi-password').value;
  var statusEl = document.getElementById('wifi-connect-status');
  statusEl.textContent = 'Connecting... (may take 10-20 seconds)';
  statusEl.style.color = '#58a6ff';
  hideKeyboard();
  var r = await api('/api/wifi/connect', 'POST', { ssid: wifiConnectSSID, password: pwd });
  if (r.status === 'ok') {
    statusEl.textContent = 'Connected!';
    statusEl.style.color = '#3fb950';
    toast('Connected to ' + wifiConnectSSID);
    setTimeout(function() {
      document.getElementById('wifi-connect-card').style.display = 'none';
      loadWifi();
    }, 1500);
  } else {
    statusEl.textContent = 'Failed: ' + (r.message || 'unknown error');
    statusEl.style.color = '#f85149';
    toast('WiFi connection failed', 'error');
  }
}

async function wifiForget(name) {
  if (!confirm('Forget network "' + name + '"?')) return;
  var r = await api('/api/wifi/forget', 'POST', { name: name });
  if (r.status === 'ok') { toast('Forgot ' + name); loadWifi(); }
  else { toast('Failed: ' + (r.message || ''), 'error'); }
}

// ===== System =====
async function loadSystem() {
  var data = await api('/api/system/info');
  var html = '';
  if (data.temp_c !== null) {
    var tc = data.temp_c > 75 ? '#f85149' : data.temp_c > 60 ? '#d29922' : '#3fb950';
    html += '<div class="info-item"><div class="info-label">CPU Temp</div><div class="info-value" style="color:' + tc + '">' + data.temp_c.toFixed(1) + '&deg;C</div></div>';
  }
  if (data.ram_total_mb) {
    html += '<div class="info-item"><div class="info-label">Memory</div><div class="info-value" style="font-size:16px">' + data.ram_used_mb + ' / ' + data.ram_total_mb + ' MB</div></div>';
  }
  if (data.uptime_hours !== undefined) {
    html += '<div class="info-item"><div class="info-label">Uptime</div><div class="info-value">' + data.uptime_hours + 'h</div></div>';
  }
  if (data.disk_total) {
    html += '<div class="info-item"><div class="info-label">Storage</div><div class="info-value" style="font-size:16px">' + data.disk_used + ' / ' + data.disk_total + '</div></div>';
  }
  html += '<div class="info-item"><div class="info-label">Display</div><div class="info-value" style="font-size:14px;color:' + (data.livi_status === 'active' ? '#3fb950' : '#f85149') + '">' + (data.livi_status || 'unknown') + '</div></div>';
  html += '<div class="info-item"><div class="info-label">Service</div><div class="info-value" style="font-size:14px;color:' + (data.sidecar_status === 'active' ? '#3fb950' : '#f85149') + '">' + (data.sidecar_status || 'unknown') + '</div></div>';
  document.getElementById('sys-info').innerHTML = html;
}

async function restartLivi() {
  if (!confirm('Restart the display? The screen will go blank for a few seconds.')) return;
  toast('Restarting...');
  await api('/api/system/restart-livi', 'POST');
  setTimeout(function() { toast('Display restarted'); }, 5000);
}

async function loadLogs() {
  document.getElementById('logs-card').style.display = 'block';
  document.getElementById('log-box').textContent = 'Loading...';
  var r = await api('/api/system/logs?count=50');
  document.getElementById('log-box').textContent = r.logs || 'No logs';
}

// Init
buildKeyboard();
loadAudio();
</script>
</body>
</html>'''


def main():
    print(f'[sidecar] Starting home phone hub sidecar on port {LISTEN_PORT}')

    # Create photos directory if it doesn't exist
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    photo_count = len([f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))]) if os.path.isdir(PHOTOS_DIR) else 0
    print(f'[sidecar] Photos directory: {PHOTOS_DIR} ({photo_count} photos)')

    # Connect to LIVI Socket.IO in background
    threading.Thread(target=connect_socketio, daemon=True).start()

    # Create a simple ringtone if none exists
    if not os.path.exists(RINGTONE_PATH):
        print(f'[sidecar] No ringtone at {RINGTONE_PATH}')
        print('[sidecar] Create one with: ffmpeg -f lavfi -i "sine=frequency=440:duration=1" -ar 44100 ' + RINGTONE_PATH)

    class ReusableHTTPServer(http.server.HTTPServer):
        allow_reuse_address = True

    server = ReusableHTTPServer(('0.0.0.0', LISTEN_PORT), RingHandler)
    print(f'[sidecar] Listening on 0.0.0.0:{LISTEN_PORT}')

    def shutdown(sig, frame):
        print('[sidecar] Shutting down...')
        server.shutdown()
        sio.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()


if __name__ == '__main__':
    main()

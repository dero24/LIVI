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

# ===== Night Mode config (v0.6 — Display/night mode) =====
# Stored in a JSON config file so it persists across sidecar restarts.
# The overlay polls /api/display/nightmode to get the config, and the
# settings page POSTs to update it.
NIGHTMODE_CONFIG_PATH = '/home/raspberry/.config/homephone/nightmode.json'
nightmode_lock = threading.Lock()
nightmode_config = {
    'enabled': True,           # master toggle
    'mode': 'auto',            # 'auto' (time-based), 'on' (always), 'off' (never)
    'start_hour': 22,          # night mode starts at 22:00 (auto mode)
    'start_min': 0,
    'end_hour': 6,             # night mode ends at 06:00 (auto mode)
    'end_min': 0,
    'brightness_pct': 35,      # overlay dimming percentage (0-100, where 100=full brightness, 0=black)
    'warm_tint': True,         # apply a subtle warm/amber tint (like Night Shift)
    'warm_tint_intensity': 0.12,  # 0-1, how strong the warm tint is
}

# Phone theme hint — companion app reports the phone's system dark mode state.
# Kept for potential future use (single-user mode), but not currently used
# since the hub is shared across multiple phones and follow-phone doesn't work.
phone_theme_hint = {'dark': None, 'reported_at': 0}
phone_theme_lock = threading.Lock()
PHONE_THEME_TTL = 300  # phone theme hint is stale after 5 min without an update


def load_nightmode_config():
    """Load night mode config from disk, falling back to defaults."""
    global nightmode_config
    try:
        os.makedirs(os.path.dirname(NIGHTMODE_CONFIG_PATH), exist_ok=True)
        with open(NIGHTMODE_CONFIG_PATH) as f:
            saved = json.load(f)
        # Merge with defaults (so new fields get default values)
        merged = nightmode_config.copy()
        merged.update(saved)
        with nightmode_lock:
            nightmode_config = merged
        print(f'[sidecar] Night mode config loaded: mode={merged["mode"]}, enabled={merged["enabled"]}')
    except FileNotFoundError:
        print('[sidecar] No night mode config file, using defaults')
        save_nightmode_config()
    except Exception as e:
        print(f'[sidecar] Error loading night mode config: {e}')


def save_nightmode_config():
    """Save night mode config to disk."""
    try:
        os.makedirs(os.path.dirname(NIGHTMODE_CONFIG_PATH), exist_ok=True)
        with nightmode_lock:
            config_copy = nightmode_config.copy()
        with open(NIGHTMODE_CONFIG_PATH, 'w') as f:
            json.dump(config_copy, f, indent=2)
    except Exception as e:
        print(f'[sidecar] Error saving night mode config: {e}')


def is_night_time():
    """Check if the current time falls within the configured night mode window."""
    with nightmode_lock:
        cfg = nightmode_config
    now = time.localtime()
    current_min = now.tm_hour * 60 + now.tm_min
    start_min = cfg['start_hour'] * 60 + cfg['start_min']
    end_min = cfg['end_hour'] * 60 + cfg['end_min']
    if start_min <= end_min:
        # Same-day window (e.g. 14:00-18:00)
        return start_min <= current_min < end_min
    else:
        # Overnight window (e.g. 22:00-06:00) — wraps past midnight
        return current_min >= start_min or current_min < end_min


def get_nightmode_status():
    """Return the current night mode config + whether night mode is currently active."""
    with nightmode_lock:
        cfg = nightmode_config.copy()

    if not cfg['enabled']:
        active = False
        reason = 'disabled'
    elif cfg['mode'] == 'on':
        active = True
        reason = 'forced-on'
    elif cfg['mode'] == 'off':
        active = False
        reason = 'forced-off'
    else:  # 'auto'
        active = is_night_time()
        reason = 'auto-time'

    cfg['active'] = active
    cfg['reason'] = reason
    return cfg


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


def handle_ring(slot, caller, phone, mac=None, phone_name=None):
    """Handle an incoming ring event."""
    print(f'[sidecar] RING slot={slot} caller={caller} phone={phone} mac={mac} name={phone_name}')
    ring_state[slot] = {
        'caller': caller or 'Unknown',
        'phone': phone or 'Unknown',
        # Which physical phone is ringing (multi-phone dock). bt_mac is the
        # ring slot for HFP-detected calls; phone_name is the BT alias.
        'bt_mac': mac or (slot if ':' in str(slot) else ''),
        'phone_name': phone_name or '',
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


def ofono_call_control(mac, action):
    """Answer ('answer') or reject ('reject') the incoming call on the HFP
    modem for the given BT MAC via oFono. Returns (ok, message).

    This is the multi-phone answer path: it works for any BT-connected phone,
    not just the one currently projecting AA."""
    try:
        import dbus
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object('org.ofono', '/'), 'org.ofono.Manager')
        modems = manager.GetModems()
    except Exception as e:
        return False, f'oFono unavailable: {e}'
    suffix = mac.replace(':', '_').upper() if mac else None
    for path, props in modems:
        if props.get('Type') != 'hfp':
            continue
        if suffix and suffix not in str(path).upper():
            continue
        try:
            vc = dbus.Interface(bus.get_object('org.ofono', path),
                                'org.ofono.VoiceCallManager')
            for call_path, call_props in vc.GetCalls():
                if call_props.get('State') == 'incoming':
                    call = dbus.Interface(bus.get_object('org.ofono', call_path),
                                          'org.ofono.VoiceCall')
                    if action == 'answer':
                        call.Answer()
                    else:
                        call.Hangup()
                    print(f'[sidecar] oFono {action} on {call_path}')
                    return True, f'{action} sent'
        except Exception as e:
            return False, f'oFono {action} failed: {e}'
    return False, 'no incoming call found' + (f' for {mac}' if mac else '')


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


# ===== Night mode handlers (v0.6 — Display/night mode) =====

def handle_nightmode_get():
    """Return the current night mode config + active status."""
    return get_nightmode_status()


def handle_nightmode_post(body):
    """Update night mode config. Only updates provided fields."""
    if not body:
        return {'error': 'body required'}, 400
    allowed_fields = {
        'enabled', 'mode', 'start_hour', 'start_min',
        'end_hour', 'end_min', 'brightness_pct', 'warm_tint', 'warm_tint_intensity'
    }
    with nightmode_lock:
        updated = []
        for key, value in body.items():
            if key in allowed_fields:
                # Validate types/ranges
                if key == 'mode' and value not in ('auto', 'on', 'off'):
                    return {'error': f'invalid mode: {value}'}, 400
                if key == 'enabled' and not isinstance(value, bool):
                    return {'error': 'enabled must be boolean'}, 400
                if key == 'warm_tint' and not isinstance(value, bool):
                    return {'error': 'warm_tint must be boolean'}, 400
                if key in ('start_hour', 'end_hour') and not (0 <= int(value) <= 23):
                    return {'error': f'{key} must be 0-23'}, 400
                if key in ('start_min', 'end_min') and not (0 <= int(value) <= 59):
                    return {'error': f'{key} must be 0-59'}, 400
                if key == 'brightness_pct' and not (5 <= int(value) <= 100):
                    return {'error': 'brightness_pct must be 5-100'}, 400
                if key == 'warm_tint_intensity' and not (0 <= float(value) <= 1):
                    return {'error': 'warm_tint_intensity must be 0-1'}, 400
                nightmode_config[key] = value
                updated.append(key)
    if updated:
        save_nightmode_config()
        print(f'[sidecar] Night mode config updated: {updated}')
    return get_nightmode_status()


def handle_theme_post(body):
    """Receive phone theme hint from companion app.

    Body: { "dark": true/false }  — phone's system dark mode state.
    Used when night mode mode='follow-phone'.
    """
    if not body or 'dark' not in body:
        return {'error': 'dark required'}, 400
    with phone_theme_lock:
        phone_theme_hint['dark'] = bool(body['dark'])
        phone_theme_hint['reported_at'] = time.time()
    print(f'[sidecar] Phone theme hint: dark={phone_theme_hint["dark"]}')
    return {'status': 'ok', 'dark': phone_theme_hint['dark']}


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


def _bt_parse_info(info):
    """Parse `bluetoothctl info` output -> (connected, icon, is_phone)."""
    connected = 'Connected: yes' in info
    icon = ''
    is_phone = False
    for iline in info.split('\n'):
        iline_s = iline.strip()
        if iline_s.startswith('Icon:'):
            # Parse Icon field (e.g. "Icon: phone" or "Icon: audio-headset")
            icon = iline_s[5:].strip()
        elif iline_s.startswith('Class:'):
            # Parse BT class: major device class is bits 13-16
            # e.g. "Class: 0x005a020c (5898764)" -> 0x0200 = Phone
            try:
                cls_hex = iline_s.split('0x')[1].split()[0]
                cls_val = int(cls_hex, 16)
                major_cls = (cls_val >> 8) & 0x1f
                if major_cls == 0x02:
                    is_phone = True
            except Exception:
                pass
    # Icon-based detection (more reliable)
    if icon in ('phone', 'modem'):
        is_phone = True
    return connected, icon, is_phone


def bt_guard_not_phone(mac):
    """Return an error dict if mac is a phone (managed by LIVI wireless AA).

    Phones must only ever be paired from the phone side — LIVI's BlueZ agent
    auto-accepts. Running bluetoothctl pair/connect from the sidecar spawns a
    SECOND agent that shows PIN/confirmation prompts on the touchscreen."""
    try:
        r = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=5)
        _, _, is_phone = _bt_parse_info(r.stdout)
        if is_phone:
            return {'status': 'error', 'mac': mac,
                    'message': "Phones pair from the phone's Bluetooth settings — the hub accepts automatically"}
    except Exception:
        pass
    return None


def get_bluetooth_devices():
    """List paired Bluetooth devices and adapter status.
    Phones (managed by LIVI wireless AA) are marked is_phone=True
    so the frontend can filter them out of the audio devices list."""
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
                    # Get detailed info including icon and class
                    connected = False
                    icon = ''
                    is_phone = False
                    try:
                        rc = subprocess.run(['bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=5)
                        connected, icon, is_phone = _bt_parse_info(rc.stdout)
                    except Exception:
                        pass
                    devices.append({'mac': mac, 'name': name, 'connected': connected,
                                   'icon': icon, 'is_phone': is_phone})
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
    """Pair a Bluetooth device (audio devices only — never phones)."""
    guard = bt_guard_not_phone(mac)
    if guard:
        return guard
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
    """Connect a paired Bluetooth device (audio devices only — never phones)."""
    guard = bt_guard_not_phone(mac)
    if guard:
        return guard
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
    """Disconnect a Bluetooth device (audio devices only — never phones)."""
    guard = bt_guard_not_phone(mac)
    if guard:
        return guard
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


def wifi_reconnect():
    """Reconnect wlan0 — bounce the interface to recover from network drops.
    Also re-applies power_save off after reconnect."""
    try:
        # Disconnect
        subprocess.run(['nmcli', 'dev', 'disconnect', 'wlan0'],
                       capture_output=True, text=True, timeout=10)
        time.sleep(2)
        # Reconnect
        r = subprocess.run(['nmcli', 'dev', 'connect', 'wlan0'],
                          capture_output=True, text=True, timeout=30)
        time.sleep(3)
        # Re-apply power_save off
        subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'],
                       capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return {'status': 'ok', 'message': 'wlan0 reconnected'}
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
        # Never cache — the hub overlay XHRs this page and must always get the
        # current version (an old cached copy shows a stale BT tab / duplicate header).
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
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
        elif parsed.path == '/api/debug/ping':
            # Ping the default gateway and return result
            try:
                gw_r = subprocess.run(['ip', 'route', 'show', 'dev', 'wlan0'],
                                      capture_output=True, text=True, timeout=5)
                gw = None
                for line in gw_r.stdout.split('\n'):
                    if 'default' in line and 'via' in line.split():
                        gw = line.split()[line.split().index('via') + 1]
                        break
                if not gw:
                    self._send_json({'error': 'No gateway found'})
                    return
                r = subprocess.run(['ping', '-I', 'wlan0', '-c', '3', '-W', '5', gw],
                                  capture_output=True, text=True, timeout=15)
                result = r.stdout.strip()
                if r.returncode == 0:
                    # Extract last line (stats)
                    stats = [l for l in result.split('\n') if 'packet loss' in l]
                    self._send_json({'result': stats[-1] if stats else result[-200:]})
                else:
                    self._send_json({'result': 'PING FAILED: ' + (r.stderr.strip()[-200:] or result[-200:])})
            except Exception as e:
                self._send_json({'error': str(e)})
        elif parsed.path == '/api/debug/diagnostics':
            # Quick system diagnostics
            diag = {'services': {}, 'network': {}, 'system': {}, 'bt': {}}
            # Services
            for svc in ['livi.service', 'homephone-sidecar.service', 'hfp-call-monitor.service',
                        'wlan0-watchdog.service', 'usb-autosuspend-fix.service']:
                r = subprocess.run(['systemctl', '--user', 'is-active', svc],
                                  capture_output=True, text=True, timeout=3)
                diag['services'][svc] = r.stdout.strip()
            # Network
            wifi = get_wifi_status()
            diag['network']['ssid'] = wifi.get('ssid')
            diag['network']['ip'] = wifi.get('ip')
            diag['network']['signal'] = wifi.get('signal')
            try:
                r = subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'get', 'power_save'],
                                  capture_output=True, text=True, timeout=3)
                diag['network']['power_save'] = r.stdout.strip().replace('Power save: ', '')
            except:
                diag['network']['power_save'] = 'unknown'
            # System
            try:
                with open('/sys/class/thermal/thermal_zone0/temp') as f:
                    diag['system']['cpu_temp'] = int(f.read().strip()) / 1000.0
            except:
                diag['system']['cpu_temp'] = 0
            try:
                with open('/sys/module/usbcore/parameters/autosuspend') as f:
                    diag['system']['autosuspend'] = f.read().strip()
            except:
                diag['system']['autosuspend'] = 'unknown'
            try:
                r = subprocess.run(['uptime', '-p'], capture_output=True, text=True, timeout=3)
                diag['system']['uptime'] = r.stdout.strip()
            except:
                pass
            try:
                r = subprocess.run(['sudo', '-n', 'vcgencmd', 'get_throttled'],
                                  capture_output=True, text=True, timeout=3)
                diag['system']['throttled'] = r.stdout.strip().replace('throttled=', '')
            except:
                diag['system']['throttled'] = 'unknown'
            # BT
            try:
                r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
                diag['bt']['devices'] = r.stdout.strip().replace('\n', ', ')
                r2 = subprocess.run(['bluetoothctl', 'show'], capture_output=True, text=True, timeout=5)
                diag['bt']['discoverable'] = 'Discoverable: yes' in r2.stdout
            except:
                pass
            self._send_json(diag)
        elif parsed.path == '/api/debug/logs':
            # Get various logs
            log_type = urllib.parse.parse_qs(parsed.query).get('type', [''])[0]
            try:
                if log_type == 'dmesg':
                    r = subprocess.run(['sudo', '-n', 'dmesg', '--color=never'],
                                      capture_output=True, text=True, timeout=10)
                    lines = r.stdout.strip().split('\n')[-30:]
                    self._send_json({'logs': '\n'.join(lines)})
                elif log_type == 'journalctl':
                    r = subprocess.run(['journalctl', '--user', '-n', '30', '--no-pager', '-q'],
                                      capture_output=True, text=True, timeout=10)
                    self._send_json({'logs': r.stdout.strip()})
                elif log_type == 'watchdog':
                    try:
                        with open('/home/raspberry/wlan0_watchdog.log') as f:
                            lines = f.readlines()[-30:]
                        self._send_json({'logs': ''.join(lines)})
                    except:
                        self._send_json({'logs': 'No watchdog log yet'})
                else:
                    self._send_json({'error': 'Unknown log type: ' + log_type})
            except Exception as e:
                self._send_json({'error': str(e)})
        elif parsed.path == '/api/display/nightmode':
            # GET — return current night mode config + active status
            self._send_json(handle_nightmode_get())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        # Slot stays a string — the HFP monitor uses the phone's BT MAC as the
        # slot so the hub knows WHICH phone is ringing (multi-phone dock).
        slot = params.get('slot', ['1'])[0]

        if parsed.path == '/ring':
            caller = params.get('caller', [None])[0]
            phone = params.get('phone', [None])[0]
            mac = params.get('mac', [None])[0]
            phone_name = params.get('phone_name', [None])[0]
            if params.get('clear', [''])[0] == '1':
                # Call ended / answered elsewhere — clear the banner. (Without
                # this branch a clear POST used to START a ring with caller
                # "Unknown" and play the ringtone.)
                handle_hangup(slot)
                self._send_json({'status': 'hungup', 'slot': slot})
            else:
                handle_ring(slot, caller, phone, mac=mac, phone_name=phone_name)
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

        elif parsed.path == '/answer':
            # Answer the incoming call on the ringing phone via oFono (HFP ATA).
            # Works for any BT-connected phone, not just the AA-projecting one.
            mac = params.get('mac', [None])[0] or (slot if ':' in slot else None)
            ok, msg = ofono_call_control(mac, 'answer')
            if slot in ring_state:
                del ring_state[slot]
            stop_ringtone()
            self._send_json({'status': 'ok' if ok else 'error', 'message': msg},
                            200 if ok else 404)

        elif parsed.path == '/reject':
            mac = params.get('mac', [None])[0] or (slot if ':' in slot else None)
            ok, msg = ofono_call_control(mac, 'reject')
            handle_hangup(slot)
            self._send_json({'status': 'ok' if ok else 'error', 'message': msg},
                            200 if ok else 404)

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

        elif parsed.path == '/api/debug/restart':
            svc = urllib.parse.parse_qs(parsed.query).get('service', [''])[0]
            if svc:
                def _restart(s):
                    time.sleep(1)
                    subprocess.run(['systemctl', '--user', 'restart', s],
                                  capture_output=True, timeout=15)
                threading.Thread(target=_restart, args=(svc,), daemon=True).start()
                self._send_json({'message': f'Restarting {svc}...'})
            else:
                self._send_json({'error': 'service required'}, 400)

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

        elif parsed.path == '/api/wifi/reconnect':
            result = wifi_reconnect()
            self._send_json(result, 200 if result.get('status') == 'ok' else 400)

        elif parsed.path == '/api/wifi/forget':
            body = self._read_body()
            name = body.get('name')
            if name:
                result = wifi_forget(name)
                self._send_json(result)
            else:
                self._send_json({'error': 'name required'}, 400)

        # ===== v0.6 — Display / Night mode =====
        elif parsed.path == '/api/display/nightmode':
            # POST — update night mode config
            body = self._read_body()
            ret = handle_nightmode_post(body)
            if isinstance(ret, tuple):
                result, code = ret
            else:
                result, code = ret, 200
            self._send_json(result, code)

        elif parsed.path == '/api/display/theme':
            # POST — companion app reports phone's system dark mode state
            body = self._read_body()
            ret = handle_theme_post(body)
            if isinstance(ret, tuple):
                result, code = ret
            else:
                result, code = ret, 200
            self._send_json(result, code)

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

  /* Header — hidden when embedded in the hub overlay iframe */
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 20px 28px 16px; flex-shrink: 0;
  }
  body.in-iframe .header { display: none; }
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
  .btn-toggle { }
  .btn-toggle.active { background: #1f6feb; border-color: #1f6feb; color: #fff; }

  /* Toggle switch (iOS-style) */
  .switch { position: relative; display: inline-block; width: 52px; height: 30px; flex-shrink: 0; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider-toggle {
    position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
    background: #30363d; border-radius: 30px; transition: 0.3s;
  }
  .slider-toggle:before {
    content: ""; position: absolute; height: 24px; width: 24px; left: 3px; bottom: 3px;
    background: #f0f6fc; border-radius: 50%; transition: 0.3s;
  }
  .switch input:checked + .slider-toggle { background: #238636; }
  .switch input:checked + .slider-toggle:before { transform: translateX(22px); }

  /* Setting rows */
  .setting-row { padding: 4px 0; }

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
    <button class="tab" data-tab="display" onclick="showTab('display', this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
      Display
    </button>
    <button class="tab" data-tab="system" onclick="showTab('system', this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 10v6m11-11h-6M7 12H1m17.4-7.4l-4.2 4.2M9.8 14.2l-4.2 4.2m12.8 0l-4.2-4.2M9.8 9.8L5.6 5.6"/></svg>
      System
    </button>
    <button class="tab" data-tab="debug" onclick="showTab('debug', this)" style="margin-left:auto">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2v4M16 2v4M3 6h18M5 6v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6M9 10l2 2-2 2M13 10l2 2-2 2"/></svg>
      Debug
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
      <div class="card" style="border-color:rgba(88,166,255,0.2);background:rgba(88,166,255,0.04)">
        <div class="card-title" style="color:#58a6ff">Wireless Android Auto</div>
        <div class="hint" style="margin-bottom:0">
          To pair your phone for wireless Android Auto, go to your phone's
          <strong>Settings &rarr; Bluetooth</strong>, find
          <strong id="bt-aa-name">homephone-countertop</strong>, and tap pair.
          The phone will connect automatically &mdash; no action needed on the hub.
        </div>
      </div>
      <div class="card">
        <div class="card-title">Adapter</div>
        <div id="bt-adapter" class="device-sub" style="margin-bottom:14px">Loading...</div>
        <div class="btn-row">
          <button class="btn btn-sm" onclick="btToggleDiscoverable(true)">Make Discoverable</button>
          <button class="btn btn-sm" onclick="btToggleDiscoverable(false)">Hide</button>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Paired Audio Devices</div>
        <div id="bt-devices"><div class="empty-state">Loading...</div></div>
      </div>
      <div class="card">
        <div class="card-title">Pair New Audio Device</div>
        <div class="hint">Put your speaker or headphones in pairing mode, then scan or enter its MAC address.</div>
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
        <div class="btn-row" style="margin-top:14px">
          <button class="btn btn-sm" onclick="wifiReconnect()" id="wifi-reconnect-btn">Disconnect &amp; Reconnect</button>
        </div>
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

    <!-- Display Tab -->
    <div id="tab-display" class="panel">
      <div class="card">
        <div class="card-title">Night Mode</div>
        <div class="setting-row" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <div>
            <div style="font-weight:500">Enable night mode</div>
            <div class="device-sub">Dims the screen during configured hours</div>
          </div>
          <label class="switch">
            <input type="checkbox" id="nm-enabled" onchange="saveNightMode()">
            <span class="slider-toggle"></span>
          </label>
        </div>
        <div class="setting-row" style="margin-bottom:16px">
          <div style="font-weight:500;margin-bottom:8px">Mode</div>
          <div class="btn-row">
            <button class="btn btn-toggle" id="nm-mode-auto" onclick="setNightModeMode('auto')">Auto (time-based)</button>
            <button class="btn btn-toggle" id="nm-mode-on" onclick="setNightModeMode('on')">Always on</button>
            <button class="btn btn-toggle" id="nm-mode-off" onclick="setNightModeMode('off')">Always off</button>
          </div>
        </div>
        <div id="nm-time-row" class="setting-row" style="margin-bottom:16px">
          <div style="font-weight:500;margin-bottom:8px">Active hours</div>
          <div class="slider-row" style="margin-bottom:8px">
            <label>Starts at</label>
            <input type="time" id="nm-start" value="22:00" onchange="saveNightMode()" style="background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:6px 10px;font-size:14px">
          </div>
          <div class="slider-row">
            <label>Ends at</label>
            <input type="time" id="nm-end" value="06:00" onchange="saveNightMode()" style="background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:6px 10px;font-size:14px">
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Brightness & Tint</div>
        <div class="slider-row" style="margin-bottom:16px">
          <label>Brightness</label>
          <input type="range" id="nm-brightness" min="5" max="100" value="35" oninput="updateBrightnessLabel(this.value)" onchange="saveNightMode()">
          <span class="vol-value" id="nm-brightness-label">35%</span>
        </div>
        <div class="setting-row" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <div>
            <div style="font-weight:500">Warm tint</div>
            <div class="device-sub">Subtle amber overlay (like Night Shift)</div>
          </div>
          <label class="switch">
            <input type="checkbox" id="nm-warm-tint" onchange="saveNightMode()">
            <span class="slider-toggle"></span>
          </label>
        </div>
        <div class="slider-row" id="nm-tint-intensity-row" style="margin-bottom:16px">
          <label>Tint strength</label>
          <input type="range" id="nm-tint-intensity" min="0" max="50" value="12" oninput="updateTintLabel(this.value)" onchange="saveNightMode()">
          <span class="vol-value" id="nm-tint-label">12%</span>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Status & Preview</div>
        <div id="nm-status" class="device-sub" style="margin-bottom:14px">Loading...</div>
        <div class="btn-row">
          <button class="btn btn-primary" onclick="previewNightMode(true)">Preview: Night</button>
          <button class="btn" onclick="previewNightMode(false)">Preview: Day</button>
          <button class="btn" onclick="loadDisplay()">Refresh</button>
        </div>
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

    <!-- Debug Tab -->
    <div id="tab-debug" class="panel">
      <div class="card">
        <div class="card-title">Network Recovery</div>
        <div class="hint">If the Pi becomes unreachable on the network, use these to bounce WiFi.</div>
        <div class="btn-row" style="margin-top:12px">
          <button class="btn btn-primary" onclick="dbgWifiReconnect()" id="dbg-wifi-btn">Disconnect &amp; Reconnect WiFi</button>
          <button class="btn btn-sm" onclick="dbgPingGateway()">Ping Gateway</button>
        </div>
        <div id="dbg-ping-result" style="margin-top:10px;font-size:13px;color:#6e7681"></div>
      </div>
      <div class="card">
        <div class="card-title">Service Control</div>
        <div class="btn-row">
          <button class="btn btn-sm" onclick="dbgRestart('homephone-sidecar')">Restart Sidecar</button>
          <button class="btn btn-sm" onclick="dbgRestart('livi')">Restart LIVI</button>
          <button class="btn btn-sm" onclick="dbgRestart('hfp-call-monitor')">Restart HFP Monitor</button>
          <button class="btn btn-sm" onclick="dbgRestart('wlan0-watchdog')">Restart Watchdog</button>
        </div>
        <div id="dbg-service-result" style="margin-top:10px;font-size:13px;color:#6e7681"></div>
      </div>
      <div class="card">
        <div class="card-title">Quick Diagnostics</div>
        <div class="btn-row">
          <button class="btn btn-sm" onclick="dbgDiagnostics()" id="dbg-diag-btn">Run Diagnostics</button>
          <button class="btn btn-sm" onclick="dbgLogs('dmesg')" id="dbg-dmesg-btn">dmesg (last 30)</button>
          <button class="btn btn-sm" onclick="dbgLogs('journalctl')">journalctl (last 30)</button>
          <button class="btn btn-sm" onclick="dbgLogs('watchdog')">Watchdog Log</button>
        </div>
        <div id="dbg-output" style="margin-top:12px;font-family:monospace;font-size:12px;color:#8b949e;white-space:pre-wrap;max-height:400px;overflow:auto;background:#161b22;padding:12px;border-radius:8px;display:none"></div>
      </div>
      <div class="card">
        <div class="card-title">System State</div>
        <div id="dbg-state" class="info-grid"><div class="empty-state">Tap "Run Diagnostics" to check.</div></div>
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
// Detect if we're embedded in the hub overlay iframe
if (window.parent && window.parent !== window) {
  document.body.classList.add('in-iframe');
}
// ===== Tab switching =====
var btPollTimer = null;  // refreshes the BT tab so external state changes show up
function showTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  // Stop BT polling whenever we leave the Bluetooth tab
  if (btPollTimer) { clearInterval(btPollTimer); btPollTimer = null; }
  if (name === 'audio') loadAudio();
  if (name === 'bluetooth') {
    loadBluetooth();
    // Poll while visible — pairing/unpairing from the phone side (or audio
    // device connect/disconnect) happens outside this page, so a one-shot
    // load goes stale and keeps showing e.g. "Connected" after an unpair.
    btPollTimer = setInterval(loadBluetooth, 4000);
  }
  if (name === 'wifi') loadWifi();
  if (name === 'display') loadDisplay();
  if (name === 'system') loadSystem();
  if (name === 'debug') dbgDiagnostics();
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
  // Update the wireless AA info card with the actual adapter name
  var aaName = document.getElementById('bt-aa-name');
  if (aaName && adp.name) aaName.textContent = adp.name;
  document.getElementById('bt-adapter').innerHTML =
    '<strong style="color:#e6edf3">' + (adp.name || 'Unknown') + '</strong> &middot; ' + (adp.address || '') + '<br>' +
    'Powered: <span class="badge ' + (adp.powered ? 'b-on' : 'b-off') + '">' + (adp.powered ? 'ON' : 'OFF') + '</span> ' +
    'Discoverable: <span class="badge ' + (adp.discoverable ? 'b-on' : 'b-off') + '">' + (adp.discoverable ? 'ON' : 'OFF') + '</span>';
  // Filter out phones (managed by LIVI wireless AA, not by this settings page)
  var audioDevices = (data.devices || []).filter(function(d) { return !d.is_phone; });
  var devHtml = '';
  if (audioDevices.length === 0) {
    devHtml = '<div class="empty-state">No paired audio devices.<br>Pair a speaker or headphones below.</div>';
  } else {
    audioDevices.forEach(function(d) {
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

async function wifiReconnect() {
  var btn = document.getElementById('wifi-reconnect-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Reconnecting...'; }
  toast('Disconnecting and reconnecting WiFi...');
  var r = await api('/api/wifi/reconnect', 'POST');
  if (r.status === 'ok') {
    toast('WiFi reconnected successfully');
  } else {
    toast('Reconnect failed: ' + (r.message || 'unknown'), 'error');
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Disconnect & Reconnect'; }
  loadWifi();
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

// ===== Display / Night Mode =====
var nmConfig = null;

async function loadDisplay() {
  var data = await api('/api/display/nightmode');
  if (!data || data.status === 'error') {
    document.getElementById('nm-status').textContent = 'Error loading night mode config';
    return;
  }
  nmConfig = data;
  // Populate form
  document.getElementById('nm-enabled').checked = data.enabled;
  document.getElementById('nm-brightness').value = data.brightness_pct;
  document.getElementById('nm-brightness-label').textContent = data.brightness_pct + '%';
  document.getElementById('nm-warm-tint').checked = data.warm_tint;
  var tintPct = Math.round(data.warm_tint_intensity * 100);
  document.getElementById('nm-tint-intensity').value = tintPct;
  document.getElementById('nm-tint-label').textContent = tintPct + '%';
  // Time inputs (format: HH:MM)
  var startStr = String(data.start_hour).padStart(2, '0') + ':' + String(data.start_min).padStart(2, '0');
  var endStr = String(data.end_hour).padStart(2, '0') + ':' + String(data.end_min).padStart(2, '0');
  document.getElementById('nm-start').value = startStr;
  document.getElementById('nm-end').value = endStr;
  // Mode buttons
  updateModeButtons(data.mode);
  // Status
  var statusEl = document.getElementById('nm-status');
  var activeText = data.active ? 'ACTIVE (dimmed)' : 'Inactive (full brightness)';
  var reasonText = '';
  if (data.reason === 'auto-time') reasonText = ' — time-based';
  else if (data.reason === 'forced-on') reasonText = ' — forced on';
  else if (data.reason === 'forced-off') reasonText = ' — forced off';
  else if (data.reason === 'disabled') reasonText = ' — master toggle off';
  statusEl.innerHTML = '<span style="color:' + (data.active ? '#d29922' : '#3fb950') + ';font-weight:500">' + activeText + '</span>' + reasonText;
  // Show/hide time row based on mode
  updateModeButtons(data.mode);
}

function updateModeButtons(mode) {
  ['auto', 'on', 'off'].forEach(function(m) {
    var btn = document.getElementById('nm-mode-' + m);
    if (btn) {
      if (m === mode) btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });
  // Show/hide time inputs (only relevant for auto mode)
  var timeRow = document.getElementById('nm-time-row');
  if (timeRow) timeRow.style.display = mode === 'auto' ? '' : 'none';
}

function setNightModeMode(mode) {
  updateModeButtons(mode);
  saveNightMode({ mode: mode });
}

function updateBrightnessLabel(val) {
  document.getElementById('nm-brightness-label').textContent = val + '%';
}

function updateTintLabel(val) {
  document.getElementById('nm-tint-label').textContent = val + '%';
}

async function saveNightMode(override) {
  var body = override || {};
  body.enabled = document.getElementById('nm-enabled').checked;
  body.brightness_pct = parseInt(document.getElementById('nm-brightness').value);
  body.warm_tint = document.getElementById('nm-warm-tint').checked;
  body.warm_tint_intensity = parseInt(document.getElementById('nm-tint-intensity').value) / 100;
  // Parse time inputs
  var startVal = document.getElementById('nm-start').value;
  var endVal = document.getElementById('nm-end').value;
  if (startVal) {
    var parts = startVal.split(':');
    body.start_hour = parseInt(parts[0]);
    body.start_min = parseInt(parts[1]);
  }
  if (endVal) {
    var parts = endVal.split(':');
    body.end_hour = parseInt(parts[0]);
    body.end_min = parseInt(parts[1]);
  }
  // If override has mode, use it; otherwise keep current
  if (!override || !override.mode) {
    // Determine current mode from active button
    ['auto', 'on', 'off'].forEach(function(m) {
      var btn = document.getElementById('nm-mode-' + m);
      if (btn && btn.classList.contains('active')) body.mode = m;
    });
  }
  var data = await api('/api/display/nightmode', 'POST', body);
  if (data && data.status !== 'error') {
    nmConfig = data;
    // Update status display
    var statusEl = document.getElementById('nm-status');
    var activeText = data.active ? 'ACTIVE (dimmed)' : 'Inactive (full brightness)';
    var reasonText = '';
    if (data.reason === 'auto-time') reasonText = ' — time-based';
    else if (data.reason === 'forced-on') reasonText = ' — forced on';
    else if (data.reason === 'forced-off') reasonText = ' — forced off';
    else if (data.reason === 'disabled') reasonText = ' — master toggle off';
    statusEl.innerHTML = '<span style="color:' + (data.active ? '#d29922' : '#3fb950') + ';font-weight:500">' + activeText + '</span>' + reasonText;
    toast('Night mode saved');
  } else {
    toast('Error saving night mode', 'error');
  }
}

async function previewNightMode(active) {
  // Temporarily force night mode on or off
  var body = { mode: active ? 'on' : 'off' };
  var data = await api('/api/display/nightmode', 'POST', body);
  if (data && data.status !== 'error') {
    toast(active ? 'Night mode preview (forced on)' : 'Day mode preview (forced off)');
    // Refresh status
    setTimeout(loadDisplay, 500);
  } else {
    toast('Error in preview', 'error');
  }
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

// ===== Debug Tab =====
async function dbgWifiReconnect() {
  var btn = document.getElementById('dbg-wifi-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Reconnecting...'; }
  var r = await api('/api/wifi/reconnect', 'POST');
  if (r.status === 'ok') { toast('WiFi reconnected'); } else { toast('Reconnect failed: ' + (r.message || ''), 'error'); }
  if (btn) { btn.disabled = false; btn.textContent = 'Disconnect & Reconnect WiFi'; }
}

async function dbgPingGateway() {
  document.getElementById('dbg-ping-result').textContent = 'Pinging...';
  var r = await api('/api/debug/ping');
  document.getElementById('dbg-ping-result').textContent = r.result || r.error || 'No response';
}

async function dbgRestart(svc) {
  document.getElementById('dbg-service-result').textContent = 'Restarting ' + svc + '...';
  var r = await api('/api/debug/restart?service=' + encodeURIComponent(svc), 'POST');
  document.getElementById('dbg-service-result').textContent = r.message || r.error || 'Done';
}

async function dbgDiagnostics() {
  var r = await api('/api/debug/diagnostics');
  var html = '';
  if (r.services) {
    for (var svc in r.services) {
      var st = r.services[svc];
      var cls = st === 'active' ? 'b-connected' : 'b-disconnected';
      html += '<div class="info-item"><span class="info-label">' + svc + '</span><span class="badge ' + cls + '">' + st + '</span></div>';
    }
  }
  if (r.network) {
    html += '<div class="info-item"><span class="info-label">WiFi SSID</span><span class="info-value">' + (r.network.ssid || 'N/A') + '</span></div>';
    html += '<div class="info-item"><span class="info-label">WiFi IP</span><span class="info-value">' + (r.network.ip || 'N/A') + '</span></div>';
    html += '<div class="info-item"><span class="info-label">WiFi Signal</span><span class="info-value">' + (r.network.signal || 0) + '%</span></div>';
    html += '<div class="info-item"><span class="info-label">Power Save</span><span class="info-value">' + (r.network.power_save || 'N/A') + '</span></div>';
  }
  if (r.system) {
    html += '<div class="info-item"><span class="info-label">CPU Temp</span><span class="info-value">' + r.system.cpu_temp + '&deg;C</span></div>';
    html += '<div class="info-item"><span class="info-label">USB Autosuspend</span><span class="info-value">' + r.system.autosuspend + '</span></div>';
    html += '<div class="info-item"><span class="info-label">Uptime</span><span class="info-value">' + (r.system.uptime || 'N/A') + '</span></div>';
    html += '<div class="info-item"><span class="info-label">Throttled</span><span class="info-value">' + (r.system.throttled || '0x0') + '</span></div>';
  }
  if (r.bt) {
    html += '<div class="info-item"><span class="info-label">BT Devices</span><span class="info-value">' + (r.bt.devices || 'none') + '</span></div>';
    html += '<div class="info-item"><span class="info-label">BT Discoverable</span><span class="info-value">' + (r.bt.discoverable ? 'Yes' : 'No') + '</span></div>';
  }
  document.getElementById('dbg-state').innerHTML = html || '<div class="empty-state">No data</div>';
}

async function dbgLogs(type) {
  var out = document.getElementById('dbg-output');
  out.style.display = 'block';
  out.textContent = 'Loading ' + type + '...';
  var r = await api('/api/debug/logs?type=' + encodeURIComponent(type));
  out.textContent = r.logs || r.error || 'No output';
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

    # Load night mode config from disk
    load_nightmode_config()

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

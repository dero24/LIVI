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

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'ringing': ring_state,
                'livi_connected': sio_connected
            }).encode())
        elif parsed.path == '/weather':
            weather = fetch_weather()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            if weather:
                self.wfile.write(json.dumps(weather).encode())
            else:
                self.wfile.write(json.dumps({'error': 'weather unavailable'}).encode())
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
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'notified', 'slot': slot}).encode())

        else:
            self.send_response(404)
            self.end_headers()


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

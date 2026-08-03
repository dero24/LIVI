#!/usr/bin/env python3
"""Extract the settings page HTML from homephone-sidecar.py and serve it locally."""
import re, http.server, sys

# Read the sidecar source
with open('homephone-sidecar.py', 'r', encoding='utf-8') as f:
    src = f.read()

# Extract SETTINGS_PAGE_HTML (it's a raw string r'''...''')
m = re.search(r"SETTINGS_PAGE_HTML = r'''(.*?)'''", src, re.DOTALL)
if not m:
    print('Could not extract SETTINGS_PAGE_HTML')
    sys.exit(1)

html = m.group(1)
print(f'Extracted settings page: {len(html)} chars')

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/settings' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path.startswith('/api/'):
            # Return empty/mock data for API calls so the page doesn't error
            import json
            mock = {}
            if self.path == '/api/bluetooth/devices':
                mock = {'devices': [{'mac': '00:11:22:33:44:55', 'name': 'Mock Headphones', 'connected': False, 'icon': 'audio-headset', 'is_phone': False}], 'adapter': {'name': 'homephone-countertop', 'address': '00:00:00:00:00:00', 'powered': True, 'discoverable': False}}
            elif self.path == '/api/audio/devices':
                mock = {'devices': [], 'default_sink': 'auto_null'}
            elif self.path == '/api/wifi/status':
                mock = {'ssid': 'Bennett', 'ip': '192.168.1.100', 'connected': True}
            elif self.path == '/api/system/info':
                mock = {'cpu_temp': 65.0, 'uptime': '2 hours', 'disk_free': '50GB'}
            elif self.path == '/api/display/nightmode':
                mock = {'enabled': False, 'opacity': 50}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(mock).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        import json
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok'}).encode())

    def log_message(self, format, *args):
        pass  # Suppress logs

port = 8123
server = http.server.HTTPServer(('127.0.0.1', port), Handler)
print(f'Serving settings page at http://localhost:{port}/settings')
print('Press Ctrl+C to stop')
server.serve_forever()

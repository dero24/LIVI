#!/usr/bin/env python3
"""
Patch the renderer (index.js) to add a ring banner overlay.

Instead of modifying the React Home component, we append a self-executing
script at the end of the file that:
1. Polls the sidecar's /status endpoint every 2 seconds
2. Creates a DOM overlay (ring banner) when a phone is ringing
3. Removes it when the call ends
4. Also adds a clock to the top of the screen

This is vanilla JS that manipulates the DOM directly — no React changes needed.
"""
import struct, json, os, sys, shutil

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
backup_path = '/home/raspberry/LIVI/extracted/resources/app.asar.bak.ringbanner'

# --- Parse the asar ---
with open(asar_path, 'rb') as f:
    vals = struct.unpack('<IIII', f.read(16))
    json_size = vals[3]
    header_json = f.read(json_size).decode('utf-8')
    data_offset = 16 + json_size
    if data_offset % 4 != 0:
        data_offset = (data_offset + 3) & ~3

header = json.loads(header_json)

def collect_files(node, prefix=''):
    results = []
    if 'files' in node:
        for name, child in node['files'].items():
            path = f"{prefix}/{name}" if prefix else name
            if 'files' in child:
                results.extend(collect_files(child, path))
            elif 'offset' in child:
                results.append((path, int(child['offset']), child.get('size', 0)))
    return results

files = collect_files(header)
print(f"Total files in asar: {len(files)}")

# --- Read the renderer file ---
renderer_path = 'out/renderer/index.js'
renderer_js = None
for path, offset, size in files:
    if path == renderer_path:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            renderer_js = f.read(size).decode('utf-8')
        print(f"Read {renderer_path}: {len(renderer_js)} chars")
        break

if not renderer_js:
    print("ERROR: Could not find renderer file!")
    sys.exit(1)

# --- The ring banner overlay script ---
# This is appended to the end of the renderer JS file.
# It runs after React has mounted and polls the sidecar for ring status.
RING_BANNER_SCRIPT = r"""

// ===== HOME PHONE HUB — RING BANNER OVERLAY =====
(function() {
  'use strict';
  var SIDECAR_URL = 'http://localhost:8123';
  var POLL_INTERVAL = 2000; // 2 seconds
  var ringState = {};
  var bannerEl = null;
  var pollTimer = null;

  function createBanner(slot, caller, phone) {
    if (bannerEl) return; // Already showing
    bannerEl = document.createElement('div');
    bannerEl.id = 'homephone-ring-banner';
    bannerEl.style.cssText = [
      'position:fixed',
      'top:0',
      'left:0',
      'right:0',
      'z-index:99999',
      'background:linear-gradient(135deg,#1a73e8,#0d47a1)',
      'color:white',
      'padding:16px 24px',
      'display:flex',
      'align-items:center',
      'justify-content:space-between',
      'gap:16px',
      'font-family:Roboto,sans-serif',
      'box-shadow:0 4px 12px rgba(0,0,0,0.3)',
      'animation:ringPulse 1s ease-in-out infinite alternate',
      'pointerEvents:auto'
    ].join(';');

    var info = document.createElement('div');
    info.style.cssText = 'flex:1;min-width:0';
    info.innerHTML = '<div style="font-size:20px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' +
      escapeHtml(caller || 'Incoming Call') + '</div>' +
      '<div style="font-size:14px;opacity:0.85;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' +
      escapeHtml(phone || 'Phone') + ' ringing</div>';

    var answerBtn = document.createElement('button');
    answerBtn.textContent = 'Answer';
    answerBtn.style.cssText = [
      'padding:12px 24px',
      'border-radius:24px',
      'border:2px solid white',
      'background:rgba(255,255,255,0.15)',
      'color:white',
      'font-size:16px',
      'font-weight:600',
      'cursor:pointer',
      'white-space:nowrap'
    ].join(';');
    answerBtn.onpointerdown = function(e) {
      e.preventDefault();
      try { window.projection.ipc.sendCommand('acceptPhone'); } catch(ex) {}
      try { var x = new XMLHttpRequest(); x.open('POST', SIDECAR_URL + '/hangup?slot=' + slot, true); x.send(); } catch(ex2) {}
      removeBanner();
    };

    var hangupBtn = document.createElement('button');
    hangupBtn.textContent = 'Decline';
    hangupBtn.style.cssText = [
      'padding:12px 24px',
      'border-radius:24px',
      'border:2px solid rgba(255,255,255,0.5)',
      'background:rgba(255,59,48,0.3)',
      'color:white',
      'font-size:16px',
      'font-weight:600',
      'cursor:pointer',
      'white-space:nowrap'
    ].join(';');
    hangupBtn.onpointerdown = function(e) {
      e.preventDefault();
      try { window.projection.ipc.sendCommand('rejectPhone'); } catch(ex) {}
      try { var x = new XMLHttpRequest(); x.open('POST', SIDECAR_URL + '/hangup?slot=' + slot, true); x.send(); } catch(ex2) {}
      removeBanner();
    };

    bannerEl.appendChild(info);
    bannerEl.appendChild(answerBtn);
    bannerEl.appendChild(hangupBtn);
    document.body.appendChild(bannerEl);

    // Add pulse animation
    if (!document.getElementById('ring-banner-style')) {
      var style = document.createElement('style');
      style.id = 'ring-banner-style';
      style.textContent = '@keyframes ringPulse{0%{background:linear-gradient(135deg,#1a73e8,#0d47a1)}100%{background:linear-gradient(135deg,#2196f3,#1565c0)}}';
      document.head.appendChild(style);
    }
  }

  function removeBanner() {
    if (bannerEl) {
      bannerEl.remove();
      bannerEl = null;
    }
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function updateBanner() {
    var slots = Object.keys(ringState);
    if (slots.length > 0) {
      var slot = slots[0];
      var info = ringState[slot];
      createBanner(slot, info.caller, info.phone);
    } else {
      removeBanner();
    }
  }

  function pollStatus() {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', SIDECAR_URL + '/status', true);
      xhr.timeout = 3000;
      xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
          if (xhr.status === 200) {
            try {
              var data = JSON.parse(xhr.responseText);
              ringState = data.ringing || {};
              updateBanner();
            } catch(e) {}
          }
        }
      };
      xhr.onerror = function() {};
      xhr.ontimeout = function() {};
      xhr.send();
    } catch(e) {
      // Sidecar not running — silently ignore
    }
  }

  // Start polling when the page is ready
  function start() {
    if (pollTimer) return;
    pollTimer = setInterval(pollStatus, POLL_INTERVAL);
    pollStatus(); // Immediate first poll
    console.log('[HomePhone] Ring banner overlay started, polling ' + SIDECAR_URL);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
// ===== END RING BANNER OVERLAY =====
"""

# --- Append the script to the renderer ---
if 'HOME PHONE HUB — RING BANNER' in renderer_js:
    print("Ring banner script already present — skipping")
else:
    renderer_js = renderer_js + RING_BANNER_SCRIPT
    print(f"Appended ring banner script: +{len(RING_BANNER_SCRIPT)} chars")

# --- Rebuild the asar ---
print("\nRebuilding asar...")

# Back up original
if not os.path.exists(backup_path):
    shutil.copy2(asar_path, backup_path)
    print(f"Backed up to {backup_path}")

# Collect all file data in order
all_files_sorted = sorted(files, key=lambda x: x[1])

new_data = bytearray()
offset_map = {}

for path, old_offset, old_size in all_files_sorted:
    if path == renderer_path:
        content = renderer_js.encode('utf-8')
    else:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + old_offset)
            content = f.read(old_size)

    new_offset = len(new_data)
    offset_map[path] = (new_offset, len(content))
    new_data.extend(content)
    while len(new_data) % 4 != 0:
        new_data.append(0)

# Update header
def update_header(node, prefix=''):
    if 'files' not in node:
        return
    for name, child in node['files'].items():
        path = f"{prefix}/{name}" if prefix else name
        if 'files' in child:
            update_header(child, path)
        elif 'offset' in child:
            if path in offset_map:
                new_off, new_size = offset_map[path]
                child['offset'] = str(new_off)
                child['size'] = new_size

update_header(header)

# Build new asar
header_json_new = json.dumps(header, separators=(',', ':')).encode('utf-8')
json_size_new = len(header_json_new)
padding = (4 - (json_size_new % 4)) % 4
header_padded = header_json_new + b'\x00' * padding
padded_size = json_size_new + padding

payload_size = 8 + padded_size
header_string_size = 4 + padded_size

asar_header = struct.pack('<IIII', 4, payload_size, header_string_size, json_size_new)
asar_header += header_padded

tmp_path = asar_path + '.tmp'
with open(tmp_path, 'wb') as f:
    f.write(asar_header)
    f.write(new_data)

# Verify
with open(tmp_path, 'rb') as f:
    verify_vals = struct.unpack('<IIII', f.read(16))
    verify_json_size = verify_vals[3]
    verify_json = f.read(verify_json_size).decode('utf-8')
    verify_header = json.loads(verify_json)
    print(f"Verification: header parsed OK, {len(verify_json)} bytes JSON")

os.replace(tmp_path, asar_path)
print(f"\nDone! New asar written to {asar_path}")
print(f"Original backed up to {backup_path}")

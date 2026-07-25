#!/usr/bin/env python3
"""
Patch the renderer (index.js) with the Home Hub UI v1 (working version)
plus device detection via onEvent and auto-return-to-hub on unplug.
"""
import struct, json, os, sys, shutil

asar_path = '/home/raspberry/LIVI/extracted/resources/app.asar'
backup_path = '/home/raspberry/LIVI/extracted/resources/app.asar.bak.homehub'

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

# Remove old patch if present
for marker in ['// ===== HOME PHONE HUB', '// ===== HOME PHONE HUB — RING BANNER']:
    idx = renderer_js.find(marker)
    if idx != -1:
        renderer_js = renderer_js[:idx]
        print(f"Trimmed at marker: {marker}")
        break

OVERLAY_SCRIPT = r"""

// ===== HOME PHONE HUB — DASHBOARD + RING BANNER =====
(function() {
  'use strict';
  var SIDECAR_URL = 'http://localhost:8123';
  var POLL_INTERVAL = 2000;
  var ringState = {};
  var bannerEl = null;
  var pollTimer = null;
  var hubEl = null;
  var phoneMode = false;
  var clockTimer = null;
  var currentDevices = []; // Track latest device list

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function sendCmd(cmd) {
    try { window.projection && window.projection.ipc && window.projection.ipc.sendCommand(cmd); } catch(e) {}
  }

  function xhrGet(url, cb) {
    try {
      var x = new XMLHttpRequest();
      x.open('GET', url, true);
      x.timeout = 3000;
      x.onreadystatechange = function() {
        if (x.readyState === 4 && x.status === 200) {
          try { cb(JSON.parse(x.responseText)); } catch(e) {}
        }
      };
      x.onerror = function() {};
      x.ontimeout = function() {};
      x.send();
    } catch(e) {}
  }

  function xhrPost(url) {
    try { var x = new XMLHttpRequest(); x.open('POST', url, true); x.send(); } catch(e) {}
  }

  // --- Clock ---
  function updateClock() {
    var now = new Date();
    var h = now.getHours();
    var m = now.getMinutes();
    var ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    var timeStr = h + ':' + (m < 10 ? '0' : '') + m;
    var days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var dateStr = days[now.getDay()] + ', ' + months[now.getMonth()] + ' ' + now.getDate();

    var timeEl = document.getElementById('homehub-time');
    var dateEl = document.getElementById('homehub-date');
    if (timeEl) timeEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
  }

  // --- Home Hub UI ---
  function createHub() {
    if (hubEl) return;

    hubEl = document.createElement('div');
    hubEl.id = 'homehub-overlay';
    hubEl.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:99998',
      'background:linear-gradient(180deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%)',
      'color:#e0e0e0',
      'font-family:Roboto,system-ui,sans-serif',
      'display:flex',
      'flex-direction:column',
      'overflow:hidden',
      'pointerEvents:auto'
    ].join(';');

    hubEl.innerHTML = `
      <style>
        #homehub-overlay * { box-sizing: border-box; }
        #homehub-time { font-size: 72px; font-weight: 300; letter-spacing: -2px; line-height: 1; }
        #homehub-date { font-size: 18px; opacity: 0.7; margin-top: 4px; }
        .homehub-section {
          background: rgba(255,255,255,0.06);
          border-radius: 20px;
          padding: 20px 24px;
          margin: 8px 16px;
          backdrop-filter: blur(10px);
        }
        .homehub-section-title {
          font-size: 13px;
          text-transform: uppercase;
          letter-spacing: 1px;
          opacity: 0.5;
          margin-bottom: 12px;
          font-weight: 600;
        }
        .homehub-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.12);
          border-radius: 18px;
          color: #e0e0e0;
          cursor: pointer;
          font-family: inherit;
          font-size: 11px;
          font-weight: 600;
          transition: background 150ms, transform 100ms;
          user-select: none;
          -webkit-user-select: none;
        }
        .homehub-btn:active { transform: scale(0.95); background: rgba(255,255,255,0.15); }
        .homehub-btn svg { width: 28px; height: 28px; }
        .homehub-btn.large svg { width: 36px; height: 36px; }
        .homehub-btn.large { font-size: 13px; }
        .homehub-device {
          display: flex;
          align-items: center;
          gap: 16px;
          background: rgba(255,255,255,0.08);
          border: 2px solid rgba(255,255,255,0.1);
          border-radius: 16px;
          padding: 16px 20px;
          cursor: pointer;
          transition: border-color 200ms, background 200ms;
        }
        .homehub-device:active { transform: scale(0.98); }
        .homehub-device.active { border-color: #4fc3f7; background: rgba(79,195,247,0.1); }
        .homehub-device-icon { font-size: 36px; }
        .homehub-device-info { flex: 1; min-width: 0; }
        .homehub-device-name { font-size: 18px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .homehub-device-status { font-size: 12px; opacity: 0.6; margin-top: 2px; }
        .homehub-phone-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          background: linear-gradient(135deg,#2196f3,#1565c0);
          border: none;
          border-radius: 16px;
          color: white;
          cursor: pointer;
          font-family: inherit;
          font-size: 16px;
          font-weight: 600;
          padding: 16px 32px;
          transition: transform 100ms, opacity 200ms;
        }
        .homehub-phone-btn:active { transform: scale(0.97); }
        .homehub-phone-btn svg { width: 24px; height: 24px; }
        @keyframes homehub-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
        .homehub-recording { animation: homehub-pulse 2s ease-in-out infinite; }
      </style>

      <!-- Header: Clock + Date -->
      <div style="text-align:center;padding:40px 16px 20px;flex-shrink:0">
        <div id="homehub-time">--:--</div>
        <div id="homehub-date">---</div>
      </div>

      <!-- Device Cards Section -->
      <div class="homehub-section" id="homehub-devices-section">
        <div class="homehub-section-title">Connected Phones</div>
        <div id="homehub-devices" style="display:flex;flex-direction:column;gap:10px">
          <div style="text-align:center;opacity:0.4;padding:20px">No phone connected</div>
        </div>
      </div>

      <!-- Media + Call Controls -->
      <div class="homehub-section" style="flex:1;display:flex;flex-direction:column;justify-content:center">
        <div class="homehub-section-title">Controls</div>
        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px">
          <button class="homehub-btn large" id="homehub-play" style="padding:18px 8px">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            <span id="homehub-play-label">Play</span>
          </button>
          <button class="homehub-btn large" id="homehub-next" style="padding:18px 8px">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-5L6 8v10zM16 6v12h2V6h-2z"/></svg>
            <span>Next</span>
          </button>
          <button class="homehub-btn large" id="homehub-prev" style="padding:18px 8px">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 5V7z"/></svg>
            <span>Prev</span>
          </button>
          <button class="homehub-btn large" id="homehub-answer" style="padding:18px 8px;background:rgba(76,175,80,0.15);border-color:rgba(76,175,80,0.3)">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z"/></svg>
            <span>Answer</span>
          </button>
          <button class="homehub-btn large" id="homehub-hangup" style="padding:18px 8px;background:rgba(244,67,54,0.15);border-color:rgba(244,67,54,0.3)">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 9c-1.6 0-3.15.25-4.6.7v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.1-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"/></svg>
            <span>Hang Up</span>
          </button>
          <button class="homehub-btn large" id="homehub-voice" style="padding:18px 8px">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z"/></svg>
            <span>Voice</span>
          </button>
        </div>
      </div>

      <!-- Open Phone Button -->
      <div style="padding:12px 16px 24px;flex-shrink:0;display:flex;justify-content:center">
        <button class="homehub-phone-btn" id="homehub-open-phone">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>
          <span>Open Phone</span>
        </button>
      </div>
    `;

    document.body.appendChild(hubEl);

    // Wire up buttons
    var playBtn = document.getElementById('homehub-play');
    var playLabel = document.getElementById('homehub-play-label');
    var isPlaying = false;
    playBtn.addEventListener('pointerdown', function() {
      isPlaying = !isPlaying;
      sendCmd(isPlaying ? 'pause' : 'play');
      playLabel.textContent = isPlaying ? 'Pause' : 'Play';
      playBtn.querySelector('svg').innerHTML = isPlaying
        ? '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>'
        : '<path d="M8 5v14l11-7z"/>';
    });

    document.getElementById('homehub-next').addEventListener('pointerdown', function() { sendCmd('next'); });
    document.getElementById('homehub-prev').addEventListener('pointerdown', function() { sendCmd('prev'); });
    document.getElementById('homehub-answer').addEventListener('pointerdown', function() { sendCmd('acceptPhone'); });
    document.getElementById('homehub-hangup').addEventListener('pointerdown', function() { sendCmd('rejectPhone'); });

    var voiceBtn = document.getElementById('homehub-voice');
    voiceBtn.addEventListener('pointerdown', function() { sendCmd('voiceAssistant'); voiceBtn.classList.add('homehub-recording'); });
    voiceBtn.addEventListener('pointerup', function() { sendCmd('voiceAssistantRelease'); voiceBtn.classList.remove('homehub-recording'); });
    voiceBtn.addEventListener('pointerleave', function() { sendCmd('voiceAssistantRelease'); voiceBtn.classList.remove('homehub-recording'); });

    document.getElementById('homehub-open-phone').addEventListener('pointerdown', function() {
      // Find first active or available device
      var activeDev = null;
      for (var i = 0; i < currentDevices.length; i++) {
        if (currentDevices[i].status === 'active' || currentDevices[i].status === 'available') {
          activeDev = currentDevices[i];
          break;
        }
      }
      if (activeDev && activeDev.status !== 'active') {
        // Select the device first, then switch to phone mode after a brief delay
        try {
          if (window.projection && window.projection.ipc && window.projection.ipc.selectDevice) {
            window.projection.ipc.selectDevice(activeDev.id);
          }
        } catch(e) {}
        // Wait for session to start before hiding hub
        setTimeout(function() { setPhoneMode(true); }, 1500);
      } else if (activeDev && activeDev.status === 'active') {
        // Already active — just switch view
        setPhoneMode(true);
      } else {
        // No device connected — flash the button to indicate error
        var btn = document.getElementById('homehub-open-phone');
        if (btn) {
          btn.style.background = 'rgba(244,67,54,0.5)';
          setTimeout(function() { btn.style.background = ''; }, 500);
        }
      }
    });

    // Start clock
    updateClock();
    clockTimer = setInterval(updateClock, 1000);
  }

  function setPhoneMode(mode) {
    phoneMode = mode;
    if (hubEl) {
      hubEl.style.display = mode ? 'none' : 'flex';
    }
    if (mode) {
      if (!document.getElementById('homehub-home-btn')) {
        var homeBtn = document.createElement('button');
        homeBtn.id = 'homehub-home-btn';
        homeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" style="width:24px;height:24px"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>';
        homeBtn.style.cssText = [
          'position:fixed',
          'top:16px',
          'right:16px',
          'z-index:99997',
          'background:rgba(0,0,0,0.6)',
          'border:1px solid rgba(255,255,255,0.2)',
          'border-radius:14px',
          'color:white',
          'cursor:pointer',
          'padding:12px',
          'display:flex',
          'align-items:center',
          'justify-content:center',
          'pointerEvents:auto'
        ].join(';');
        homeBtn.addEventListener('pointerdown', function() { setPhoneMode(false); });
        document.body.appendChild(homeBtn);
      }
      document.getElementById('homehub-home-btn').style.display = 'flex';
    } else {
      var hb = document.getElementById('homehub-home-btn');
      if (hb) hb.style.display = 'none';
    }
  }

  // --- LIVI event listener (devices + unplug) ---
  function registerLiviEvents() {
    try {
      if (!window.projection || !window.projection.ipc || !window.projection.ipc.onEvent) return;
      window.projection.ipc.onEvent(function(evt) {
        var args = Array.prototype.slice.call(arguments, 1);
        var msg = args[0] || {};
        if (msg.type === 'devices' && msg.payload) {
          var container = document.getElementById('homehub-devices');
          if (container) renderDevices(container, msg.payload);
        } else if (msg.type === 'unplugged' || msg.type === 'failure') {
          console.log('[HomePhone] LIVI event: ' + msg.type + ' — returning to hub');
          setPhoneMode(false);
          setTimeout(updateDevices, 500);
        }
      });
      console.log('[HomePhone] Registered LIVI onEvent listener');
    } catch(e) {
      console.warn('[HomePhone] Could not register onEvent: ' + e);
    }
  }

  // --- Device cards ---
  function updateDevices() {
    var container = document.getElementById('homehub-devices');
    if (!container) return;
    try {
      if (window.projection && window.projection.ipc && window.projection.ipc.getDevices) {
        window.projection.ipc.getDevices().then(function(devs) {
          renderDevices(container, devs);
        }).catch(function() { renderDevices(container, []); });
        return;
      }
    } catch(e) {}
    renderDevices(container, []);
  }

  function renderDevices(container, devices) {
    currentDevices = devices || [];
    if (!devices || devices.length === 0) {
      container.innerHTML = '<div style="text-align:center;opacity:0.4;padding:20px">No phone connected</div>';
      return;
    }
    var html = '';
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      var isActive = d.status === 'active';
      var isOffline = d.status === 'offline';
      var icon = d.protocol === 'androidauto' ? '🤖' : d.protocol === 'carplay' ? '📱' : '📲';
      var statusText = isActive ? 'Active' : isOffline ? 'Offline' : 'Available';
      var batteryText = (typeof d.batteryLevel === 'number') ? d.batteryLevel + '% battery' : '';
      html += '<div class="homehub-device' + (isActive ? ' active' : '') + '" data-device-id="' + escapeHtml(d.id) + '">' +
        '<div class="homehub-device-icon">' + icon + '</div>' +
        '<div class="homehub-device-info">' +
          '<div class="homehub-device-name">' + escapeHtml(d.name || d.model || d.id) + '</div>' +
          '<div class="homehub-device-status">' + escapeHtml(statusText) + (batteryText ? ' &middot; ' + batteryText : '') + '</div>' +
        '</div>' +
        '</div>';
    }
    container.innerHTML = html;
    var cards = container.querySelectorAll('.homehub-device');
    for (var j = 0; j < cards.length; j++) {
      (function(card) {
        card.addEventListener('pointerdown', function() {
          var id = card.getAttribute('data-device-id');
          try {
            if (window.projection && window.projection.ipc && window.projection.ipc.selectDevice) {
              window.projection.ipc.selectDevice(id);
            }
          } catch(e) {}
        });
      })(cards[j]);
    }
  }

  // --- Ring Banner ---
  function createBanner(slot, caller, phone) {
    if (bannerEl) return;
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
    answerBtn.style.cssText = 'padding:12px 24px;border-radius:24px;border:2px solid white;background:rgba(255,255,255,0.15);color:white;font-size:16px;font-weight:600;cursor:pointer;white-space:nowrap';
    answerBtn.onpointerdown = function(e) {
      e.preventDefault();
      sendCmd('acceptPhone');
      xhrPost(SIDECAR_URL + '/hangup?slot=' + slot);
      removeBanner();
    };
    var hangupBtn = document.createElement('button');
    hangupBtn.textContent = 'Decline';
    hangupBtn.style.cssText = 'padding:12px 24px;border-radius:24px;border:2px solid rgba(255,255,255,0.5);background:rgba(255,59,48,0.3);color:white;font-size:16px;font-weight:600;cursor:pointer;white-space:nowrap';
    hangupBtn.onpointerdown = function(e) {
      e.preventDefault();
      sendCmd('rejectPhone');
      xhrPost(SIDECAR_URL + '/hangup?slot=' + slot);
      removeBanner();
    };
    bannerEl.appendChild(info);
    bannerEl.appendChild(answerBtn);
    bannerEl.appendChild(hangupBtn);
    document.body.appendChild(bannerEl);
    if (!document.getElementById('ring-banner-style')) {
      var style = document.createElement('style');
      style.id = 'ring-banner-style';
      style.textContent = '@keyframes ringPulse{0%{background:linear-gradient(135deg,#1a73e8,#0d47a1)}100%{background:linear-gradient(135deg,#2196f3,#1565c0)}}';
      document.head.appendChild(style);
    }
  }

  function removeBanner() {
    if (bannerEl) { bannerEl.remove(); bannerEl = null; }
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

  // --- Polling ---
  function pollStatus() {
    xhrGet(SIDECAR_URL + '/status', function(data) {
      ringState = data.ringing || {};
      updateBanner();
    });
  }

  // --- Start ---
  function start() {
    if (pollTimer) return;
    createHub();
    registerLiviEvents();
    pollTimer = setInterval(pollStatus, POLL_INTERVAL);
    pollStatus();
    setInterval(updateDevices, 5000);
    updateDevices();
    console.log('[HomePhone] Home hub UI started');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    setTimeout(start, 1000);
  }
})();
// ===== END HOME PHONE HUB =====
"""

renderer_js = renderer_js + OVERLAY_SCRIPT
print(f"Appended overlay script: +{len(OVERLAY_SCRIPT)} chars")

# --- Rebuild the asar ---
print("\nRebuilding asar...")

if not os.path.exists(backup_path):
    shutil.copy2(asar_path, backup_path)
    print(f"Backed up to {backup_path}")

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

with open(tmp_path, 'rb') as f:
    verify_vals = struct.unpack('<IIII', f.read(16))
    verify_json_size = verify_vals[3]
    verify_json = f.read(verify_json_size).decode('utf-8')
    verify_header = json.loads(verify_json)
    print(f"Verification: header parsed OK, {len(verify_json)} bytes JSON")

os.replace(tmp_path, asar_path)
print(f"\nDone! New asar written to {asar_path}")

#!/usr/bin/env python3
"""
Patch the renderer (index.js) with the Home Hub UI v2 — Master Phone Layout.

Key changes from v1:
- Portrait 600x1024 AA rendering (config change, not here)
- Hub bar covers top 424px only (not full screen)
- Phone video always visible in bottom 600px (no "Open Phone" button, no phone mode)
- LIVI's built-in view area (projectionViewAreaTop=424) handles touch mapping natively
- No custom touch remapping needed
- Device selector pills (compact, horizontal)
- No car-style media control buttons (phone UI handles media)
- Screensaver placeholder in bottom 600px when no phone connected
- Ring banner appears within the 424px hub bar
- Sleek, modern, appliance-like aesthetic (not a car dashboard)
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

// ===== HOME PHONE HUB v2 — MASTER PHONE LAYOUT =====
(function() {
  'use strict';
  var SIDECAR_URL = 'http://127.0.0.1:8123';
  var POLL_INTERVAL = 2000;
  var HUB_HEIGHT = 450;
  var PHONE_HEIGHT = 574;

  var ringState = {};
  var pollTimer = null;
  var barEl = null;
  var screensaverEl = null;
  var ringEl = null;
  var clockTimer = null;
  var currentDevices = [];
  var masterDeviceId = null;
  var phoneConnected = false;   // phone is physically plugged in & projecting
  var viewingAA = false;        // user is viewing the AA/CarPlay screen (not home)
  var phoneNames = {}; // deviceId -> user-defined name (persisted in localStorage)
  var phoneSlots = {}; // slot number -> deviceId (mapped by dock order)
  var registrationHandled = {};

  // --- Load/save phone names ---
  function loadPhoneNames() {
    try {
      var saved = localStorage.getItem('homehub.phoneNames');
      if (saved) phoneNames = JSON.parse(saved) || {};
    } catch(e) { phoneNames = {}; }
  }
  function savePhoneNames() {
    try { localStorage.setItem('homehub.phoneNames', JSON.stringify(phoneNames)); } catch(e) {}
  }
  function getPhoneName(deviceId, fallback) {
    if (phoneNames[deviceId]) return phoneNames[deviceId];
    return fallback || 'Phone';
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
    var months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    var dateStr = days[now.getDay()] + ', ' + months[now.getMonth()] + ' ' + now.getDate();

    var timeEl = document.getElementById('hub-time');
    var dateEl = document.getElementById('hub-date');
    var ssTime = document.getElementById('hub-ss-time');
    var ssDate = document.getElementById('hub-ss-date');
    if (timeEl) timeEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
    if (ssTime) ssTime.textContent = timeStr + ' ' + ampm;
    if (ssDate) ssDate.textContent = dateStr;
  }

  // --- SVG Icons ---
  var SVG = {
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    phoneFill: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    answer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    decline: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="23" y1="1" x2="1" y2="23"/><path d="M21.21 4.39a19.79 19.79 0 0 0-8.63-3.07A19.5 19.5 0 0 0 6.61 4.39M3.54 7.46a19.79 19.79 0 0 0-3.07 8.67M12 2v4M19 5l-2 2M5 19l-2 2"/></svg>',
    music: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    battery: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="6" width="18" height="12" rx="2" ry="2"/><line x1="23" y1="13" x2="23" y2="11"/></svg>',
    bolt: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>'
  };

  // --- Hub Bar (top 424px) ---
  function createHub() {
    if (barEl) return;

    barEl = document.createElement('div');
    barEl.id = 'homehub-bar';
    barEl.style.cssText = [
      'position:fixed',
      'top:0',
      'left:0',
      'right:0',
      'height:' + HUB_HEIGHT + 'px',
      'z-index:99998',
      'background:#0d1117',
      'color:#e6edf3',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
      'display:flex',
      'flex-direction:column',
      'overflow:hidden',
      'pointer-events:auto',
      'user-select:none',
      '-webkit-user-select:none'
    ].join(';');

    barEl.innerHTML = `
      <style>
        #homehub-bar * { box-sizing: border-box; margin: 0; }
        #homehub-bar { padding: 0; }

        /* When no phone is connected, hide LIVI's built-in UI to prevent
           the "flash" of LIVI's Home page during unplug transitions.
           Our full-screen screensaver (z-index 99999) covers everything,
           but this ensures LIVI's content/nav roots are truly invisible.
           NOTE: We do NOT hide #projection-root — the AA/CarPlay video canvas
           must remain visible (just covered by the screensaver) so LIVI's
           hardware video decoder can render into it. If we hide it with
           visibility:hidden, the decoder may not produce frames, and when
           the user taps a phone bubble to reveal AA, the screen will show
           LIVI's homepage instead of the phone's AA/CarPlay video. */
        body.homehub-no-phone #content-root { visibility: hidden !important; }
        body.homehub-no-phone #nav-root { visibility: hidden !important; }

        /* Header: Clock + Weather — matches screensaver aesthetic */
        #hub-header {
          display: flex; align-items: flex-start; justify-content: space-between;
          padding: 36px 40px 0;
          flex-shrink: 0;
        }
        #hub-time {
          font-size: 72px; font-weight: 200; letter-spacing: -3px; line-height: 1;
          color: #f0f6fc; opacity: 0.95;
        }
        #hub-date {
          font-size: 18px; font-weight: 300; color: #8b949e; margin-top: 8px; letter-spacing: 0.5px;
        }
        #hub-weather {
          display: flex; flex-direction: column; align-items: flex-end; gap: 4px;
        }
        #hub-weather-temp { font-size: 32px; font-weight: 200; color: #f0f6fc; opacity: 0.95; }
        #hub-weather-cond { font-size: 14px; font-weight: 300; color: #8b949e; }
        #hub-weather-icon { font-size: 24px; }

        /* Device bubbles — clean, minimal, no label */
        #hub-devices-wrap {
          padding: 32px 40px 0;
          flex-shrink: 0;
        }
        #hub-devices {
          display: flex; gap: 16px; flex-wrap: nowrap; overflow-x: auto;
          align-items: center;
        }
        #hub-devices::-webkit-scrollbar { display: none; }

        /* Phone bubble — matches the dark, minimal aesthetic */
        .hub-pill {
          display: inline-flex; align-items: center; gap: 18px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.05);
          border-radius: 30px;
          padding: 20px 52px 20px 20px;
          cursor: pointer;
          transition: all 250ms cubic-bezier(0.4,0,0.2,1);
          white-space: nowrap;
          flex-shrink: 0;
          box-sizing: border-box;
          min-height: 88px;
        }
        .hub-pill:active { transform: scale(0.96); }

        /* Avatar circle with initial */
        .hub-pill-avatar {
          width: 64px; height: 64px; border-radius: 50%;
          background: rgba(255,255,255,0.06);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
          font-size: 30px; font-weight: 300; color: #8b949e;
          transition: all 250ms ease;
          box-sizing: border-box;
        }
        .hub-pill-text {
          display: flex; flex-direction: column; gap: 6px;
          flex-shrink: 0;
          box-sizing: border-box;
          padding-right: 12px;
        }
        .hub-pill-name {
          font-size: 24px; font-weight: 400; color: #8b949e;
          letter-spacing: 0.3px;
          line-height: 1.2;
          display: block;
        }
        .hub-pill-batt {
          font-size: 15px; font-weight: 300; color: #484f58; display: flex; align-items: center; gap: 5px;
          line-height: 1.2;
        }
        .hub-pill-batt svg { width: 18px; height: 18px; }
        .hub-pill-batt .bolt { width: 12px; height: 12px; color: #3fb950; }

        /* Active (master) phone — subtle blue, not heavy */
        .hub-pill.active {
          background: rgba(88,166,255,0.08);
          border-color: rgba(88,166,255,0.2);
        }
        .hub-pill.active .hub-pill-avatar {
          background: rgba(88,166,255,0.15);
          color: #58a6ff;
        }
        .hub-pill.active .hub-pill-name { color: #f0f6fc; font-weight: 500; }
        .hub-pill.active .hub-pill-batt { color: #8b949e; }

        /* Ringing phone — red pulse glow */
        .hub-pill.ringing {
          background: rgba(255,107,107,0.1);
          border-color: rgba(255,107,107,0.35);
          animation: hub-pill-ring-pulse 1.5s ease-in-out infinite;
        }
        @keyframes hub-pill-ring-pulse {
          0%,100% {
            border-color: rgba(255,107,107,0.25);
            box-shadow: 0 0 0 0 rgba(255,107,107,0);
          }
          50% {
            border-color: rgba(255,107,107,0.6);
            box-shadow: 0 0 24px 6px rgba(255,107,107,0.15);
          }
        }
        .hub-pill.ringing .hub-pill-avatar {
          background: rgba(255,107,107,0.15);
          color: #ff6b6b;
          animation: hub-pill-avatar-pulse 1.5s ease-in-out infinite;
        }
        @keyframes hub-pill-avatar-pulse {
          0%,100% { transform: scale(1); }
          50% { transform: scale(1.08); }
        }
        .hub-pill.ringing .hub-pill-name { color: #ff6b6b; font-weight: 500; }

        /* Active AND ringing — ringing takes priority */
        .hub-pill.active.ringing {
          background: rgba(255,107,107,0.1);
          border-color: rgba(255,107,107,0.35);
        }

        .hub-pill-empty {
          font-size: 15px; font-weight: 300; color: #484f58; padding: 10px 4px;
        }

        #hub-bottom {
          flex: 1; display: flex; flex-direction: column; justify-content: flex-end;
          padding: 0 40px 28px;
        }

        /* Now Playing — minimal, no card, just text like screensaver hint */
        #hub-nowplaying {
          display: flex; align-items: center; gap: 14px;
          padding: 0;
          background: transparent;
          border-radius: 0;
          border: none;
        }
        #hub-np-icon { width: 22px; height: 22px; color: #484f58; flex-shrink: 0; }
        #hub-np-info { flex: 1; min-width: 0; }
        #hub-np-title {
          font-size: 16px; font-weight: 400; color: #8b949e;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        #hub-np-artist {
          font-size: 14px; font-weight: 300; color: #484f58; margin-top: 3px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        /* Ring Banner */
        #hub-ring {
          display: none;
          flex-direction: column; gap: 14px;
          padding: 16px 20px;
          background: linear-gradient(135deg,rgba(255,107,107,0.15),rgba(255,68,68,0.08));
          border-radius: 16px;
          border: 1px solid rgba(255,107,107,0.3);
          animation: hub-ring-pulse 2s ease-in-out infinite;
        }
        @keyframes hub-ring-pulse {
          0%,100% { border-color: rgba(255,107,107,0.3); }
          50% { border-color: rgba(255,107,107,0.6); }
        }
        #hub-ring-info {
          display: flex; align-items: center; gap: 12px;
        }
        #hub-ring-caller-icon {
          width: 40px; height: 40px; border-radius: 50%;
          background: rgba(255,107,107,0.2);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
        }
        #hub-ring-caller-icon svg { width: 22px; height: 22px; color: #ff6b6b; }
        #hub-ring-text { flex: 1; min-width: 0; }
        #hub-ring-caller {
          font-size: 18px; font-weight: 600; color: #f0f6fc;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        #hub-ring-phone {
          font-size: 13px; color: #8b949e; margin-top: 2px;
        }
        #hub-ring-buttons { display: flex; gap: 12px; }
        .hub-ring-btn {
          flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px;
          padding: 12px; border-radius: 12px; border: none;
          font-family: inherit; font-size: 15px; font-weight: 600;
          cursor: pointer; transition: transform 100ms, opacity 200ms;
        }
        .hub-ring-btn:active { transform: scale(0.96); }
        .hub-ring-btn svg { width: 20px; height: 20px; }
        #hub-ring-decline {
          background: rgba(255,68,68,0.15); color: #ff6b6b;
          border: 1px solid rgba(255,68,68,0.3);
        }
        #hub-ring-answer {
          background: rgba(63,185,80,0.15); color: #3fb950;
          border: 1px solid rgba(63,185,80,0.3);
        }

        /* No phone hint in hub bar */
        #hub-nophone-hint {
          display: none;
          font-size: 13px; color: #484f58; text-align: center;
          padding: 12px 0;
        }
      </style>

      <!-- Header: Clock + Weather + Settings -->
      <div id="hub-header">
        <div>
          <div id="hub-time">--:--</div>
          <div id="hub-date">---</div>
        </div>
        <div style="display:flex;align-items:flex-start;gap:20px">
          <div id="hub-weather">
            <div id="hub-weather-temp">--&deg;</div>
            <div id="hub-weather-cond"><span id="hub-weather-icon">--</span></div>
          </div>
          <div id="hub-home-btn" onclick="homehubGoHome()" style="
            width:44px;height:44px;border-radius:12px;
            border:1px solid #21262d;background:rgba(22,27,34,0.6);
            display:flex;align-items:center;justify-content:center;
            cursor:pointer;transition:all 0.2s;opacity:0.5;
          " onmouseover="this.style.opacity=1;this.style.background='rgba(22,27,34,0.9)'"
            onmouseout="this.style.opacity=0.5;this.style.background='rgba(22,27,34,0.6)'">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8b949e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          </div>
          <div id="hub-settings-btn" onclick="homehubOpenSettings()" style="
            width:44px;height:44px;border-radius:12px;
            border:1px solid #21262d;background:rgba(22,27,34,0.6);
            display:flex;align-items:center;justify-content:center;
            cursor:pointer;transition:all 0.2s;opacity:0.5;
          " onmouseover="this.style.opacity=1;this.style.background='rgba(22,27,34,0.9)'"
            onmouseout="this.style.opacity=0.5;this.style.background='rgba(22,27,34,0.6)'">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8b949e" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 1v6m0 10v6m11-11h-6M7 12H1m17.4-7.4l-4.2 4.2M9.8 14.2l-4.2 4.2m12.8 0l-4.2-4.2M9.8 9.8L5.6 5.6"/>
            </svg>
          </div>
        </div>
      </div>

      <!-- Device Bubbles (no label — the bubbles speak for themselves) -->
      <div id="hub-devices-wrap">
        <div id="hub-devices">
          <div class="hub-pill-empty">No phone connected</div>
        </div>
      </div>

      <!-- Bottom: Now Playing (minimal, no card) -->
      <div id="hub-bottom">
        <div id="hub-nowplaying">
          <div id="hub-np-icon">${SVG.music}</div>
          <div id="hub-np-info">
            <div id="hub-np-title">Nothing playing</div>
            <div id="hub-np-artist">Connect a phone to start</div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(barEl);
  }

  // --- Screensaver (full screen when no phone, hidden when phone connected) ---
  function createScreensaver() {
    if (screensaverEl) return;

    screensaverEl = document.createElement('div');
    screensaverEl.id = 'homehub-screensaver';
    screensaverEl.style.cssText = [
      'position:fixed',
      'top:0',
      'left:0',
      'right:0',
      'bottom:0',
      'z-index:99999',
      'background:#0d1117',
      'color:#e6edf3',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
      'display:flex',
      'flex-direction:column',
      'align-items:center',
      'justify-content:center',
      'pointer-events:auto',
      'user-select:none',
      '-webkit-user-select:none',
      'transition:opacity 400ms ease'
    ].join(';');

    screensaverEl.innerHTML = `
      <style>
        #homehub-screensaver * { box-sizing: border-box; margin: 0; padding: 0; }
        #hub-ss-time {
          font-size: 120px; font-weight: 200; letter-spacing: -5px; line-height: 1;
          color: #f0f6fc; opacity: 0.95;
        }
        #hub-ss-date {
          font-size: 24px; font-weight: 300; color: #8b949e; margin-top: 16px;
          letter-spacing: 0.5px;
        }
        #hub-ss-hint {
          margin-top: 64px;
          font-size: 16px; color: #484f58; text-align: center;
          display: flex; align-items: center; gap: 10px;
        }
        #hub-ss-hint svg { width: 22px; height: 22px; }
        #hub-ss-devices {
          display: flex; gap: 16px; max-width: calc(100% - 64px);
          margin-top: 28px; overflow-x: auto; align-items: center;
        }
        #hub-ss-devices::-webkit-scrollbar { display: none; }
        #hub-ss-devices .hub-pill { padding: 16px 32px 16px 16px; min-height: 76px; }
        #hub-ss-devices .hub-pill-avatar { width: 52px; height: 52px; font-size: 24px; }
        #hub-ss-devices .hub-pill-name { font-size: 20px; }
        #hub-ss-settings {
          position: absolute; top: 24px; right: 24px;
          width: 44px; height: 44px; border-radius: 12px;
          border: 1px solid #21262d; background: rgba(22,27,34,0.4);
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; transition: all 0.2s; opacity: 0.3;
        }
        #hub-ss-settings:hover { opacity: 1; background: rgba(22,27,34,0.8); }
        #hub-ss-settings:active { transform: scale(0.93); }
      </style>
      <div id="hub-ss-settings" onclick="homehubOpenSettings()">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8b949e" stroke-width="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 1v6m0 10v6m11-11h-6M7 12H1m17.4-7.4l-4.2 4.2M9.8 14.2l-4.2 4.2m12.8 0l-4.2-4.2M9.8 9.8L5.6 5.6"/>
        </svg>
      </div>
      <div id="hub-ss-time">--:--</div>
      <div id="hub-ss-date">---</div>
      <div id="hub-ss-hint">${SVG.phone} Dock a phone to get started</div>
      <div id="hub-ss-devices"></div>
    `;

    document.body.appendChild(screensaverEl);
  }

  // --- Ring Banner (separate floating element, works in both states) ---
  function createRingBanner() {
    if (ringEl) return;

    ringEl = document.createElement('div');
    ringEl.id = 'homehub-ring';
    ringEl.style.cssText = [
      'position:fixed',
      'left:50%',
      'transform:translateX(-50%)',
      'z-index:100000',
      'display:none',
      'flex-direction:column',
      'gap:14px',
      'padding:20px 24px',
      'width:520px',
      'max-width:calc(100% - 32px)',
      'background:linear-gradient(135deg,rgba(40,20,25,0.95),rgba(30,15,20,0.95))',
      'border-radius:20px',
      'border:1px solid rgba(255,107,107,0.3)',
      'box-shadow:0 8px 32px rgba(0,0,0,0.5),0 0 40px rgba(255,107,107,0.1)',
      'animation:hub-ring-pulse 2s ease-in-out infinite',
      'backdrop-filter:blur(20px)',
      '-webkit-backdrop-filter:blur(20px)',
      'color:#e6edf3',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
      'pointer-events:auto',
      'user-select:none',
      '-webkit-user-select:none'
    ].join(';');

    ringEl.innerHTML = `
      <style>
        @keyframes hub-ring-pulse {
          0%,100% { border-color: rgba(255,107,107,0.3); box-shadow: 0 8px 32px rgba(0,0,0,0.5),0 0 40px rgba(255,107,107,0.1); }
          50% { border-color: rgba(255,107,107,0.6); box-shadow: 0 8px 32px rgba(0,0,0,0.5),0 0 60px rgba(255,107,107,0.2); }
        }
        #homehub-ring * { box-sizing: border-box; margin: 0; padding: 0; }
        #hub-ring-info {
          display: flex; align-items: center; gap: 14px;
        }
        #hub-ring-caller-icon {
          width: 48px; height: 48px; border-radius: 50%;
          background: rgba(255,107,107,0.2);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0;
        }
        #hub-ring-caller-icon svg { width: 26px; height: 26px; color: #ff6b6b; }
        #hub-ring-text { flex: 1; min-width: 0; }
        #hub-ring-caller {
          font-size: 22px; font-weight: 600; color: #f0f6fc;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        #hub-ring-phone {
          font-size: 14px; color: #8b949e; margin-top: 4px;
        }
        #hub-ring-buttons { display: flex; gap: 12px; }
        .hub-ring-btn {
          flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px;
          padding: 14px; border-radius: 14px; border: none;
          font-family: inherit; font-size: 16px; font-weight: 600;
          cursor: pointer; transition: transform 100ms, opacity 200ms;
        }
        .hub-ring-btn:active { transform: scale(0.96); }
        .hub-ring-btn svg { width: 22px; height: 22px; }
        #hub-ring-decline {
          background: rgba(255,68,68,0.15); color: #ff6b6b;
          border: 1px solid rgba(255,68,68,0.3);
        }
        #hub-ring-answer {
          background: rgba(63,185,80,0.15); color: #3fb950;
          border: 1px solid rgba(63,185,80,0.3);
        }
      </style>
      <div id="hub-ring-info">
        <div id="hub-ring-caller-icon">${SVG.phoneFill}</div>
        <div id="hub-ring-text">
          <div id="hub-ring-caller">Unknown Caller</div>
          <div id="hub-ring-phone">---</div>
        </div>
      </div>
      <div id="hub-ring-buttons">
        <button id="hub-ring-decline" class="hub-ring-btn">${SVG.decline} Decline</button>
        <button id="hub-ring-answer" class="hub-ring-btn">${SVG.answer} Answer</button>
      </div>
    `;

    document.body.appendChild(ringEl);

    var declineBtn = document.getElementById('hub-ring-decline');
    var answerBtn = document.getElementById('hub-ring-answer');
    if (declineBtn) declineBtn.addEventListener('click', function() {
      sendCmd('rejectPhone');
      xhrPost(SIDECAR_URL + '/hangup?slot=1');
    });
    if (answerBtn) answerBtn.addEventListener('click', function() {
      sendCmd('acceptPhone');
      xhrPost(SIDECAR_URL + '/hangup?slot=1');
    });
  }

  // --- Phone Registration Prompt (with on-screen touch keyboard) ---
  var registrationEl = null;
  var pendingRegistrationDeviceId = null; // Device waiting for registration
  var registrationCompleteCallback = null; // Called after registration completes

  function showRegistrationPrompt(deviceId, defaultName, onComplete) {
    if (registrationEl) return; // Already showing
    if (phoneNames[deviceId]) { if (onComplete) onComplete(); return; } // Already registered

    pendingRegistrationDeviceId = deviceId;
    registrationCompleteCallback = onComplete;

    registrationEl = document.createElement('div');
    registrationEl.id = 'homehub-register';
    registrationEl.style.cssText = [
      'position:fixed',
      'top:0','left:0','right:0','bottom:0',
      'z-index:100001',
      'background:rgba(13,17,23,0.95)',
      'backdrop-filter:blur(20px)',
      '-webkit-backdrop-filter:blur(20px)',
      'color:#e6edf3',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
      'display:flex',
      'flex-direction:column',
      'align-items:center',
      'justify-content:center',
      'pointer-events:auto',
      'user-select:none',
      '-webkit-user-select:none'
    ].join(';');

    // Build keyboard rows
    var kbRows = [
      'QWERTYUIOP',
      'ASDFGHJKL',
      'ZXCVBNM'
    ];

    var kbHtml = '';
    for (var r = 0; r < kbRows.length; r++) {
      var rowLetters = kbRows[r];
      var rowHtml = '<div class="hub-kb-row">';
      // Add shift on last row
      if (r === 2) {
        rowHtml += '<button class="hub-kb-key hub-kb-shift" data-action="shift">shift</button>';
      }
      for (var c = 0; c < rowLetters.length; c++) {
        rowHtml += '<button class="hub-kb-key" data-letter="' + rowLetters[c] + '">' + rowLetters[c].toLowerCase() + '</button>';
      }
      // Add backspace on last row
      if (r === 2) {
        rowHtml += '<button class="hub-kb-key hub-kb-back" data-action="back">&#9003;</button>';
      }
      rowHtml += '</div>';
      kbHtml += rowHtml;
    }
    // Space bar row
    kbHtml += '<div class="hub-kb-row"><button class="hub-kb-key hub-kb-space" data-action="space">space</button></div>';

    registrationEl.innerHTML = `
      <style>
        #homehub-register * { box-sizing: border-box; margin: 0; padding: 0; }
        #hub-reg-card {
          background:rgba(22,27,34,0.98);
          border:1px solid rgba(88,166,255,0.3);
          border-radius:24px;
          padding:36px 32px 28px;
          width:520px;
          max-width:calc(100% - 32px);
          box-shadow:0 12px 48px rgba(0,0,0,0.6);
        }
        #hub-reg-title {
          font-size: 24px; font-weight: 600; color: #f0f6fc; margin-bottom: 8px;
          text-align: center;
        }
        #hub-reg-subtitle {
          font-size: 15px; color: #8b949e; margin-bottom: 24px; text-align: center;
        }
        #hub-reg-display {
          width: 100%; padding: 16px 20px;
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.12);
          border-radius: 14px;
          color: #f0f6fc; font-size: 22px; font-family: inherit; font-weight: 500;
          text-align: center;
          min-height: 56px;
          display: flex; align-items: center; justify-content: center;
          margin-bottom: 24px;
          transition: border-color 200ms;
        }
        #hub-reg-display.empty { color: #484f58; font-weight: 300; font-size: 18px; }
        #hub-reg-display .cursor { display: inline-block; width: 2px; height: 24px; background: #58a6ff; margin-left: 2px; animation: hub-cursor-blink 1s step-end infinite; }
        @keyframes hub-cursor-blink { 0%,50% { opacity: 1; } 51%,100% { opacity: 0; } }

        #hub-kb { margin-bottom: 20px; }
        .hub-kb-row { display: flex; justify-content: center; gap: 6px; margin-bottom: 6px; }
        .hub-kb-key {
          min-width: 44px; height: 52px;
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 10px;
          color: #e6edf3; font-family: inherit; font-size: 18px; font-weight: 500;
          cursor: pointer; transition: background 100ms, transform 80ms;
          display: flex; align-items: center; justify-content: center;
          flex: 1; max-width: 60px;
        }
        .hub-kb-key:active { background: rgba(88,166,255,0.2); transform: scale(0.92); }
        .hub-kb-key.uppercase { text-transform: uppercase; }
        .hub-kb-shift, .hub-kb-back {
          flex: 1.5; max-width: 80px; font-size: 14px; color: #8b949e;
          background: rgba(255,255,255,0.04);
        }
        .hub-kb-shift.active { background: rgba(88,166,255,0.15); color: #58a6ff; }
        .hub-kb-space { flex: 4; max-width: 280px; }
        #hub-reg-buttons { display: flex; gap: 12px; }
        #hub-reg-skip {
          flex: 0 0 auto; padding: 14px 24px; border-radius: 14px;
          background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
          color: #8b949e; font-family: inherit; font-size: 16px; font-weight: 500;
          cursor: pointer;
        }
        #hub-reg-save {
          flex: 1; padding: 14px 24px; border-radius: 14px;
          background: rgba(88,166,255,0.15); border: 1px solid rgba(88,166,255,0.4);
          color: #58a6ff; font-family: inherit; font-size: 16px; font-weight: 600;
          cursor: pointer;
        }
        #hub-reg-save:active, #hub-reg-skip:active { transform: scale(0.97); }
        #hub-reg-save.disabled { opacity: 0.4; pointer-events: none; }
      </style>
      <div id="hub-reg-card">
        <div id="hub-reg-title">New Phone Detected</div>
        <div id="hub-reg-subtitle">Name this phone so the hub can identify it during calls</div>
        <div id="hub-reg-display" class="empty"><span id="hub-reg-text"></span><span class="cursor"></span></div>
        <div id="hub-kb">${kbHtml}</div>
        <div id="hub-reg-buttons">
          <button id="hub-reg-skip">Skip</button>
          <button id="hub-reg-save" class="disabled">Save Name</button>
        </div>
      </div>
    `;

    document.body.appendChild(registrationEl);

    // --- Touch keyboard logic ---
    var typedText = '';
    var shiftActive = false;
    var textSpan = document.getElementById('hub-reg-text');
    var displayEl = document.getElementById('hub-reg-display');
    var saveBtn = document.getElementById('hub-reg-save');
    var skipBtn = document.getElementById('hub-reg-skip');

    function updateDisplay() {
      if (textSpan) textSpan.textContent = typedText;
      if (displayEl) {
        if (typedText.length > 0) {
          displayEl.classList.remove('empty');
        } else {
          displayEl.classList.add('empty');
        }
      }
      if (saveBtn) {
        if (typedText.trim().length > 0) {
          saveBtn.classList.remove('disabled');
        } else {
          saveBtn.classList.add('disabled');
        }
      }
    }

    function typeLetter(letter) {
      if (typedText.length >= 30) return;
      typedText += shiftActive ? letter.toUpperCase() : letter.toLowerCase();
      if (shiftActive) {
        shiftActive = false;
        var shiftBtn = registrationEl.querySelector('.hub-kb-shift');
        if (shiftBtn) shiftBtn.classList.remove('active');
      }
      updateDisplay();
    }

    function typeBackspace() {
      typedText = typedText.slice(0, -1);
      updateDisplay();
    }

    function typeSpace() {
      if (typedText.length >= 30) return;
      if (typedText.length === 0) return; // No leading space
      typedText += ' ';
      updateDisplay();
    }

    function toggleShift() {
      shiftActive = !shiftActive;
      var shiftBtn = registrationEl.querySelector('.hub-kb-shift');
      if (shiftBtn) shiftBtn.classList.toggle('active', shiftActive);
    }

    // Attach keyboard handlers
    var keys = registrationEl.querySelectorAll('.hub-kb-key');
    for (var i = 0; i < keys.length; i++) {
      (function(key) {
        key.addEventListener('click', function() {
          var letter = key.getAttribute('data-letter');
          var action = key.getAttribute('data-action');
          if (letter) {
            typeLetter(letter);
          } else if (action === 'back') {
            typeBackspace();
          } else if (action === 'space') {
            typeSpace();
          } else if (action === 'shift') {
            toggleShift();
          }
        });
      })(keys[i]);
    }

    updateDisplay();

    // --- Save / Skip ---
    function closeAndSave(save) {
      if (save && typedText.trim()) {
        phoneNames[deviceId] = typedText.trim();
        savePhoneNames();
      }
      if (registrationEl) {
        registrationEl.remove();
        registrationEl = null;
      }
      pendingRegistrationDeviceId = null;
      var cb = registrationCompleteCallback;
      registrationCompleteCallback = null;
      if (cb) cb();
    }

    if (saveBtn) saveBtn.addEventListener('click', function() {
      if (typedText.trim().length > 0) closeAndSave(true);
    });
    if (skipBtn) skipBtn.addEventListener('click', function() { closeAndSave(false); });
  }

  // --- Device pills rendering ---
  // Bubbles show avatar (first initial), name, and battery.
  // Active phone = blue highlight. Ringing phone = red pulse.
  function renderDevices() {
    var containers = [document.getElementById('hub-devices'), document.getElementById('hub-ss-devices')];
    var hint = document.getElementById('hub-ss-hint');

    // Update slot mapping: assign slots based on device list order
    phoneSlots = {};
    var activeIdx = 0;
    for (var s = 0; s < currentDevices.length; s++) {
      if (currentDevices[s].status === 'active') {
        phoneSlots[String(activeIdx + 1)] = currentDevices[s].id;
        activeIdx++;
      }
    }

    // Determine which device is ringing (if any)
    var ringingDeviceId = null;
    if (ringState && ringState.ringing && ringState.slot) {
      ringingDeviceId = phoneSlots[ringState.slot];
      // Fallback: if no slot mapping, use master device
      if (!ringingDeviceId && masterDeviceId) ringingDeviceId = masterDeviceId;
    }

    var html = '';
    for (var i = 0; i < currentDevices.length; i++) {
      var d = currentDevices[i];
      // Only show bubbles for phones that are physically plugged in.
      // 'active' = projecting AA video, 'available' = plugged in but not yet projecting.
      // Skip devices with other statuses (disconnected, remembered, etc.)
      if (d.status !== 'active' && d.status !== 'available') continue;
      var isActive = d.id === masterDeviceId;
      var isRinging = d.id === ringingDeviceId;
      var defaultName = d.name || d.model || 'Phone';
      var name = getPhoneName(d.id, defaultName);
      var initial = name.charAt(0).toUpperCase();
      var batt = '';
      if (d.batteryLevel !== undefined && d.batteryLevel !== null) {
        var charging = d.batteryCharging ? '<span class="bolt">' + SVG.bolt + '</span>' : '';
        batt = '<span class="hub-pill-batt">' + SVG.battery + ' ' + d.batteryLevel + '%' + charging + '</span>';
      }
      var classes = 'hub-pill';
      if (isActive) classes += ' active';
      if (isRinging) classes += ' ringing';
      html += '<div class="' + classes + '" data-device-id="' + d.id + '">'
        + '<div class="hub-pill-avatar">' + initial + '</div>'
        + '<div class="hub-pill-text">'
        + '<span class="hub-pill-name">' + name + '</span>'
        + batt
        + '</div>'
        + '</div>';
    }

    for (var j = 0; j < containers.length; j++) {
      var container = containers[j];
      if (!container) continue;
      container.innerHTML = html;
      var pills = container.querySelectorAll('.hub-pill[data-device-id]');
      for (var k = 0; k < pills.length; k++) {
        (function(pill) {
          pill.addEventListener('click', function() {
            var id = pill.getAttribute('data-device-id');
            if (id && window.projection && window.projection.ipc && window.projection.ipc.selectDevice) {
              window.projection.ipc.selectDevice(id);
              masterDeviceId = id;
              homeCommandSent = false;
              sendHomeCommand();
              showAAView();
              renderDevices();
            }
          });
        })(pills[k]);
      }
    }

    if (hint) hint.innerHTML = activeIdx ? SVG.phone + ' Select a phone to open Android Auto or CarPlay' : SVG.phone + ' Dock a phone to get started';
  }

  // --- View switching: home screen vs AA/CarPlay view ---
  // showHomeView: cover everything with the screensaver (home screen).
  //   The phone keeps rendering AA underneath, we just cover it.
  function showHomeView() {
    viewingAA = false;
    if (screensaverEl) {
      screensaverEl.style.display = 'flex';
      screensaverEl.style.opacity = '1';
    }
    if (barEl) barEl.style.display = 'none';
    document.body.classList.add('homehub-no-phone');
  }

  // showAAView: fade screensaver out, show hub bar on top of AA video.
  function showAAView() {
    viewingAA = true;
    if (barEl) barEl.style.display = 'flex';
    var np = document.getElementById('hub-nowplaying');
    if (np) np.style.display = 'flex';

    if (screensaverEl) {
      screensaverEl.style.opacity = '0';
      setTimeout(function() {
        if (screensaverEl && !viewingAA) return;
        if (screensaverEl) screensaverEl.style.display = 'none';
      }, 450);
    }

    document.body.classList.remove('homehub-no-phone');
    pollNowPlaying();
  }

  // --- Phone connection state ---
  // setPhoneConnected: called when a phone physically connects/disconnects.
  // When connecting, we stay on the home view (user taps bubble to enter AA).
  // When disconnecting, we ensure the home view is shown.
  function setPhoneConnected(connected) {
    phoneConnected = connected;

    if (connected) {
      // Phone just connected — stay on home view, show the bubble.
      // User will tap the bubble to enter AA view.
      showHomeView();
    } else {
      // Phone unplugged: IMMEDIATELY cover LIVI's UI to prevent the flash.
      viewingAA = false;
      if (screensaverEl) {
        screensaverEl.style.display = 'flex';
        screensaverEl.style.opacity = '1';
      }
      if (barEl) barEl.style.display = 'none';
      document.body.classList.add('homehub-no-phone');

      // Reset now-playing text
      var titleEl = document.getElementById('hub-np-title');
      var artistEl = document.getElementById('hub-np-artist');
      if (titleEl) titleEl.textContent = 'Nothing playing';
      if (artistEl) artistEl.textContent = 'Connect a phone to start';
    }
  }

  // Go back to home screen from AA view (home button handler)
  function homehubGoHome() {
    showHomeView();
  }

  // --- Ring banner (floating, works in both phone-connected and idle states) ---
  function updateRingBanner() {
    if (!ringEl) return;

    var ringing = ringState && ringState.ringing;
    if (ringing) {
      ringEl.style.display = 'flex';
      // Position: when viewing AA, show in upper portion of screen.
      // When on home screen, show centered on full-screen screensaver.
      if (viewingAA) {
        ringEl.style.top = (HUB_HEIGHT - 100) + 'px';
        ringEl.style.transform = 'translateX(-50%)';
      } else {
        ringEl.style.top = '50%';
        ringEl.style.transform = 'translate(-50%, -50%)';
      }
      var callerEl = document.getElementById('hub-ring-caller');
      var phoneEl = document.getElementById('hub-ring-phone');
      if (callerEl) callerEl.textContent = ringState.caller || 'Unknown Caller';
      // Show which phone is ringing if we know
      var phoneName = ringState.phoneName || '';
      var callerNum = ringState.phone || '';
      if (phoneName && callerNum) {
        if (phoneEl) phoneEl.textContent = callerNum + ' \u00b7 ' + phoneName;
      } else if (phoneName) {
        if (phoneEl) phoneEl.textContent = phoneName;
      } else if (callerNum) {
        if (phoneEl) phoneEl.textContent = callerNum;
      } else {
        if (phoneEl) phoneEl.textContent = '';
      }
    } else {
      ringEl.style.display = 'none';
    }

    // Re-render device pills so the ringing bubble highlights
    renderDevices();
  }

  // --- Weather ---
  // Sidecar requests Fahrenheit from open-meteo. Response shape:
  //   { current: { temperature_2m: 72.5, weathercode: 0, ... } }
  function fetchWeather() {
    xhrGet(SIDECAR_URL + '/weather', function(data) {
      var tempEl = document.getElementById('hub-weather-temp');
      var condEl = document.getElementById('hub-weather-cond');
      if (!tempEl || !condEl) return;
      var current = data && data.current ? data.current : data;
      if (current && current.temperature_2m !== undefined) {
        var tempF = Math.round(current.temperature_2m);
        tempEl.textContent = tempF + '\u00b0F';
        var code = current.weathercode;
        var icon = '\u2600'; // sun
        var desc = 'Clear';
        if (code === 0) { icon = '\u2600'; desc = 'Clear'; }
        else if (code <= 3) { icon = '\u2601'; desc = 'Cloudy'; }
        else if (code <= 48) { icon = '\u2318'; desc = 'Foggy'; }
        else if (code <= 67) { icon = '\u2614'; desc = 'Rainy'; }
        else if (code <= 77) { icon = '\u2744'; desc = 'Snowy'; }
        else if (code <= 82) { icon = '\u2614'; desc = 'Rainy'; }
        else if (code <= 99) { icon = '\u26a8'; desc = 'Stormy'; }
        condEl.innerHTML = '<span id="hub-weather-icon">' + icon + '</span> ' + desc;
      }
    });
  }

  // --- Now Playing: poll LIVI's readMedia() for AA media info ---
  // MediaPayload: { payload: { media: { MediaSongName, MediaArtistName, MediaAPPName, ... } } }
  function pollNowPlaying() {
    if (!window.projection || !window.projection.ipc || !window.projection.ipc.readMedia) return;
    if (!phoneConnected) return; // No point polling if no phone

    window.projection.ipc.readMedia().then(function(data) {
      var titleEl = document.getElementById('hub-np-title');
      var artistEl = document.getElementById('hub-np-artist');
      if (!titleEl || !artistEl) return;

      var media = data && data.payload && data.payload.media;
      if (media && media.MediaSongName) {
        titleEl.textContent = media.MediaSongName;
        var artist = media.MediaArtistName || '';
        var app = media.MediaAPPName || '';
        if (artist && app) {
          artistEl.textContent = artist + ' \u00b7 ' + app;
        } else if (artist) {
          artistEl.textContent = artist;
        } else if (app) {
          artistEl.textContent = app;
        } else {
          artistEl.textContent = '';
        }
      } else {
        titleEl.textContent = 'Nothing playing';
        artistEl.textContent = 'Browse apps on your phone';
      }
    }).catch(function() {});
  }

  // --- Poll sidecar for ring status ---
  // Sidecar returns: { ringing: {} } when idle, { ringing: {"1": {caller,phone,...}} } when ringing
  // An empty object {} is truthy in JS, so we must check key count, not truthiness.
  // We also look up which phone is ringing using the slot → deviceId mapping.
  function pollStatus() {
    xhrGet(SIDECAR_URL + '/status', function(data) {
      var ringDict = data && data.ringing ? data.ringing : {};
      var ringKeys = Object.keys(ringDict);
      var newRinging = ringKeys.length > 0;
      var wasRinging = !!(ringState && ringState.ringing);

      if (newRinging) {
        var slot = ringKeys[0];
        var info = ringDict[slot] || {};
        // Look up phone name for this slot
        var deviceId = phoneSlots[slot];
        var phoneName = deviceId ? getPhoneName(deviceId, '') : '';
        // If no slot mapping, try to use the active device
        if (!phoneName && masterDeviceId) {
          phoneName = getPhoneName(masterDeviceId, '');
        }
        ringState = {
          ringing: true,
          caller: info.caller || 'Unknown Caller',
          phone: info.phone || '',
          phoneName: phoneName,
          slot: slot
        };
      } else {
        ringState = { ringing: false };
      }

      if (newRinging !== wasRinging) {
        updateRingBanner();
      } else if (newRinging) {
        updateRingBanner();
      }
    });
  }

  // --- Device detection via onEvent ---
  // Only 'active' status means the phone is actually projecting video.
  // 'available' means plugged in but not projecting — don't count as connected.
  function hasActiveDevice(devices) {
    if (!devices || !devices.length) return false;
    for (var i = 0; i < devices.length; i++) {
      if (devices[i].status === 'active') return true;
    }
    return false;
  }

  function getFirstActiveDevice(devices) {
    if (!devices || !devices.length) return null;
    for (var i = 0; i < devices.length; i++) {
      if (devices[i].status === 'active') return devices[i];
    }
    return null;
  }

  function isActiveDevice(deviceId) {
    if (!deviceId) return false;
    for (var i = 0; i < currentDevices.length; i++) {
      if (currentDevices[i].id === deviceId && currentDevices[i].status === 'active') return true;
    }
    return false;
  }

  // Send 'home' command to AA to leave Maps and go to the phone home screen.
  // Also send 'pause' to stop auto-playing music from the previous session.
  // Delayed slightly to let the AA session fully initialize first.
  var homeCommandSent = false;
  function sendHomeCommand() {
    if (homeCommandSent) return;
    homeCommandSent = true;
    // Give AA a moment to finish connecting before pressing home
    setTimeout(function() { sendCmd('home'); }, 2000);
    // Send pause to stop auto-resumed music
    setTimeout(function() { sendCmd('pause'); }, 3000);
    // Send home again after a longer delay in case the first was too early
    setTimeout(function() { sendCmd('home'); }, 5000);
  }

  // Called when a device becomes active. If it's new (not registered),
  // show the registration prompt while leaving the home screen visible.
  function handleActiveDevice(active) {
    if (!active || phoneNames[active.id] || registrationHandled[active.id]) return;
    registrationHandled[active.id] = true;
    var defName = active.name || active.model || 'Phone';
    showRegistrationPrompt(active.id, defName, function() {
      renderDevices();
    });
  }

  function updateDeviceState() {
    var active = getFirstActiveDevice(currentDevices);
    if (!active) {
      masterDeviceId = null;
      homeCommandSent = false;
      setPhoneConnected(false);
    } else if (masterDeviceId && !isActiveDevice(masterDeviceId)) {
      masterDeviceId = null;
      homeCommandSent = false;
      setPhoneConnected(false);
    }
    if (!masterDeviceId && active) handleActiveDevice(active);
    renderDevices();
  }

  function setupDeviceDetection() {
    if (!window.projection || !window.projection.ipc || !window.projection.ipc.onEvent) return;

    window.projection.ipc.onEvent(function(event) {
      if (!event) return;
      var type = event.type;
      var payload = event.payload;

      if (type === 'devices' && payload) {
        currentDevices = Array.isArray(payload) ? payload : [];
        updateDeviceState();
      } else if (type === 'plugged') {
        homeCommandSent = false;
      } else if (type === 'unplugged' || type === 'failure') {
        homeCommandSent = false;
        if (window.projection && window.projection.ipc && window.projection.ipc.getDevices) {
          window.projection.ipc.getDevices().then(function(devices) {
            currentDevices = devices || [];
            updateDeviceState();
          }).catch(function() {});
        } else {
          currentDevices = [];
          updateDeviceState();
        }
      }
    });

    // Also poll getDevices periodically as a fallback
    function refreshDevices() {
      if (window.projection && window.projection.ipc && window.projection.ipc.getDevices) {
        window.projection.ipc.getDevices().then(function(devices) {
          currentDevices = devices || [];
          updateDeviceState();
        }).catch(function() {});
      }
    }
    refreshDevices();
    setInterval(refreshDevices, 3000);
  }

  // --- Settings overlay ---
  var settingsOverlayEl = null;

  function homehubOpenSettings() {
    if (settingsOverlayEl) return; // Already open
    settingsOverlayEl = document.createElement('div');
    settingsOverlayEl.id = 'homehub-settings-overlay';
    settingsOverlayEl.style.cssText = [
      'position:fixed', 'top:0', 'left:0', 'right:0', 'bottom:0',
      'z-index:100000',
      'background:#0d1117',
      'display:flex', 'flex-direction:column',
      'opacity:0', 'transition:opacity 300ms ease'
    ].join(';');

    var loading = document.createElement('div');
    loading.style.cssText = 'margin:auto;color:#8b949e;font:18px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif';
    loading.textContent = 'Loading settings...';
    settingsOverlayEl.appendChild(loading);
    document.body.appendChild(settingsOverlayEl);

    requestAnimationFrame(function() {
      settingsOverlayEl.style.opacity = '1';
    });

    // Use XHR (not fetch) to load the settings HTML — XHR is proven to work
    // with the sidecar (same mechanism as weather/ring polling). fetch() may
    // hang under LIVI's COEP (Cross-Origin-Embedder-Policy: require-corp).
    var xhr = new XMLHttpRequest();
    xhr.open('GET', SIDECAR_URL + '/settings', true);
    xhr.timeout = 5000;
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== 4) return;
      if (!settingsOverlayEl) return;
      if (xhr.status === 200) {
        var iframe = document.createElement('iframe');
        iframe.style.cssText = 'flex:1;border:none;width:100%;height:100%';
        iframe.setAttribute('allow', 'clipboard-read; clipboard-write');
        // Use srcdoc so the iframe renders the HTML as an about:blank document
        // (inherits parent origin — no cross-origin iframe navigation issues).
        // Inject a <base> tag so relative API calls resolve to the sidecar.
        iframe.srcdoc = xhr.responseText.replace(/<head([^>]*)>/i, '<head$1><base href="' + SIDECAR_URL + '/">');
        loading.remove();
        settingsOverlayEl.appendChild(iframe);
      } else {
        loading.textContent = 'Unable to load settings (HTTP ' + xhr.status + ')';
      }
    };
    xhr.onerror = function() {
      if (settingsOverlayEl) loading.textContent = 'Unable to load settings (network error)';
    };
    xhr.ontimeout = function() {
      if (settingsOverlayEl) loading.textContent = 'Unable to load settings (timeout)';
    };
    xhr.send();

    // Listen for close message from the iframe
    window.addEventListener('message', function(e) {
      if (e.data === 'close-settings') {
        homehubCloseSettings();
      }
    });
  }

  function homehubCloseSettings() {
    if (!settingsOverlayEl) return;
    settingsOverlayEl.style.opacity = '0';
    setTimeout(function() {
      if (settingsOverlayEl) {
        settingsOverlayEl.remove();
        settingsOverlayEl = null;
      }
    }, 300);
  }

  // Expose globally so onclick handlers can call it
  window.homehubOpenSettings = homehubOpenSettings;
  window.homehubCloseSettings = homehubCloseSettings;
  window.homehubGoHome = homehubGoHome;

  // --- Start ---
  function start() {
    loadPhoneNames();
    createHub();
    createScreensaver();
    createRingBanner();
    updateClock();
    fetchWeather();
    setupDeviceDetection();

    // Clock: update every 10s (seconds not shown)
    clockTimer = setInterval(updateClock, 10000);

    // Weather: refresh every 10 min
    setInterval(fetchWeather, 600000);

    // Ring status: poll every 2s
    pollTimer = setInterval(pollStatus, 2000);
    pollStatus();

    // Now playing: poll every 5s (only when phone connected)
    setInterval(pollNowPlaying, 5000);

    console.log('[HomeHub v2] Master Phone Layout started');
  }

  // Wait for React to mount, then start
  setTimeout(start, 1500);
})();
"""

# Append the overlay script to the renderer JS
renderer_js += OVERLAY_SCRIPT
print(f"Appended overlay script: {len(OVERLAY_SCRIPT)} chars")

# --- Rebuild the ASAR ---
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
print(f"\nNow update config and restart LIVI:")
print(f"  python3 -c \"import json; f='/home/raspberry/.config/LIVI/config.json'; c=json.load(open(f)); c['projectionWidth']=600; c['projectionHeight']=1024; c['projectionViewAreaTop']=424; json.dump(c, open(f,'w'), indent=2)\"")
print(f"  systemctl --user restart livi.service")

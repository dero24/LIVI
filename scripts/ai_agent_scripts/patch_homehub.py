#!/usr/bin/env python3
"""
Patch the renderer (index.js) to add:
1. Ring banner overlay (polls sidecar for incoming calls)
2. Full-screen Home Hub UI (replaces car dashboard look)

The Home Hub is a vanilla JS DOM overlay that:
- Has an opaque background (covers AA video/Maps)
- Shows a big clock + date
- Shows device cards (phone name, battery, status)
- Has media controls (play/pause/next/prev)
- Has call controls (answer/hangup/voice)
- Has an "Open Phone" button to show AA video
- When in phone mode, shows a "Home" button to return to hub
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

# --- Check if already patched ---
if 'HOME PHONE HUB — HOME HUB UI' in renderer_js:
    print("Home hub UI already present — removing old patch first")
    # Remove everything from the first patch marker to the end
    idx = renderer_js.find('// ===== HOME PHONE HUB — RING BANNER OVERLAY =====')
    if idx != -1:
        renderer_js = renderer_js[:idx]
        print(f"Trimmed to {len(renderer_js)} chars")
    else:
        idx = renderer_js.find('// ===== HOME PHONE HUB — HOME HUB UI =====')
        if idx != -1:
            renderer_js = renderer_js[:idx]
            print(f"Trimmed to {len(renderer_js)} chars")

# --- The combined overlay script ---
OVERLAY_SCRIPT = r"""

// ===== HOME PHONE HUB — RING BANNER + HOME HUB UI v2 =====
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
  var weatherTimer = null;
  var photoList = [];
  var currentPhotoIdx = 0;
  var bgImgEl = null;
  var screensaverEl = null;
  var screensaverImgEl = null;
  var screensaverActive = false;
  var lastActivity = Date.now();
  var SCREENSAVER_IDLE_MS = 120000; // 2 minutes
  var SCREENSAVER_SLIDE_MS = 8000; // 8 seconds per photo
  var screensaverSlideTimer = null;

  // --- Utility ---
  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }

  function sendCmd(cmd) {
    try { window.projection && window.projection.ipc && window.projection.ipc.sendCommand(cmd); } catch(e) {}
  }

  function xhrGet(url, cb, errCb) {
    try {
      var x = new XMLHttpRequest();
      x.open('GET', url, true);
      x.timeout = 5000;
      x.onreadystatechange = function() {
        if (x.readyState === 4) {
          if (x.status === 200) {
            try { cb(JSON.parse(x.responseText)); } catch(e) { if(errCb) errCb(e); }
          } else { if(errCb) errCb(x.status); }
        }
      };
      x.onerror = function() { if(errCb) errCb('network'); };
      x.ontimeout = function() { if(errCb) errCb('timeout'); };
      x.send();
    } catch(e) { if(errCb) errCb(e); }
  }

  function xhrPost(url) {
    try { var x = new XMLHttpRequest(); x.open('POST', url, true); x.send(); } catch(e) {}
  }

  // --- Weather codes (WMO) ---
  var WEATHER_ICONS = {
    0: '☀️', 1: '🌤️', 2: '⛅', 3: '☁️', 45: '🌫️', 48: '🌫️',
    51: '🌦️', 53: '🌦️', 55: '🌧️', 56: '🌧️', 57: '🌧️',
    61: '🌧️', 63: '🌧️', 65: '🌧️', 66: '🌧️', 67: '🌧️',
    71: '🌨️', 73: '🌨️', 75: '❄️', 77: '❄️',
    80: '🌦️', 81: '🌧️', 82: '🌧️', 85: '🌨️', 86: '🌨️',
    95: '⛈️', 96: '⛈️', 99: '⛈️'
  };
  var WEATHER_DESC = {
    0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Cloudy',
    45: 'Fog', 48: 'Fog', 51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
    56: 'Freezing drizzle', 57: 'Freezing drizzle', 61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
    66: 'Freezing rain', 67: 'Freezing rain', 71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
    77: 'Snow grains', 80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
    85: 'Snow showers', 86: 'Heavy snow showers', 95: 'Thunderstorm', 96: 'Thunderstorm', 99: 'Thunderstorm'
  };

  // --- Time-aware greeting ---
  function getGreeting() {
    var h = new Date().getHours();
    if (h < 5) return 'Good night';
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    if (h < 21) return 'Good evening';
    return 'Good night';
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

    var timeEl = document.getElementById('homehub-time');
    var dateEl = document.getElementById('homehub-date');
    var greetEl = document.getElementById('homehub-greeting');
    if (timeEl) timeEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
    if (greetEl) greetEl.textContent = getGreeting();
  }

  // --- Weather ---
  function updateWeather() {
    xhrGet(SIDECAR_URL + '/weather', function(data) {
      if (!data || !data.current) return;
      var temp = Math.round(data.current.temperature_2m || 0);
      var code = data.current.weathercode;
      var icon = WEATHER_ICONS[code] || '🌡️';
      var desc = WEATHER_DESC[code] || '';
      var feels = Math.round(data.current.apparent_temperature || temp);

      var tempEl = document.getElementById('homehub-weather-temp');
      var iconEl = document.getElementById('homehub-weather-icon');
      var descEl = document.getElementById('homehub-weather-desc');
      if (tempEl) tempEl.textContent = temp + '°';
      if (iconEl) iconEl.textContent = icon;
      if (descEl) descEl.textContent = desc + ' · feels ' + feels + '°';
    }, function() {
      // Weather unavailable — hide weather section
      var ws = document.getElementById('homehub-weather-section');
      if (ws) ws.style.display = 'none';
    });
  }

  // --- Photos ---
  function loadPhotos() {
    xhrGet(SIDECAR_URL + '/photos', function(data) {
      photoList = data.photos || [];
      if (photoList.length > 0) {
        setBgPhoto(0);
        console.log('[HomePhone] Loaded ' + photoList.length + ' photos');
      }
    }, function() {
      // No photos — that's fine, gradient background stays
    });
  }

  function setBgPhoto(idx) {
    if (photoList.length === 0) return;
    currentPhotoIdx = idx % photoList.length;
    if (!bgImgEl) return;
    var url = SIDECAR_URL + '/photo/' + encodeURIComponent(photoList[currentPhotoIdx]);
    var img = new Image();
    img.onload = function() {
      bgImgEl.style.backgroundImage = 'url("' + url + '")';
      bgImgEl.style.opacity = '0.25';
    };
    img.src = url;
  }

  function rotateBgPhoto() {
    if (photoList.length === 0) return;
    setBgPhoto((currentPhotoIdx + 1) % photoList.length);
  }

  // --- Screensaver ---
  function showScreensaver() {
    if (screensaverActive || photoList.length === 0) return;
    screensaverActive = true;
    if (!screensaverEl) {
      screensaverEl = document.createElement('div');
      screensaverEl.id = 'homehub-screensaver';
      screensaverEl.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:99998',
        'background:#000', 'display:flex',
        'align-items:center', 'justify-content:center',
        'transition:opacity 1.5s ease', 'opacity:0',
        'pointerEvents:auto'
      ].join(';');
      screensaverImgEl = document.createElement('img');
      screensaverImgEl.style.cssText = 'max-width:100%;max-height:100%;object-fit:contain;transition:opacity 1.5s ease';
      screensaverEl.appendChild(screensaverImgEl);
      screensaverEl.addEventListener('pointerdown', wakeFromScreensaver);
      document.body.appendChild(screensaverEl);
    }
    screensaverEl.style.display = 'flex';
    // Force reflow then fade in
    setTimeout(function() { screensaverEl.style.opacity = '1'; }, 50);
    // Hide hub
    if (hubEl) hubEl.style.opacity = '0';
    setTimeout(function() { if (hubEl) hubEl.style.display = 'none'; }, 1500);
    // Start slideshow
    showScreensaverPhoto(0);
    screensaverSlideTimer = setInterval(function() {
      var next = (currentPhotoIdx + 1) % photoList.length;
      showScreensaverPhoto(next);
    }, SCREENSAVER_SLIDE_MS);
    console.log('[HomePhone] Screensaver activated');
  }

  function showScreensaverPhoto(idx) {
    if (!screensaverImgEl || photoList.length === 0) return;
    currentPhotoIdx = idx % photoList.length;
    var url = SIDECAR_URL + '/photo/' + encodeURIComponent(photoList[currentPhotoIdx]);
    screensaverImgEl.style.opacity = '0';
    setTimeout(function() {
      screensaverImgEl.src = url;
      screensaverImgEl.style.opacity = '1';
    }, 800);
  }

  function wakeFromScreensaver() {
    if (!screensaverActive) return;
    screensaverActive = false;
    lastActivity = Date.now();
    if (screensaverSlideTimer) { clearInterval(screensaverSlideTimer); screensaverSlideTimer = null; }
    if (screensaverEl) {
      screensaverEl.style.opacity = '0';
      setTimeout(function() { if (screensaverEl) screensaverEl.style.display = 'none'; }, 1500);
    }
    if (hubEl) { hubEl.style.display = 'flex'; hubEl.style.opacity = '1'; }
    console.log('[HomePhone] Woke from screensaver');
  }

  function checkIdle() {
    if (screensaverActive || phoneMode) return;
    if (Date.now() - lastActivity > SCREENSAVER_IDLE_MS) {
      showScreensaver();
    }
  }

  function notifyActivity() {
    lastActivity = Date.now();
    if (screensaverActive) wakeFromScreensaver();
  }

  // --- Home Hub UI ---
  function createHub() {
    if (hubEl) return;

    // Background image layer (photos)
    bgImgEl = document.createElement('div');
    bgImgEl.id = 'homehub-bg';
    bgImgEl.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:99997',
      'background-size:cover', 'background-position:center',
      'background-repeat:no-repeat', 'opacity:0',
      'transition:opacity 2s ease', 'pointerEvents:none'
    ].join(';');
    document.body.appendChild(bgImgEl);

    hubEl = document.createElement('div');
    hubEl.id = 'homehub-overlay';
    hubEl.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:99998',
      'background:linear-gradient(180deg,rgba(15,15,30,0.85) 0%,rgba(20,25,50,0.8) 50%,rgba(10,15,35,0.9) 100%)',
      'color:#e8e8e8', 'font-family:Roboto,system-ui,sans-serif',
      'display:flex', 'flex-direction:column', 'overflow:hidden',
      'pointerEvents:auto', 'transition:opacity 1s ease'
    ].join(';');

    hubEl.innerHTML = `
      <style>
        #homehub-overlay * { box-sizing: border-box; }
        #homehub-time { font-size: 84px; font-weight: 200; letter-spacing: -3px; line-height: 1; text-shadow: 0 2px 20px rgba(0,0,0,0.5); }
        #homehub-date { font-size: 16px; opacity: 0.6; margin-top: 6px; letter-spacing: 0.5px; }
        #homehub-greeting { font-size: 22px; font-weight: 400; opacity: 0.8; margin-bottom: 4px; }
        .homehub-card {
          background: rgba(255,255,255,0.07);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 24px;
          padding: 20px 24px;
          margin: 6px 20px;
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
        }
        .homehub-weather-row {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        #homehub-weather-icon { font-size: 48px; line-height: 1; }
        #homehub-weather-temp { font-size: 42px; font-weight: 300; line-height: 1; }
        #homehub-weather-desc { font-size: 13px; opacity: 0.6; margin-top: 4px; }
        .homehub-device {
          display: flex;
          align-items: center;
          gap: 16px;
          background: rgba(255,255,255,0.06);
          border: 2px solid rgba(255,255,255,0.06);
          border-radius: 18px;
          padding: 16px 20px;
          cursor: pointer;
          transition: border-color 200ms, background 200ms, transform 100ms;
          user-select: none;
          -webkit-user-select: none;
        }
        .homehub-device:active { transform: scale(0.98); }
        .homehub-device.active { border-color: rgba(79,195,247,0.5); background: rgba(79,195,247,0.08); }
        .homehub-device-icon { font-size: 32px; }
        .homehub-device-info { flex: 1; min-width: 0; }
        .homehub-device-name { font-size: 17px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .homehub-device-status { font-size: 12px; opacity: 0.5; margin-top: 2px; }
        .homehub-phone-btn {
          display: flex; align-items: center; justify-content: center; gap: 10px;
          background: rgba(255,255,255,0.1);
          border: 1px solid rgba(255,255,255,0.15);
          border-radius: 18px;
          color: #e8e8e8; cursor: pointer; font-family: inherit;
          font-size: 15px; font-weight: 500; padding: 16px 32px;
          transition: transform 100ms, background 200ms;
          user-select: none; -webkit-user-select: none;
        }
        .homehub-phone-btn:active { transform: scale(0.97); background: rgba(255,255,255,0.15); }
        .homehub-phone-btn svg { width: 22px; height: 22px; opacity: 0.8; }
      </style>

      <!-- Header: Greeting + Clock + Weather -->
      <div style="text-align:center;padding:48px 16px 16px;flex-shrink:0">
        <div id="homehub-greeting">Hello</div>
        <div id="homehub-time">--:--</div>
        <div id="homehub-date">---</div>
      </div>

      <!-- Weather Card -->
      <div class="homehub-card" id="homehub-weather-section">
        <div class="homehub-weather-row">
          <div id="homehub-weather-icon">🌡️</div>
          <div>
            <div id="homehub-weather-temp">--°</div>
            <div id="homehub-weather-desc">Loading weather...</div>
          </div>
        </div>
      </div>

      <!-- Device Cards -->
      <div class="homehub-card" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="font-size:12px;text-transform:uppercase;letter-spacing:1px;opacity:0.4;margin-bottom:14px;font-weight:600">Phones</div>
        <div id="homehub-devices" style="display:flex;flex-direction:column;gap:10px;overflow-y:auto;flex:1">
          <div style="text-align:center;opacity:0.3;padding:30px">No phone connected</div>
        </div>
      </div>

      <!-- Open Phone Button -->
      <div style="padding:10px 20px 32px;flex-shrink:0;display:flex;justify-content:center">
        <button class="homehub-phone-btn" id="homehub-open-phone">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>
          <span>Open Phone</span>
        </button>
      </div>
    `;

    document.body.appendChild(hubEl);

    // Wire up Open Phone button
    document.getElementById('homehub-open-phone').addEventListener('pointerdown', function() {
      notifyActivity();
      setPhoneMode(true);
    });

    // Start clock
    updateClock();
    clockTimer = setInterval(updateClock, 1000);

    // Weather updates every 30 min
    updateWeather();
    weatherTimer = setInterval(updateWeather, 1800000);

    // Rotate background photo every 5 minutes
    setInterval(rotateBgPhoto, 300000);

    // Idle check every 10 seconds
    setInterval(checkIdle, 10000);

    // Track activity
    document.addEventListener('pointerdown', notifyActivity, { passive: true });
    document.addEventListener('pointermove', notifyActivity, { passive: true });
  }

  function setPhoneMode(mode) {
    phoneMode = mode;
    if (hubEl) hubEl.style.display = mode ? 'none' : 'flex';
    if (bgImgEl) bgImgEl.style.display = mode ? 'none' : 'block';
    if (mode) {
      if (!document.getElementById('homehub-home-btn')) {
        var homeBtn = document.createElement('button');
        homeBtn.id = 'homehub-home-btn';
        homeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" style="width:24px;height:24px"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>';
        homeBtn.style.cssText = 'position:fixed;top:16px;right:16px;z-index:99997;background:rgba(0,0,0,0.6);border:1px solid rgba(255,255,255,0.2);border-radius:14px;color:white;cursor:pointer;padding:12px;display:flex;align-items:center;justify-content:center;pointerEvents:auto';
        homeBtn.addEventListener('pointerdown', function() { notifyActivity(); setPhoneMode(false); });
        document.body.appendChild(homeBtn);
      }
      document.getElementById('homehub-home-btn').style.display = 'flex';
    } else {
      var hb = document.getElementById('homehub-home-btn');
      if (hb) hb.style.display = 'none';
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

  // --- LIVI event listener (devices + unplug) ---
  function registerLiviEvents() {
    try {
      if (!window.projection || !window.projection.ipc || !window.projection.ipc.onEvent) return;
      // onEvent returns a cleanup function
      window.projection.ipc.onEvent(function(evt) {
        var args = Array.prototype.slice.call(arguments, 1);
        var msg = args[0] || {};
        if (msg.type === 'devices' && msg.payload) {
          // Live device list update
          var container = document.getElementById('homehub-devices');
          if (container) renderDevices(container, msg.payload);
        } else if (msg.type === 'unplugged' || msg.type === 'failure') {
          // Phone unplugged or session failed — return to hub
          console.log('[HomePhone] LIVI event: ' + msg.type + ' — returning to hub');
          setPhoneMode(false);
          // Refresh device list
          setTimeout(updateDevices, 500);
        }
      });
      console.log('[HomePhone] Registered LIVI onEvent listener');
    } catch(e) {
      console.warn('[HomePhone] Could not register onEvent: ' + e);
    }
  }

  function renderDevices(container, devices) {
    if (!devices || devices.length === 0) {
      container.innerHTML = '<div style="text-align:center;opacity:0.3;padding:30px">No phone connected</div>';
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
          '<div class="homehub-device-status">' + escapeHtml(statusText) + (batteryText ? ' · ' + batteryText : '') + '</div>' +
        '</div></div>';
    }
    container.innerHTML = html;
    var cards = container.querySelectorAll('.homehub-device');
    for (var j = 0; j < cards.length; j++) {
      (function(card) {
        card.addEventListener('pointerdown', function() {
          notifyActivity();
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
    bannerEl.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:white;padding:20px 28px;display:flex;align-items:center;justify-content:space-between;gap:20px;font-family:Roboto,sans-serif;box-shadow:0 4px 20px rgba(0,0,0,0.4);animation:ringPulse 1.5s ease-in-out infinite alternate;pointerEvents:auto';
    var info = document.createElement('div');
    info.style.cssText = 'flex:1;min-width:0';
    info.innerHTML = '<div style="font-size:24px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + escapeHtml(caller || 'Incoming Call') + '</div><div style="font-size:15px;opacity:0.85;margin-top:4px">' + escapeHtml(phone || 'Phone') + ' is ringing</div>';
    var answerBtn = document.createElement('button');
    answerBtn.textContent = 'Answer';
    answerBtn.style.cssText = 'padding:14px 32px;border-radius:28px;border:2px solid white;background:rgba(255,255,255,0.2);color:white;font-size:18px;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0';
    answerBtn.onpointerdown = function(e) { e.preventDefault(); sendCmd('acceptPhone'); xhrPost(SIDECAR_URL + '/hangup?slot=' + slot); removeBanner(); };
    var hangupBtn = document.createElement('button');
    hangupBtn.textContent = 'Decline';
    hangupBtn.style.cssText = 'padding:14px 32px;border-radius:28px;border:2px solid rgba(255,255,255,0.4);background:rgba(255,59,48,0.3);color:white;font-size:18px;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0';
    hangupBtn.onpointerdown = function(e) { e.preventDefault(); sendCmd('rejectPhone'); xhrPost(SIDECAR_URL + '/hangup?slot=' + slot); removeBanner(); };
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

  function removeBanner() { if (bannerEl) { bannerEl.remove(); bannerEl = null; } }

  function updateBanner() {
    var slots = Object.keys(ringState);
    if (slots.length > 0) {
      var slot = slots[0];
      var info = ringState[slot];
      createBanner(slot, info.caller, info.phone);
    } else { removeBanner(); }
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
    loadPhotos();
    // Register for live LIVI events (device list changes, unplug events)
    registerLiviEvents();
    // Poll ring status from sidecar
    pollTimer = setInterval(pollStatus, POLL_INTERVAL);
    pollStatus();
    // Poll devices as fallback (in case onEvent isn't available)
    setInterval(updateDevices, 5000);
    updateDevices();
    console.log('[HomePhone] Home hub UI v2 started');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    setTimeout(start, 1000);
  }
})();
// ===== END HOME PHONE HUB =====
"""

# --- Append the script to the renderer ---
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
print(f"Original backed up to {backup_path}")

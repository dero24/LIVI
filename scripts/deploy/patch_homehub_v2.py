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
import struct, json, os, sys, shutil, re

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
  var landingEl = null;
  var ringEl = null;
  var clockTimer = null;
  var currentDevices = [];
  var lastRenderedHtml = {}; // container id -> html (skip redundant re-renders)
  var sidecarFailures = 0;   // consecutive /status poll failures
  var healthDotEl = null;
  var ssPhotos = [];         // photo screensaver playlist (filenames)
  var ssPhotoIdx = 0;
  var ssPhotoLayerA = null;
  var ssPhotoLayerB = null;
  var ssPhotoActiveIsA = true;
  var masterDeviceId = null;
  var phoneConnected = false;   // phone is physically plugged in & projecting
  var viewingAA = false;        // user is viewing the AA/CarPlay screen (not home)
  var viewingLanding = false;   // user is viewing the phone landing page
  var mediaIsPlaying = false;   // tracks AA media play state for play/pause button
  var phoneNames = {}; // deviceId -> user-defined name (persisted in localStorage)
  var phoneSlots = {}; // slot number -> deviceId (mapped by dock order)
  var registrationHandled = {};
  var appPositions = {}; // deviceId -> { phone:{x,y}, messages:{x,y}, music:{x,y} }
  var calibrating = false;     // true during calibration flow
  var calibrationEl = null;    // calibration overlay element
  var calibrationStep = 0;     // 0=intro, 1=phone, 2=messages, 3=music, 4=done
  var calibrationData = {};    // collected positions during calibration

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

  // --- Load/save app positions (calibration data) ---
  function loadAppPositions() {
    try {
      var saved = localStorage.getItem('homehub.appPositions');
      if (saved) appPositions = JSON.parse(saved) || {};
    } catch(e) { appPositions = {}; }
  }
  function saveAppPositions() {
    try { localStorage.setItem('homehub.appPositions', JSON.stringify(appPositions)); } catch(e) {}
  }
  function isPhoneCalibrated(deviceId) {
    var pos = appPositions[deviceId];
    return pos && pos.phone && pos.messages && pos.music;
  }

  function sendCmd(cmd) {
    console.log('[HomeHub] sendCmd:', cmd);
    try { window.projection && window.projection.ipc && window.projection.ipc.sendCommand(cmd); } catch(e) { console.log('[HomeHub] sendCmd error:', e); }
  }
  // Expose immediately — don't wait for end of IIFE in case a JS error
  // prevents execution from reaching the bottom global exports.
  window.sendCmd = sendCmd;

  // --- Touch injection ---
  // AA sends video in canonical 16:9 tiers (800×480, 1280×720, 1920×1080, etc.).
  // Our display is 600×1024 (portrait). matchFittingAAResolution picks the
  // smallest tier where the display content fits within 1.2× upscale.
  // For 600×1024, that's 1920×1080. The 600×1024 content is centered within
  // the 1920×1080 tier with left/right margins.
  //
  // Tier geometry (calculated from matchFittingAAResolution for 600×1024):
  //   tierW=1920, tierH=1080
  //   contentW = roundEven(1080 * 600/1024) = 632
  //   arLeft = floor((1920-632)/2) = 644
  //   viewAreaTop = 450 (tier pixels, from config)
  //
  // Display (600×1024) → Tier (1920×1080) conversion:
  //   tierX = arLeft + (dispX / 600) * contentW = 644 + dispX * 632/600
  //   tierY = (dispY / 1024) * 1080
  //   normX = tierX / 1920
  //   normY = tierY / 1080
  var TIER_W = 1920, TIER_H = 1080;
  var CONTENT_W = 632, AR_LEFT = 644;
  var VIEW_AREA_TOP = 450;

  // Convert display pixels (0-600, 0-1024) to normalized touch coords (0-1)
  // relative to the full AA video tier.
  function displayToTouchNorm(dispX, dispY) {
    var tierX = AR_LEFT + (dispX / 600) * CONTENT_W;
    var tierY = (dispY / 1024) * TIER_H;
    return { x: tierX / TIER_W, y: tierY / TIER_H };
  }

  // Send a touch event at display coordinates. action: 14=Down, 15=Move, 16=Up
  function sendTouchEvent(dispX, dispY, action) {
    try {
      var ipc = window.projection && window.projection.ipc;
      if (!ipc || !ipc.sendTouch) return;
      var n = displayToTouchNorm(dispX, dispY);
      ipc.sendTouch(n.x, n.y, action);
    } catch(e) {}
  }

  // Tap at display coordinates (down + up with 50ms gap)
  function sendTouchAt(dispX, dispY) {
    sendTouchEvent(dispX, dispY, 14);  // Down
    setTimeout(function() {
      sendTouchEvent(dispX, dispY, 16);  // Up
    }, 50);
  }

  // --- Navigate to a specific AA app using recorded touch sequence ---
  // This runs IN THE BACKGROUND while the landing page is still visible.
  // The user never sees the AA dashboard or the navigation happening.
  // onComplete is called after the app should be open, so the caller can
  // then fade to AA view.
  function navigateToApp(appName, onComplete) {
    var pos = appPositions[masterDeviceId] && appPositions[masterDeviceId][appName];
    if (!pos) {
      // No calibration for this app — just go to dashboard
      sendCmd('home');
      setTimeout(function() { if (onComplete) onComplete(); }, 600);
      return;
    }
    // 1. Go to AA dashboard (resets to top of app grid)
    sendCmd('home');
    // 2. Wait for dashboard to render
    setTimeout(function() {
      if (pos.sequence && pos.sequence.length > 0) {
        // Replay the recorded touch sequence (scrolls + tap)
        replayTouchSequence(pos.sequence, function() {
          if (onComplete) onComplete();
        });
      } else if (pos.x !== undefined && pos.y !== undefined) {
        // Fallback: just tap the recorded position (no scroll needed)
        sendTouchAt(pos.x, pos.y);
        setTimeout(function() {
          if (onComplete) onComplete();
        }, 800);
      } else {
        if (onComplete) onComplete();
      }
    }, 800);
  }

  // Replay a recorded touch sequence. Each event: { x, y, action, delay }
  // where x,y are display coordinates, action is 14/15/16, delay is ms
  // since previous event (capped at 50ms for replay speed).
  function replayTouchSequence(sequence, onComplete) {
    var i = 0;
    function playNext() {
      if (i >= sequence.length) {
        setTimeout(function() { if (onComplete) onComplete(); }, 500);
        return;
      }
      var evt = sequence[i];
      sendTouchEvent(evt.x, evt.y, evt.action);
      i++;
      if (i < sequence.length) {
        var nextDelay = Math.min(sequence[i].delay, 50);
        if (nextDelay < 10) nextDelay = 10;
        setTimeout(playNext, nextDelay);
      } else {
        // Last event — wait for app to open
        setTimeout(function() { if (onComplete) onComplete(); }, 800);
      }
    }
    playNext();
  }

  // --- Navigate LIVI's React Router to the projection route ('/') ---
  // LIVI only shows #projection-root (visibility/opacity/z-index) and calls
  // setVisible(true) to unhide the native video plane when pathname === '/'.
  // LIVI's own Devices page does selectDevice(id) then navigate('/') — we must
  // do the same or the AA view stays black. LIVI uses a HashRouter, so setting
  // location.hash triggers navigation; the popstate dispatch is a fallback in
  // case the hashchange alone is not picked up.
  function navToProjection() {
    try {
      if (window.location.hash !== '#/') {
        window.location.hash = '#/';
      }
      var ev;
      try { ev = new PopStateEvent('popstate'); } catch(e) { ev = new Event('popstate'); }
      window.dispatchEvent(ev);
    } catch(e) {}
  }

  function xhrGet(url, cb, errCb) {
    try {
      var x = new XMLHttpRequest();
      x.open('GET', url, true);
      x.timeout = 3000;
      x.onreadystatechange = function() {
        if (x.readyState === 4) {
          if (x.status === 200) {
            try { cb(JSON.parse(x.responseText)); } catch(e) {}
          } else if (errCb) {
            errCb();
          }
        }
      };
      x.onerror = function() { if (errCb) errCb(); };
      x.ontimeout = function() { if (errCb) errCb(); };
      x.send();
    } catch(e) { if (errCb) errCb(); }
  }

  // --- Sidecar health dot ---
  // A tiny dot in the bottom-right corner of the screen. Hidden when the
  // sidecar is healthy. Amber pulse after ~6s of failed polls, red after
  // ~20s. Honest, not alarming — "I can't reach the alert system."
  function createHealthDot() {
    if (healthDotEl) return;
    var st = document.createElement('style');
    st.textContent = '@keyframes hub-health-pulse{0%,100%{opacity:0.35}50%{opacity:1}}';
    document.head.appendChild(st);
    healthDotEl = document.createElement('div');
    healthDotEl.id = 'homehub-health';
    healthDotEl.style.cssText = [
      'position:fixed', 'right:14px', 'bottom:14px', 'width:10px', 'height:10px',
      'border-radius:50%', 'z-index:100002', 'display:none', 'pointer-events:none'
    ].join(';');
    document.body.appendChild(healthDotEl);
  }

  function updateHealthDot() {
    if (!healthDotEl) return;
    if (sidecarFailures >= 10) {
      healthDotEl.style.display = 'block';
      healthDotEl.style.background = '#ff6b6b';
      healthDotEl.style.animation = 'hub-health-pulse 1.2s ease-in-out infinite';
    } else if (sidecarFailures >= 3) {
      healthDotEl.style.display = 'block';
      healthDotEl.style.background = '#d29922';
      healthDotEl.style.animation = 'hub-health-pulse 2s ease-in-out infinite';
    } else {
      healthDotEl.style.display = 'none';
    }
  }

  function xhrPost(url) {
    try { var x = new XMLHttpRequest(); x.open('POST', url, true); x.send(); } catch(e) {}
  }

  // --- Clock ---
  function updateClock() {
    var now = new Date();
    var hour24 = now.getHours();
    var h = hour24;
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
    var ssGreeting = document.getElementById('hub-ss-greeting');
    if (timeEl) timeEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
    if (ssTime) ssTime.textContent = timeStr + ' ' + ampm;
    if (ssDate) ssDate.textContent = dateStr;

    // Time-based greeting — quiet, human, like the house saying hello
    if (ssGreeting) {
      var g = 'Good night';
      if (hour24 >= 5 && hour24 < 12) g = 'Good morning';
      else if (hour24 >= 12 && hour24 < 17) g = 'Good afternoon';
      else if (hour24 >= 17 && hour24 < 22) g = 'Good evening';
      ssGreeting.textContent = g;
    }

    // Night mode (22:00 - 07:00): everything whispers — dim clock, no
    // weather, photos nearly black. Just a clock in the dark.
    var night = hour24 >= 22 || hour24 < 7;
    if (document.body) {
      if (night) document.body.classList.add('hub-night');
      else document.body.classList.remove('hub-night');
    }
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
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    // Landing page tiles — stroke-width 1.5 for a lighter, more elegant feel
    phoneTab: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    messages: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    musicTab: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    apps: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    // Media transport controls
    skipBack: '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    skipForward: '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    playIcon: '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    pauseIcon: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
    // Notification bell
    bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    arrowRight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>'
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

        /* PERMANENTLY hide LIVI's Home page, nav, and all non-projection UI.
           #projection-root is a direct child of #content-root (confirmed via
           DOM dump). We hide all other children of #content-root so LIVI's
           Home page never shows — preventing the unplug flash. */
        #content-root > *:not(#projection-root) { display: none !important; }
        #nav-root { display: none !important; }

        /* Hide LIVI's "waiting for phone" logo/placeholder inside
           #projection-root. This is the SVG logo that shows when no phone
           is projecting. It has a 120ms fade-out transition, which causes
           a logo flash on unplug. By hiding it permanently, the flash is
           eliminated. The actual AA video is in #videoContainer, not
           affected by this rule. */
        #projection-root > .MuiBox-root { display: none !important; }

        /* Force #projection-root to always have a high z-index so AA video
           appears above our body background. LIVI sets z-index:-1 when not
           projecting, which puts it below everything. We override it so
           the video is visible as soon as it starts rendering. */
        #projection-root { z-index: 999 !important; }

        /* Match background to our screensaver color so empty space behind
           LIVI's elements is the same dark color.
           CRITICAL: LIVI renders AA video as a NATIVE UNDERLAY below the
           web view. When streaming on the '/' route it sets html.show-video,
           which makes html/body/#root/#main/#videoContainer TRANSPARENT so
           the video shows through (see src/renderer/index.html). If we
           force an opaque background here, it paints over the video and the
           bottom half is black. So only apply when show-video/show-cluster
           are NOT set. */
        html:not(.show-video):not(.show-cluster) body,
        html:not(.show-video):not(.show-cluster) #root,
        html:not(.show-video):not(.show-cluster) #main,
        html:not(.show-video):not(.show-cluster) #videoContainer {
          background: #0d1117 !important;
        }

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
          animation: hub-pill-in 350ms cubic-bezier(0.16,1,0.3,1) both;
        }
        @keyframes hub-pill-in {
          from { opacity: 0; transform: translateY(10px) scale(0.96); }
          to { opacity: 1; transform: translateY(0) scale(1); }
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

        /* Media transport controls — only visible in aa-mode */
        #hub-np-controls {
          display: none; align-items: center; gap: 8px; flex-shrink: 0;
        }
        #homehub-bar.aa-mode #hub-np-controls { display: flex; }
        .hub-ctrl-btn {
          width: 36px; height: 36px; border-radius: 10px;
          border: none; background: transparent;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; color: #8b949e;
          transition: all 150ms cubic-bezier(0.4,0,0.2,1);
        }
        .hub-ctrl-btn svg { width: 20px; height: 20px; }
        .hub-ctrl-btn:active { transform: scale(0.88); color: #f0f6fc; }
        .hub-ctrl-btn:hover { color: #f0f6fc; background: rgba(255,255,255,0.04); }
        .hub-ctrl-play { width: 44px; height: 44px; border-radius: 12px; }
        .hub-ctrl-play svg { width: 24px; height: 24px; }

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

        /* === Motion: smooth size/padding transitions for mode switches === */
        #hub-time, #hub-date, #hub-weather-temp, #hub-weather-cond,
        #hub-np-title, #hub-np-artist, #hub-np-icon,
        .hub-pill, .hub-pill-avatar, .hub-pill-name {
          transition: all 400ms cubic-bezier(0.4,0,0.2,1);
        }
        #hub-header, #hub-devices-wrap, #hub-bottom {
          transition: padding 400ms cubic-bezier(0.4,0,0.2,1);
        }
        #hub-np-title, #hub-np-artist { transition: opacity 200ms ease-out; }

        /* === AA view mode: the phone is the star, the bar is the stagehand ===
           Everything in the bar quiets down and compacts so the AA video
           owns the screen. Now-playing is the one thing we emphasize —
           it's the most glanceable info while the phone is in use. */
        #homehub-bar.aa-mode #hub-header { padding: 24px 40px 0; }
        #homehub-bar.aa-mode #hub-time { font-size: 44px; letter-spacing: -2px; }
        #homehub-bar.aa-mode #hub-date { font-size: 15px; margin-top: 4px; }
        #homehub-bar.aa-mode #hub-weather-temp { font-size: 24px; }
        #homehub-bar.aa-mode #hub-weather-cond { font-size: 12px; }
        #homehub-bar.aa-mode #hub-devices-wrap { padding: 20px 40px 0; }
        #homehub-bar.aa-mode .hub-pill {
          padding: 12px 36px 12px 12px; min-height: 64px; gap: 12px;
        }
        #homehub-bar.aa-mode .hub-pill-avatar { width: 44px; height: 44px; font-size: 20px; }
        #homehub-bar.aa-mode .hub-pill-name { font-size: 18px; }
        #homehub-bar.aa-mode .hub-pill-batt { font-size: 13px; }
        #homehub-bar.aa-mode #hub-bottom { align-items: center; padding-bottom: 40px; }
        #homehub-bar.aa-mode #hub-nowplaying { gap: 16px; }
        #homehub-bar.aa-mode #hub-np-icon { width: 28px; height: 28px; color: #8b949e; }
        #homehub-bar.aa-mode #hub-np-title { font-size: 20px; color: #f0f6fc; }
        #homehub-bar.aa-mode #hub-np-artist { font-size: 15px; color: #8b949e; margin-top: 4px; }

        /* Bar entrance: arrives gently as the screensaver lifts */
        #homehub-bar.bar-reveal { animation: hub-bar-reveal 500ms cubic-bezier(0.16,1,0.3,1) both; }
        @keyframes hub-bar-reveal {
          from { opacity: 0; transform: translateY(-14px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* Ambient warm glow across the whole bar while a call rings —
           "a lamp turning on", not an alarm. (!important beats the inline
           background on #homehub-bar.) */
        #homehub-bar.ringing {
          background: linear-gradient(180deg, rgba(255,107,107,0.12) 0%, rgba(13,17,23,0) 60%) !important;
          animation: hub-bar-ring-glow 2s ease-in-out infinite;
        }
        @keyframes hub-bar-ring-glow {
          0%,100% { box-shadow: inset 0 0 0 rgba(255,107,107,0); }
          50% { box-shadow: inset 0 -70px 90px -40px rgba(255,107,107,0.14); }
        }

        /* Night mode: the bar whispers after dark */
        body.hub-night #homehub-bar #hub-time { opacity: 0.55; }
        body.hub-night #homehub-bar #hub-weather { display: none; }
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

      <!-- Bottom: Now Playing + Media Controls -->
      <div id="hub-bottom">
        <div id="hub-nowplaying">
          <div id="hub-np-icon">${SVG.music}</div>
          <div id="hub-np-info">
            <div id="hub-np-title">Nothing playing</div>
            <div id="hub-np-artist">Connect a phone to start</div>
          </div>
          <div id="hub-np-controls">
            <button class="hub-ctrl-btn" id="hub-ctrl-prev" aria-label="Previous track">${SVG.skipBack}</button>
            <button class="hub-ctrl-btn hub-ctrl-play" id="hub-ctrl-play" aria-label="Play/Pause">${SVG.playIcon}</button>
            <button class="hub-ctrl-btn" id="hub-ctrl-next" aria-label="Next track">${SVG.skipForward}</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(barEl);

    // Wire up media controls via addEventListener (inline onclick blocked by CSP)
    var prevBtn = barEl.querySelector('#hub-ctrl-prev');
    var playBtn = barEl.querySelector('#hub-ctrl-play');
    var nextBtn = barEl.querySelector('#hub-ctrl-next');
    if (prevBtn) prevBtn.addEventListener('click', function() { sendCmd('prev'); });
    // Play/pause: send 'pause' if currently playing, 'play' if paused/stopped
    if (playBtn) playBtn.addEventListener('click', function() {
      sendCmd(mediaIsPlaying ? 'pause' : 'play');
    });
    if (nextBtn) nextBtn.addEventListener('click', function() { sendCmd('next'); });
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
      'transition:opacity 600ms cubic-bezier(0.4,0,0.2,1),transform 600ms cubic-bezier(0.4,0,0.2,1)'
    ].join(';');

    screensaverEl.innerHTML = `
      <style>
        #homehub-screensaver * { box-sizing: border-box; margin: 0; padding: 0; }

        /* Photo layers — two stacked divs, crossfaded, Ken Burns drift.
           inset:-4% gives the pan headroom so edges never show. */
        #hub-ss-photos { position: absolute; inset: 0; overflow: hidden; z-index: 0; }
        .hub-ss-photo {
          position: absolute; inset: -4%;
          background-size: cover; background-position: center;
          opacity: 0; transition: opacity 2500ms ease;
          will-change: transform, opacity;
        }
        .hub-ss-photo.visible { opacity: 1; }
        .hub-ss-photo.kb-a { animation: hub-kenburns-a 24s ease-in-out infinite alternate; }
        .hub-ss-photo.kb-b { animation: hub-kenburns-b 24s ease-in-out infinite alternate; }
        @keyframes hub-kenburns-a {
          from { transform: scale(1.02) translate(0, 0); }
          to   { transform: scale(1.10) translate(-1.5%, -1%); }
        }
        @keyframes hub-kenburns-b {
          from { transform: scale(1.10) translate(1.5%, 1%); }
          to   { transform: scale(1.02) translate(0, 0); }
        }

        /* Scrim keeps the clock and pills legible over any photo */
        #hub-ss-scrim {
          position: absolute; inset: 0; z-index: 1;
          background: linear-gradient(180deg,
            rgba(13,17,23,0.55) 0%,
            rgba(13,17,23,0.15) 30%,
            rgba(13,17,23,0.15) 55%,
            rgba(13,17,23,0.78) 100%);
          opacity: 0; transition: opacity 1200ms ease;
        }
        #homehub-screensaver.has-photos #hub-ss-scrim { opacity: 1; }

        #hub-ss-greeting {
          position: relative; z-index: 2;
          font-size: 20px; font-weight: 300; color: #8b949e;
          letter-spacing: 0.5px; margin-bottom: 16px; min-height: 24px;
        }
        #hub-ss-time {
          position: relative; z-index: 2;
          font-size: 120px; font-weight: 200; letter-spacing: -5px; line-height: 1;
          color: #f0f6fc; opacity: 0.95;
        }
        #hub-ss-date {
          position: relative; z-index: 2;
          font-size: 24px; font-weight: 300; color: #8b949e; margin-top: 16px;
          letter-spacing: 0.5px;
        }
        #hub-ss-hint {
          position: relative; z-index: 2;
          margin-top: 64px;
          font-size: 16px; color: #6e7681; text-align: center;
          display: flex; align-items: center; gap: 10px;
        }
        #hub-ss-hint svg { width: 22px; height: 22px; }
        #hub-ss-devices {
          position: relative; z-index: 2;
          display: flex; gap: 16px; max-width: calc(100% - 64px);
          margin-top: 28px; overflow-x: auto; align-items: center;
        }
        #hub-ss-devices::-webkit-scrollbar { display: none; }
        #hub-ss-devices .hub-pill { padding: 16px 32px 16px 16px; min-height: 76px; }
        #hub-ss-devices .hub-pill-avatar { width: 52px; height: 52px; font-size: 24px; }
        #hub-ss-devices .hub-pill-name { font-size: 20px; }
        #hub-ss-settings {
          position: absolute; top: 24px; right: 24px; z-index: 3;
          width: 44px; height: 44px; border-radius: 12px;
          border: 1px solid #21262d; background: rgba(22,27,34,0.4);
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; transition: all 0.2s; opacity: 0.3;
        }
        #hub-ss-settings:hover { opacity: 1; background: rgba(22,27,34,0.8); }
        #hub-ss-settings:active { transform: scale(0.93); }

        /* Night mode: just a dim clock in the dark. Photos nearly black. */
        body.hub-night #hub-ss-time { opacity: 0.5; }
        body.hub-night #hub-ss-greeting, body.hub-night #hub-ss-hint { opacity: 0.3; }
        body.hub-night #hub-ss-photos .hub-ss-photo { filter: brightness(0.45); }
        body.hub-night #hub-ss-settings { opacity: 0.15; }
      </style>
      <div id="hub-ss-photos">
        <div class="hub-ss-photo kb-a" id="hub-ss-photo-a"></div>
        <div class="hub-ss-photo kb-b" id="hub-ss-photo-b"></div>
      </div>
      <div id="hub-ss-scrim"></div>
      <div id="hub-ss-settings" onclick="homehubOpenSettings()">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8b949e" stroke-width="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 1v6m0 10v6m11-11h-6M7 12H1m17.4-7.4l-4.2 4.2M9.8 14.2l-4.2 4.2m12.8 0l-4.2-4.2M9.8 9.8L5.6 5.6"/>
        </svg>
      </div>
      <div id="hub-ss-greeting"></div>
      <div id="hub-ss-time">--:--</div>
      <div id="hub-ss-date">---</div>
      <div id="hub-ss-hint">${SVG.phone} Dock a phone to get started</div>
      <div id="hub-ss-devices"></div>
    `;

    document.body.appendChild(screensaverEl);

    ssPhotoLayerA = document.getElementById('hub-ss-photo-a');
    ssPhotoLayerB = document.getElementById('hub-ss-photo-b');
  }

  // --- Phone Landing Page (bottom 574px, shown when user taps a bubble) ---
  // Curated quick-action tiles + notification preview. Replaces going
  // straight to AA's apps grid. User taps a tile → fades to AA → jumps
  // to that AA tab via keyboard navigation.
  function createLandingPage() {
    if (landingEl) return;

    landingEl = document.createElement('div');
    landingEl.id = 'homehub-landing';
    landingEl.style.cssText = [
      'position:fixed',
      'top:' + HUB_HEIGHT + 'px',
      'left:0',
      'right:0',
      'bottom:0',
      'z-index:99997',
      'background:#0d1117',
      'color:#e6edf3',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
      'display:flex',
      'flex-direction:column',
      'overflow:hidden',
      'pointer-events:none',
      'opacity:0',
      'user-select:none',
      '-webkit-user-select:none',
      'transition:opacity 400ms cubic-bezier(0.4,0,0.2,1)'
    ].join(';');

    landingEl.innerHTML = `
      <style>
        #homehub-landing * { box-sizing: border-box; margin: 0; padding: 0; }

        #hub-landing-content {
          flex: 1; display: flex; flex-direction: column;
          padding: 24px 40px 28px;
          overflow-y: auto;
        }
        #hub-landing-content::-webkit-scrollbar { display: none; }

        /* Tile grid — 2×2, matching the design system */
        #hub-landing-tiles {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          margin-bottom: 20px;
        }
        .hub-tile {
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          gap: 12px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.05);
          border-radius: 16px;
          padding: 24px 16px;
          cursor: pointer;
          transition: all 250ms cubic-bezier(0.4,0,0.2,1);
          min-height: 130px;
          animation: hub-tile-in 400ms cubic-bezier(0.16,1,0.3,1) both;
        }
        .hub-tile:nth-child(1) { animation-delay: 0ms; }
        .hub-tile:nth-child(2) { animation-delay: 60ms; }
        .hub-tile:nth-child(3) { animation-delay: 120ms; }
        .hub-tile:nth-child(4) { animation-delay: 180ms; }
        @keyframes hub-tile-in {
          from { opacity: 0; transform: translateY(12px) scale(0.96); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .hub-tile:active {
          transform: scale(0.95);
          background: rgba(255,255,255,0.06);
        }
        .hub-tile svg {
          width: 40px; height: 40px; color: #8b949e;
          transition: color 200ms;
        }
        .hub-tile:active svg { color: #f0f6fc; }
        .hub-tile-label {
          font-size: 20px; font-weight: 400; color: #f0f6fc;
          letter-spacing: 0.3px;
        }
        /* Uncalibrated tiles — dimmed, with setup badge */
        .hub-tile.uncalibrated {
          opacity: 0.45;
        }
        .hub-tile.uncalibrated:active {
          opacity: 0.8;
        }
        .hub-tile-badge {
          font-size: 11px; font-weight: 600; color: #58a6ff;
          text-transform: uppercase; letter-spacing: 1px;
          margin-top: 4px;
        }
        /* Navigating state — tile pulses while AA navigation happens in background */
        .hub-tile.navigating {
          animation: hub-tile-pulse 1s ease-in-out infinite;
        }
        @keyframes hub-tile-pulse {
          0%,100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        /* Notification preview area */
        #hub-landing-notifs {
          flex: 1; min-height: 0;
          display: flex; flex-direction: column; gap: 8px;
        }
        #hub-landing-notifs-label {
          font-size: 13px; font-weight: 600; color: #484f58;
          text-transform: uppercase; letter-spacing: 1.5px;
          margin-bottom: 4px;
        }
        .hub-notif-row {
          display: flex; align-items: center; gap: 12px;
          padding: 12px 16px;
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.03);
          border-radius: 12px;
          cursor: pointer;
          transition: all 200ms cubic-bezier(0.4,0,0.2,1);
        }
        .hub-notif-row:active { transform: scale(0.98); background: rgba(255,255,255,0.05); }
        .hub-notif-icon {
          width: 32px; height: 32px; border-radius: 8px;
          background: rgba(255,255,255,0.06);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0; color: #8b949e;
        }
        .hub-notif-icon svg { width: 18px; height: 18px; }
        .hub-notif-text {
          flex: 1; min-width: 0;
          font-size: 15px; font-weight: 400; color: #8b949e;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .hub-notif-empty {
          font-size: 15px; font-weight: 300; color: #484f58;
          padding: 12px 0; text-align: center;
        }
        .hub-notif-check {
          display: flex; align-items: center; gap: 10px;
          padding: 14px 16px;
          background: rgba(88,166,255,0.06);
          border: 1px solid rgba(88,166,255,0.12);
          border-radius: 12px;
          cursor: pointer;
          transition: all 200ms cubic-bezier(0.4,0,0.2,1);
        }
        .hub-notif-check:active { transform: scale(0.98); background: rgba(88,166,255,0.1); }
        .hub-notif-check.navigating {
          animation: hub-tile-pulse 1s ease-in-out infinite;
        }
        .hub-notif-check-icon {
          width: 28px; height: 28px; border-radius: 8px;
          background: rgba(88,166,255,0.1);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0; color: #58a6ff;
        }
        .hub-notif-check-icon svg { width: 16px; height: 16px; }
        .hub-notif-check-text {
          flex: 1; font-size: 14px; font-weight: 400; color: #8b949e;
        }
        .hub-notif-check-arrow { color: #484f58; }
        .hub-notif-check-arrow svg { width: 16px; height: 16px; }

        /* Full Apps Grid link — tertiary, text only */
        #hub-landing-apps-link {
          display: flex; align-items: center; justify-content: center; gap: 8px;
          padding: 14px;
          margin-top: 12px;
          font-size: 16px; font-weight: 400; color: #58a6ff;
          cursor: pointer;
          transition: all 200ms cubic-bezier(0.4,0,0.2,1);
        }
        #hub-landing-apps-link:active { transform: scale(0.96); }
        #hub-landing-apps-link svg { width: 18px; height: 18px; }
      </style>
      <div id="hub-landing-content">
        <div id="hub-landing-tiles">
          <div class="hub-tile" data-app="phone">
            ${SVG.phoneTab}
            <div class="hub-tile-label">Phone</div>
            <div class="hub-tile-badge" style="display:none">Setup needed</div>
          </div>
          <div class="hub-tile" data-app="messages">
            ${SVG.messages}
            <div class="hub-tile-label">Messages</div>
            <div class="hub-tile-badge" style="display:none">Setup needed</div>
          </div>
          <div class="hub-tile" data-app="music">
            ${SVG.musicTab}
            <div class="hub-tile-label">Music</div>
            <div class="hub-tile-badge" style="display:none">Setup needed</div>
          </div>
          <div class="hub-tile" data-app="apps">
            ${SVG.apps}
            <div class="hub-tile-label">Apps</div>
          </div>
        </div>
        <div id="hub-landing-notifs">
          <div id="hub-landing-notifs-label">Notifications</div>
          <div class="hub-notif-check" id="hub-notif-check-aa" onclick="homehubOpenNotifications()">
            <div class="hub-notif-check-icon">${SVG.messages}</div>
            <div class="hub-notif-check-text">Check phone for notifications</div>
            <div class="hub-notif-check-arrow">${SVG.arrowRight}</div>
          </div>
        </div>
        <div id="hub-landing-apps-link" onclick="homehubOpenFullApps()">
          Full Apps Grid
          ${SVG.arrowRight}
        </div>
      </div>
    `;

    document.body.appendChild(landingEl);

    // Wire up tile click handlers
    var tiles = landingEl.querySelectorAll('.hub-tile[data-app]');
    for (var i = 0; i < tiles.length; i++) {
      (function(tile) {
        tile.addEventListener('click', function() {
          var app = tile.getAttribute('data-app');
          if (app === 'apps') {
            // Apps tile — no calibration needed, just go to AA dashboard
            tile.classList.add('navigating');
            sendCmd('home');
            setTimeout(function() {
              tile.classList.remove('navigating');
              showAAView();
            }, 600);
            return;
          }
          // Check if this app is calibrated
          var pos = appPositions[masterDeviceId] && appPositions[masterDeviceId][app];
          if (!pos) {
            // Not calibrated — start full calibration flow
            startCalibration(null);
            return;
          }
          // Calibrated — navigate invisibly (landing page stays visible)
          tile.classList.add('navigating');
          navigateToApp(app, function() {
            tile.classList.remove('navigating');
            showAAView();
          });
        });
      })(tiles[i]);
    }
  }

  // Update tile visual state based on calibration
  function updateLandingTileState() {
    if (!landingEl) return;
    var calibrated = isPhoneCalibrated(masterDeviceId);
    var tiles = landingEl.querySelectorAll('.hub-tile[data-app]');
    for (var i = 0; i < tiles.length; i++) {
      var tile = tiles[i];
      var app = tile.getAttribute('data-app');
      if (app === 'apps') continue; // Apps tile always works
      var pos = appPositions[masterDeviceId] && appPositions[masterDeviceId][app];
      var badge = tile.querySelector('.hub-tile-badge');
      if (pos) {
        tile.classList.remove('uncalibrated');
        if (badge) badge.style.display = 'none';
      } else {
        tile.classList.add('uncalibrated');
        if (badge) badge.style.display = 'block';
      }
    }
  }

  // Open full AA apps grid (sendCmd('home') goes to AA dashboard)
  function homehubOpenFullApps() {
    showAAView();
    sendCmd('home');
  }

  // Open AA notifications panel — replays the calibrated touch sequence.
  // Always sends 'home' first to reset to the AA dashboard, so it works
  // even if the user is already on the notifications page (prevents toggle-off).
  // Follows the same pattern as phone/messages tiles: navigate invisibly
  // (landing page stays visible), then reveal AA after the panel is open.
  function homehubOpenNotifications() {
    var pos = getNotifsPos();
    var notifEl = document.getElementById('hub-notif-check-aa');
    if (pos) {
      // Add navigating pulse to the notification button
      if (notifEl) notifEl.classList.add('navigating');
      // 1. Go to AA dashboard (resets to top of app grid) — landing page stays visible
      sendCmd('home');
      // 2. Wait for dashboard to render, then replay the recorded sequence
      setTimeout(function() {
        if (pos.sequence && pos.sequence.length > 0) {
          replayTouchSequence(pos.sequence, function() {
            // Notifications panel should now be open — reveal AA
            if (notifEl) notifEl.classList.remove('navigating');
            showAAView();
          });
        } else if (pos.x !== undefined && pos.y !== undefined) {
          // Fallback: just tap the recorded position
          sendTouchAt(pos.x, pos.y);
          setTimeout(function() {
            if (notifEl) notifEl.classList.remove('navigating');
            showAAView();
          }, 800);
        } else {
          if (notifEl) notifEl.classList.remove('navigating');
          showAAView();
        }
      }, 800);
    } else {
      // No calibration — fall back to apps grid
      homehubOpenFullApps();
    }
  }
  window.homehubOpenFullApps = homehubOpenFullApps;
  window.homehubOpenNotifications = homehubOpenNotifications;

  // --- Calibration Flow ---
  // First time a phone connects (or when user taps an uncalibrated tile),
  // we run a quick calibration: show the AA dashboard through a semi-transparent
  // overlay and ask the user to tap each app (Phone, Messages, Music).
  // The touch coordinates are recorded and cached in localStorage per device.
  //
  // Calibration steps:
  //   0 = intro screen ("Let's set up quick access")
  //   1 = "Tap your Phone app"
  //   2 = "Tap your Messages app"
  //   3 = "Tap your Music app"
  //   4 = done → save and go to landing page

  var CALIBRATION_APPS = [
    { key: 'phone',    label: 'Phone',    icon: SVG.phoneTab },
    { key: 'messages', label: 'Messages', icon: SVG.messages },
    { key: 'music',    label: 'Music',    icon: SVG.musicTab }
  ];

  function startCalibration(specificApp) {
    // specificApp: if set, only calibrate this one app (user tapped an
    // uncalibrated tile). If null, calibrate all three.
    calibrating = true;
    calibrationStep = 0;
    // Preserve existing positions so skipped apps keep their calibration.
    // finishCalibration overwrites appPositions[masterDeviceId] entirely,
    // so we must seed calibrationData with what we already have.
    var existing = appPositions[masterDeviceId] || {};
    calibrationData = JSON.parse(JSON.stringify(existing));

    // If only calibrating one app, skip the intro and go straight to that step
    if (specificApp) {
      for (var i = 0; i < CALIBRATION_APPS.length; i++) {
        if (CALIBRATION_APPS[i].key === specificApp) {
          calibrationStep = i + 1;
          break;
        }
      }
    }

    showCalibrationOverlay();
  }

  function showCalibrationOverlay() {
    if (calibrationEl) calibrationEl.remove();

    calibrationEl = document.createElement('div');
    calibrationEl.id = 'homehub-calibration';
    calibrationEl.style.cssText = [
      'position:fixed',
      'top:0', 'left:0', 'right:0', 'bottom:0',
      'z-index:100002',
      'background:rgba(13,17,23,0.75)',
      'backdrop-filter:blur(2px)',
      '-webkit-backdrop-filter:blur(2px)',
      'color:#e6edf3',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
      'display:flex',
      'flex-direction:column',
      'align-items:center',
      'user-select:none',
      '-webkit-user-select:none',
      'opacity:0',
      'transition:opacity 300ms ease'
    ].join(';');

    if (calibrationStep === 0) {
      // Intro screen
      calibrationEl.innerHTML = `
        <style>
          #homehub-calibration * { box-sizing: border-box; margin: 0; padding: 0; }
          #hub-cal-intro {
            margin: auto;
            text-align: center;
            max-width: 440px;
            padding: 0 40px;
          }
          #hub-cal-intro-icon {
            width: 80px; height: 80px; margin: 0 auto 24px;
            color: #58a6ff; opacity: 0.8;
          }
          #hub-cal-intro-icon svg { width: 80px; height: 80px; }
          #hub-cal-intro-title {
            font-size: 28px; font-weight: 300; color: #f0f6fc;
            margin-bottom: 12px; letter-spacing: -0.5px;
          }
          #hub-cal-intro-sub {
            font-size: 17px; font-weight: 300; color: #8b949e;
            line-height: 1.5; margin-bottom: 32px;
          }
          #hub-cal-intro-btn {
            padding: 16px 48px; border-radius: 14px;
            background: rgba(88,166,255,0.15);
            border: 1px solid rgba(88,166,255,0.4);
            color: #58a6ff; font-family: inherit;
            font-size: 18px; font-weight: 600;
            cursor: pointer;
            transition: all 200ms cubic-bezier(0.4,0,0.2,1);
          }
          #hub-cal-intro-btn:active { transform: scale(0.96); }
          #hub-cal-skip {
            margin-top: 16px;
            font-size: 15px; color: #484f58;
            cursor: pointer; background: none; border: none;
            font-family: inherit;
          }
          #hub-cal-skip:hover { color: #8b949e; }
        </style>
        <div id="hub-cal-intro">
          <div id="hub-cal-intro-icon">${SVG.phoneTab}</div>
          <div id="hub-cal-intro-title">Quick App Setup</div>
          <div id="hub-cal-intro-sub">
            Tap each app on your phone's dashboard so the hub can open it
            directly. This takes about 10 seconds and only needs to be done once.
          </div>
          <button id="hub-cal-intro-btn">Get Started</button>
          <button id="hub-cal-skip">Skip for now</button>
        </div>
      `;
    } else {
      // App-tapping step
      var app = CALIBRATION_APPS[calibrationStep - 1];
      var progress = '';
      for (var i = 0; i < CALIBRATION_APPS.length; i++) {
        var done = (i < calibrationStep - 1) ||
          (calibrationData[CALIBRATION_APPS[i].key] !== undefined);
        progress += '<div class="hub-cal-dot' + (done ? ' done' : '') +
          (i === calibrationStep - 1 ? ' current' : '') + '"></div>';
      }

      calibrationEl.innerHTML = `
        <style>
          #homehub-calibration * { box-sizing: border-box; margin: 0; padding: 0; }
          #hub-cal-header {
            position: fixed; top: 0; left: 0; right: 0;
            padding: 40px 40px 20px;
            text-align: center;
            background: linear-gradient(180deg, rgba(13,17,23,0.9) 0%, rgba(13,17,23,0) 100%);
            pointer-events: none;
            z-index: 2;
          }
          #hub-cal-instruction {
            font-size: 24px; font-weight: 400; color: #f0f6fc;
            margin-bottom: 12px;
          }
          #hub-cal-sub {
            font-size: 15px; font-weight: 300; color: #8b949e;
          }
          #hub-cal-progress {
            display: flex; gap: 8px; justify-content: center;
            margin-top: 16px;
          }
          .hub-cal-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: rgba(255,255,255,0.15);
            transition: all 200ms;
          }
          .hub-cal-dot.done { background: #3fb950; }
          .hub-cal-dot.current {
            background: #58a6ff;
            box-shadow: 0 0 8px rgba(88,166,255,0.5);
          }
          #hub-cal-touch-area {
            position: fixed;
            top: ${HUB_HEIGHT}px; left: 0; right: 0; bottom: 0;
            z-index: 1;
            cursor: crosshair;
            touch-action: none;
          }
          #hub-cal-reticle {
            position: fixed;
            width: 60px; height: 60px;
            border: 2px solid rgba(88,166,255,0.6);
            border-radius: 50%;
            pointer-events: none;
            z-index: 3;
            transform: translate(-50%, -50%);
            display: none;
            transition: opacity 100ms;
          }
          #hub-cal-reticle::after {
            content: '';
            position: absolute;
            top: 50%; left: 50%;
            width: 6px; height: 6px;
            background: #58a6ff;
            border-radius: 50%;
            transform: translate(-50%, -50%);
          }
          #hub-cal-skip-step {
            position: fixed; bottom: 24px; right: 24px;
            font-size: 15px; color: #484f58;
            cursor: pointer; background: none; border: none;
            font-family: inherit; z-index: 4;
          }
          #hub-cal-skip-step:hover { color: #8b949e; }
        </style>
        <div id="hub-cal-header">
          <div id="hub-cal-instruction">Tap your ${app.label} app</div>
          <div id="hub-cal-sub">Scroll to find it if needed, then tap the ${app.label} icon</div>
          <div id="hub-cal-progress">${progress}</div>
        </div>
        <div id="hub-cal-touch-area"></div>
        <div id="hub-cal-reticle"></div>
        <button id="hub-cal-skip-step">Skip this app</button>
      `;
    }

    document.body.appendChild(calibrationEl);
    requestAnimationFrame(function() {
      if (calibrationEl) calibrationEl.style.opacity = '1';
    });

    // Wire up handlers
    if (calibrationStep === 0) {
      // Intro screen
      var startBtn = calibrationEl.querySelector('#hub-cal-intro-btn');
      var skipBtn = calibrationEl.querySelector('#hub-cal-skip');
      if (startBtn) startBtn.addEventListener('click', function() {
        calibrationStep = 1;
        // Fade to AA dashboard (show AA view, send home)
        showAAView();
        sendCmd('home');
        setTimeout(function() {
          showCalibrationOverlay();
        }, 800);
      });
      if (skipBtn) skipBtn.addEventListener('click', function() {
        closeCalibration();
      });
    } else {
      // App-tapping step — user scrolls the AA dashboard to find the app,
      // then taps it to record its position. Scrolls ARE forwarded to AA
      // so the dashboard moves, but the final TAP is NOT forwarded — we
      // just record the coordinates. This keeps the user on the dashboard
      // so they can calibrate the next app without going back.
      //
      // Technique: "deferred down" — we don't send the DOWN event to AA
      // until we detect movement (>5px). If the user lifts their finger
      // without significant movement, it was a tap → record only, don't
      // forward. If they did move, it was a scroll → send the deferred
      // DOWN at the original position, then all the MOVEs, then the UP.
      var touchArea = calibrationEl.querySelector('#hub-cal-touch-area');
      var reticle = calibrationEl.querySelector('#hub-cal-reticle');
      var skipStepBtn = calibrationEl.querySelector('#hub-cal-skip-step');

      if (touchArea) {
        // Recording state for this calibration step
        var stepSequence = [];      // all touch events: {x, y, action, delay}
        var stepStartTime = 0;
        var pointerDownPos = null;  // {x, y} display coords of pointerdown
        var scrolling = false;      // true once we've sent the deferred DOWN
        var pendingMoves = [];      // moves buffered before deferred DOWN
        var lastEventTime = 0;

        // Show reticle following finger
        touchArea.addEventListener('pointermove', function(e) {
          if (reticle) {
            reticle.style.display = 'block';
            reticle.style.left = e.clientX + 'px';
            reticle.style.top = e.clientY + 'px';
          }
        });
        touchArea.addEventListener('pointerleave', function() {
          if (reticle) reticle.style.display = 'none';
        });

        // Pointer down — record but DON'T forward to AA yet (deferred)
        touchArea.addEventListener('pointerdown', function(e) {
          e.preventDefault();
          var dispX = e.clientX;
          var dispY = e.clientY;
          pointerDownPos = { x: dispX, y: dispY };
          scrolling = false;
          pendingMoves = [];
          var now = Date.now();
          if (stepStartTime === 0) stepStartTime = now;
          var delay = now - (lastEventTime || stepStartTime);
          lastEventTime = now;
          // Record in sequence but don't send to AA yet
          stepSequence.push({ x: dispX, y: dispY, action: 14, delay: delay });
        });

        // Pointer move — if scrolling, forward to AA; if not yet, check threshold
        touchArea.addEventListener('pointermove', function(e) {
          if (!pointerDownPos) return;
          e.preventDefault();
          var dispX = e.clientX;
          var dispY = e.clientY;
          var dx = dispX - pointerDownPos.x;
          var dy = dispY - pointerDownPos.y;
          var dist = Math.sqrt(dx * dx + dy * dy);
          var now = Date.now();
          var delay = now - lastEventTime;
          lastEventTime = now;

          if (!scrolling) {
            if (dist > 8) {
              // Movement detected — this is a scroll. Send the deferred DOWN
              // at the original position, then catch up with buffered moves.
              scrolling = true;
              sendTouchEvent(pointerDownPos.x, pointerDownPos.y, 14);
              // Send any buffered moves
              for (var i = 0; i < pendingMoves.length; i++) {
                sendTouchEvent(pendingMoves[i].x, pendingMoves[i].y, 15);
              }
              pendingMoves = [];
            } else {
              // Not enough movement yet — buffer the move
              pendingMoves.push({ x: dispX, y: dispY });
              stepSequence.push({ x: dispX, y: dispY, action: 15, delay: delay });
              return;
            }
          }

          // We're scrolling — forward to AA and record
          stepSequence.push({ x: dispX, y: dispY, action: 15, delay: delay });
          sendTouchEvent(dispX, dispY, 15);
        });

        // Pointer up — check if tap (record only) or scroll (forward UP)
        touchArea.addEventListener('pointerup', function(e) {
          if (!pointerDownPos) return;
          e.preventDefault();
          var dispX = e.clientX;
          var dispY = e.clientY;
          var now = Date.now();
          var delay = now - lastEventTime;
          lastEventTime = now;

          var dx = dispX - pointerDownPos.x;
          var dy = dispY - pointerDownPos.y;
          var dist = Math.sqrt(dx * dx + dy * dy);

          if (scrolling) {
            // This was a scroll — send UP to AA, record it, keep recording
            stepSequence.push({ x: dispX, y: dispY, action: 16, delay: delay });
            sendTouchEvent(dispX, dispY, 16);
            pointerDownPos = null;
            scrolling = false;
            // Don't advance — user is still looking for the app
          } else if (dist < 15) {
            // This was a TAP — DON'T forward to AA, just record
            // Record the UP in the sequence (for replay later)
            stepSequence.push({ x: dispX, y: dispY, action: 16, delay: delay });
            // Also remove the DOWN from the sequence since it wasn't a scroll
            // Actually, keep it — during replay we WANT the tap to be sent.
            // The sequence now contains: [scrolls...] + [DOWN at tap pos, UP at tap pos]
            // During replay, this will scroll then tap, opening the app. Perfect.

            var app = CALIBRATION_APPS[calibrationStep - 1];
            calibrationData[app.key] = {
              x: dispX, y: dispY,
              sequence: stepSequence.slice()
            };

            // Advance to next step
            calibrationStep++;
            pointerDownPos = null;
            if (calibrationStep > CALIBRATION_APPS.length) {
              finishCalibration();
            } else {
              if (reticle) {
                reticle.style.background = 'rgba(63,185,80,0.3)';
                reticle.style.borderColor = '#3fb950';
              }
              setTimeout(function() {
                showCalibrationOverlay();
              }, 400);
            }
          } else {
            // Moved more than 15px but never crossed the scroll threshold
            // (shouldn't happen, but handle gracefully) — treat as tap
            stepSequence.push({ x: dispX, y: dispY, action: 16, delay: delay });
            var app2 = CALIBRATION_APPS[calibrationStep - 1];
            calibrationData[app2.key] = {
              x: pointerDownPos.x, y: pointerDownPos.y,
              sequence: stepSequence.slice()
            };
            calibrationStep++;
            pointerDownPos = null;
            if (calibrationStep > CALIBRATION_APPS.length) {
              finishCalibration();
            } else {
              setTimeout(function() { showCalibrationOverlay(); }, 400);
            }
          }
        });

        // Handle pointercancel
        touchArea.addEventListener('pointercancel', function(e) {
          if (!pointerDownPos) return;
          if (scrolling) {
            sendTouchEvent(e.clientX, e.clientY, 16);
            stepSequence.push({ x: e.clientX, y: e.clientY, action: 16, delay: 0 });
          }
          pointerDownPos = null;
          scrolling = false;
        });
      }

      if (skipStepBtn) skipStepBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        calibrationStep++;
        if (calibrationStep > CALIBRATION_APPS.length) {
          finishCalibration();
        } else {
          showCalibrationOverlay();
        }
      });
    }
  }

  function finishCalibration() {
    // Save calibration data
    if (masterDeviceId) {
      appPositions[masterDeviceId] = calibrationData;
      saveAppPositions();
    }
    closeCalibration();
    // Go to landing page
    showLandingView();
  }

  function closeCalibration() {
    calibrating = false;
    calibrationStep = 0;
    calibrationData = {};
    if (calibrationEl) {
      calibrationEl.style.opacity = '0';
      var el = calibrationEl;
      calibrationEl = null;
      setTimeout(function() { el.remove(); }, 300);
    }
  }

  // Re-calibrate: clear cached positions for current phone and restart
  function homehubRecalibrate() {
    if (masterDeviceId && appPositions[masterDeviceId]) {
      delete appPositions[masterDeviceId];
      saveAppPositions();
    }
    // Close settings if open
    homehubCloseSettings();
    // Start full calibration
    startCalibration(null);
  }
  window.homehubRecalibrate = homehubRecalibrate;

  // --- Notifications button calibration ---
  // Uses the same "deferred down" technique as app calibration:
  // scrolls are forwarded to AA, but the final TAP is recorded (not forwarded).
  // Stores a touch sequence that gets replayed when opening notifications.
  // The replay always starts with sendCmd('home') to reset to the dashboard,
  // so it works even if the user is already on the notifications page.
  function getNotifsPos() {
    try {
      var raw = localStorage.getItem('homehub.notifsPos');
      if (raw) return JSON.parse(raw);
    } catch(e) {}
    return null;
  }
  function saveNotifsPos(data) {
    try { localStorage.setItem('homehub.notifsPos', JSON.stringify(data)); } catch(e) {}
  }

  var notifsCalEl = null;
  var notifsCalSequence = [];
  var notifsCalStart = 0;
  var notifsCalLastTime = 0;

  function startNotifsCalibration() {
    // Show AA dashboard first
    showAAView();
    sendCmd('home');

    // Wait for dashboard to render, then show the calibration overlay
    setTimeout(function() {
      notifsCalSequence = [];
      notifsCalStart = 0;
      notifsCalLastTime = 0;

      notifsCalEl = document.createElement('div');
      notifsCalEl.id = 'homehub-notifs-cal';
      notifsCalEl.style.cssText = [
        'position:fixed', 'top:0', 'left:0', 'right:0', 'bottom:0',
        'z-index:100002',
        'background:rgba(13,17,23,0.75)',
        'backdrop-filter:blur(2px)',
        '-webkit-backdrop-filter:blur(2px)',
        'color:#e6edf3',
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif',
        'display:flex', 'flex-direction:column', 'align-items:center',
        'user-select:none', '-webkit-user-select:none',
        'opacity:0', 'transition:opacity 300ms ease'
      ].join(';');

      notifsCalEl.innerHTML = '<style>' +
        '#homehub-notifs-cal * { box-sizing:border-box; margin:0; padding:0; }' +
        '#hub-ncal-header { position:fixed; top:0; left:0; right:0; padding:40px 40px 20px;' +
          'text-align:center; background:linear-gradient(180deg,rgba(13,17,23,0.9) 0%,rgba(13,17,23,0) 100%);' +
          'pointer-events:none; z-index:2; }' +
        '#hub-ncal-instruction { font-size:24px; font-weight:400; color:#f0f6fc; margin-bottom:12px; }' +
        '#hub-ncal-sub { font-size:15px; font-weight:300; color:#8b949e; }' +
        '#hub-ncal-touch-area { position:fixed; top:' + HUB_HEIGHT + 'px; left:0; right:0; bottom:0;' +
          'z-index:1; cursor:crosshair; touch-action:none; }' +
        '#hub-ncal-reticle { position:fixed; width:60px; height:60px;' +
          'border:2px solid rgba(63,185,80,0.6); border-radius:50%;' +
          'pointer-events:none; z-index:3; transform:translate(-50%,-50%);' +
          'display:none; transition:opacity 100ms; }' +
        '#hub-ncal-reticle::after { content:""; position:absolute; top:50%; left:50%;' +
          'width:6px; height:6px; background:#3fb950; border-radius:50%;' +
          'transform:translate(-50%,-50%); }' +
        '#hub-ncal-cancel { position:fixed; bottom:24px; right:24px;' +
          'font-size:15px; color:#484f58; cursor:pointer; background:none; border:none;' +
          'font-family:inherit; z-index:4; }' +
        '#hub-ncal-cancel:hover { color:#8b949e; }' +
        '</style>' +
        '<div id="hub-ncal-header">' +
          '<div id="hub-ncal-instruction">Tap the notifications bell icon</div>' +
          '<div id="hub-ncal-sub">Scroll to find it if needed, then tap the bell (bottom right)</div>' +
        '</div>' +
        '<div id="hub-ncal-touch-area"></div>' +
        '<div id="hub-ncal-reticle"></div>' +
        '<button id="hub-ncal-cancel">Cancel</button>';

      document.body.appendChild(notifsCalEl);
      requestAnimationFrame(function() {
        if (notifsCalEl) notifsCalEl.style.opacity = '1';
      });

      // Wire up the same "deferred down" technique as app calibration
      var touchArea = notifsCalEl.querySelector('#hub-ncal-touch-area');
      var reticle = notifsCalEl.querySelector('#hub-ncal-reticle');
      var cancelBtn = notifsCalEl.querySelector('#hub-ncal-cancel');

      var pointerDownPos = null;
      var scrolling = false;
      var pendingMoves = [];

      if (touchArea) {
        touchArea.addEventListener('pointermove', function(e) {
          if (reticle) {
            reticle.style.display = 'block';
            reticle.style.left = e.clientX + 'px';
            reticle.style.top = e.clientY + 'px';
          }
        });
        touchArea.addEventListener('pointerleave', function() {
          if (reticle) reticle.style.display = 'none';
        });

        touchArea.addEventListener('pointerdown', function(e) {
          e.preventDefault();
          var dispX = e.clientX;
          var dispY = e.clientY;
          pointerDownPos = { x: dispX, y: dispY };
          scrolling = false;
          pendingMoves = [];
          var now = Date.now();
          if (notifsCalStart === 0) notifsCalStart = now;
          var delay = now - (notifsCalLastTime || notifsCalStart);
          notifsCalLastTime = now;
          notifsCalSequence.push({ x: dispX, y: dispY, action: 14, delay: delay });
        });

        touchArea.addEventListener('pointermove', function(e) {
          if (!pointerDownPos) return;
          e.preventDefault();
          var dispX = e.clientX;
          var dispY = e.clientY;
          var dx = dispX - pointerDownPos.x;
          var dy = dispY - pointerDownPos.y;
          var dist = Math.sqrt(dx * dx + dy * dy);
          var now = Date.now();
          var delay = now - notifsCalLastTime;
          notifsCalLastTime = now;

          if (!scrolling) {
            if (dist > 8) {
              scrolling = true;
              sendTouchEvent(pointerDownPos.x, pointerDownPos.y, 14);
              for (var i = 0; i < pendingMoves.length; i++) {
                sendTouchEvent(pendingMoves[i].x, pendingMoves[i].y, 15);
              }
              pendingMoves = [];
            } else {
              pendingMoves.push({ x: dispX, y: dispY });
              notifsCalSequence.push({ x: dispX, y: dispY, action: 15, delay: delay });
              return;
            }
          }
          notifsCalSequence.push({ x: dispX, y: dispY, action: 15, delay: delay });
          sendTouchEvent(dispX, dispY, 15);
        });

        touchArea.addEventListener('pointerup', function(e) {
          if (!pointerDownPos) return;
          e.preventDefault();
          var dispX = e.clientX;
          var dispY = e.clientY;
          var now = Date.now();
          var delay = now - notifsCalLastTime;
          notifsCalLastTime = now;
          var dx = dispX - pointerDownPos.x;
          var dy = dispY - pointerDownPos.y;
          var dist = Math.sqrt(dx * dx + dy * dy);

          if (scrolling) {
            notifsCalSequence.push({ x: dispX, y: dispY, action: 16, delay: delay });
            sendTouchEvent(dispX, dispY, 16);
            pointerDownPos = null;
            scrolling = false;
          } else if (dist < 15) {
            // TAP — record but don't forward to AA
            notifsCalSequence.push({ x: dispX, y: dispY, action: 16, delay: delay });
            saveNotifsPos({
              x: dispX, y: dispY,
              sequence: notifsCalSequence.slice()
            });
            if (reticle) {
              reticle.style.background = 'rgba(63,185,80,0.3)';
              reticle.style.borderColor = '#3fb950';
            }
            // Close overlay and return to landing
            setTimeout(function() {
              closeNotifsCalibration();
              showLandingView();
            }, 400);
          } else {
            notifsCalSequence.push({ x: dispX, y: dispY, action: 16, delay: delay });
            saveNotifsPos({
              x: pointerDownPos.x, y: pointerDownPos.y,
              sequence: notifsCalSequence.slice()
            });
            setTimeout(function() {
              closeNotifsCalibration();
              showLandingView();
            }, 400);
          }
        });

        touchArea.addEventListener('pointercancel', function(e) {
          if (!pointerDownPos) return;
          if (scrolling) {
            sendTouchEvent(e.clientX, e.clientY, 16);
          }
          pointerDownPos = null;
          scrolling = false;
        });
      }

      if (cancelBtn) {
        cancelBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          closeNotifsCalibration();
          showLandingView();
        });
      }
    }, 800);
  }

  function closeNotifsCalibration() {
    if (notifsCalEl) {
      notifsCalEl.style.opacity = '0';
      var el = notifsCalEl;
      notifsCalEl = null;
      setTimeout(function() { el.remove(); }, 300);
    }
    notifsCalSequence = [];
    notifsCalStart = 0;
    notifsCalLastTime = 0;
  }
  window.startNotifsCalibration = startNotifsCalibration;

  // --- Photo screensaver (Ken Burns) ---
  // Sidecar serves /photos (list) and /photo/<name> (image, CORP headers set).
  // 15s per photo, 2.5s crossfade, endless gentle drift — "like memory,
  // not a slideshow." With no photos on the Pi, falls back to the dark clock.
  function refreshPhotos() {
    xhrGet(SIDECAR_URL + '/photos', function(data) {
      ssPhotos = (data && data.photos) || [];
      if (screensaverEl) {
        if (ssPhotos.length) screensaverEl.classList.add('has-photos');
        else screensaverEl.classList.remove('has-photos');
      }
      if (ssPhotos.length) showNextPhoto();
    });
  }

  function showNextPhoto() {
    if (!ssPhotos.length || !ssPhotoLayerA || !ssPhotoLayerB) return;
    var incoming = ssPhotoActiveIsA ? ssPhotoLayerB : ssPhotoLayerA;
    var outgoing = ssPhotoActiveIsA ? ssPhotoLayerA : ssPhotoLayerB;
    var name = ssPhotos[ssPhotoIdx % ssPhotos.length];
    ssPhotoIdx++;
    incoming.style.backgroundImage = 'url(' + SIDECAR_URL + '/photo/' + encodeURIComponent(name) + ')';
    incoming.classList.add('visible');
    outgoing.classList.remove('visible');
    ssPhotoActiveIsA = !ssPhotoActiveIsA;
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
      'animation:hub-ring-arrive 350ms cubic-bezier(0.16,1,0.3,1),hub-ring-pulse 2s ease-in-out 350ms infinite',
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
        /* The banner doesn't appear — it ARRIVES, like someone walking in.
           Uses the "translate" property so it composes with the inline
           "transform" positioning (translateX/-50%). */
        @keyframes hub-ring-arrive {
          from { opacity: 0; translate: 0 16px; }
          to { opacity: 1; translate: 0 0; }
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
      // Skip the DOM rewrite entirely when nothing changed — this keeps
      // entrance animations from replaying on every poll and preserves
      // touch/press state on the pills.
      if (lastRenderedHtml[container.id] === html) continue;
      lastRenderedHtml[container.id] = html;
      container.innerHTML = html;
      var pills = container.querySelectorAll('.hub-pill[data-device-id]');
      for (var k = 0; k < pills.length; k++) {
        (function(pill) {
          pill.addEventListener('click', function() {
            var id = pill.getAttribute('data-device-id');
            if (id && window.projection && window.projection.ipc && window.projection.ipc.selectDevice) {
              window.projection.ipc.selectDevice(id);
              masterDeviceId = id;
              // Show the phone landing page instead of going straight to AA.
              // User picks a tab (Phone/Messages/Music/Apps) from the landing page.
              showLandingView();
              renderDevices();
            }
          });
        })(pills[k]);
      }
    }

    if (hint) hint.innerHTML = activeIdx ? SVG.phone + ' Select a phone to open Android Auto or CarPlay' : SVG.phone + ' Dock a phone to get started';
  }

  // --- View switching: home screen vs AA/CarPlay view ---
  // KEY DESIGN: The screensaver is ALWAYS display:flex (never display:none).
  // We toggle visibility with opacity + pointer-events only. This avoids
  // layout reflows when showing the screensaver, which is critical for the
  // unplug case — LIVI's React app switches to its Home page before our
  // event handler fires, so we need the screensaver to cover instantly
  // in the same frame, with zero reflow delay.
  //
  // - opacity:0 + pointer-events:none = invisible, touch passes through to AA
  // - opacity:1 + pointer-events:auto  = visible, captures touch (home screen)
  //
  // The CSS transition (opacity 400ms ease) gives smooth fades for user
  // actions (home button, bubble tap). For unplug, we temporarily disable
  // the transition for an instant cover.

  // showHomeView: smooth fade IN of the screensaver (home screen).
  //   Used by: home button from landing, phone connect, unplug.
  //   Hides both landing page and AA view.
  function showHomeView() {
    viewingAA = false;
    viewingLanding = false;
    if (barEl) barEl.classList.remove('aa-mode');
    if (landingEl) {
      landingEl.style.opacity = '0';
      landingEl.style.pointerEvents = 'none';
    }
    if (screensaverEl) {
      screensaverEl.style.opacity = '1';
      screensaverEl.style.transform = 'scale(1)';
      screensaverEl.style.pointerEvents = 'auto';
    }
    setTimeout(function() {
      if (!viewingAA && !viewingLanding && barEl) barEl.style.display = 'none';
    }, 650);
  }

  // showLandingView: fade IN the landing page, fade OUT the screensaver.
  //   Used by: bubble tap. The hub bar is shown in aa-mode (compacted).
  //   AA video is hidden underneath the landing page.
  function showLandingView() {
    viewingAA = false;
    viewingLanding = true;
    navToProjection();
    if (barEl) {
      barEl.style.display = 'flex';
      barEl.classList.add('aa-mode');
      barEl.classList.remove('bar-reveal');
      void barEl.offsetHeight;
      barEl.classList.add('bar-reveal');
    }
    if (screensaverEl) {
      screensaverEl.style.opacity = '0';
      screensaverEl.style.transform = 'scale(0.98)';
      screensaverEl.style.pointerEvents = 'none';
    }
    if (landingEl) {
      landingEl.style.opacity = '1';
      landingEl.style.pointerEvents = 'auto';
    }
    updateLandingTileState();
    pollNowPlaying();
  }

  // showAAView: fade OUT both screensaver and landing page, revealing AA video.
  //   Used by: landing tile tap, full apps grid link.
  function showAAView() {
    viewingAA = true;
    viewingLanding = false;
    navToProjection();
    if (barEl) {
      barEl.style.display = 'flex';
      barEl.classList.add('aa-mode');
      barEl.classList.remove('bar-reveal');
      void barEl.offsetHeight;
      barEl.classList.add('bar-reveal');
    }
    var np = document.getElementById('hub-nowplaying');
    if (np) np.style.display = 'flex';

    if (screensaverEl) {
      screensaverEl.style.opacity = '0';
      screensaverEl.style.transform = 'scale(0.98)';
      screensaverEl.style.pointerEvents = 'none';
    }
    if (landingEl) {
      landingEl.style.opacity = '0';
      landingEl.style.pointerEvents = 'none';
    }

    pollNowPlaying();
  }

  // --- Phone connection state ---
  function setPhoneConnected(connected) {
    phoneConnected = connected;

    if (connected) {
      // Phone just connected — stay on home view, show the bubble.
      showHomeView();
    } else {
      // Phone unplugged: cover with screensaver instantly.
      viewingAA = false;
      viewingLanding = false;
      if (screensaverEl) {
        screensaverEl.style.transition = 'none';
        screensaverEl.style.opacity = '1';
        screensaverEl.style.transform = 'scale(1)';
        screensaverEl.style.pointerEvents = 'auto';
        void screensaverEl.offsetHeight;
        screensaverEl.style.transition = '';
      }
      if (landingEl) {
        landingEl.style.opacity = '0';
        landingEl.style.pointerEvents = 'none';
      }
      if (barEl) {
        barEl.style.display = 'none';
        barEl.classList.remove('aa-mode');
      }
      setNowPlayingText('Nothing playing', 'Connect a phone to start');
    }
  }

  // Home button handler:
  // - In AA view → go to landing page (phone is still connected)
  // - In landing view → go to home screen
  function homehubGoHome() {
    if (viewingAA) {
      showLandingView();
    } else {
      showHomeView();
    }
  }

  // --- Ring banner (floating, works in both phone-connected and idle states) ---
  function updateRingBanner() {
    if (!ringEl) return;

    var ringing = ringState && ringState.ringing;

    // Ambient warm glow across the whole hub bar while ringing
    if (barEl) {
      if (ringing) barEl.classList.add('ringing');
      else barEl.classList.remove('ringing');
    }

    if (ringing) {
      ringEl.style.display = 'flex';
      // Position: when viewing AA, show in upper portion of screen.
      // When on home screen, show centered on full-screen screensaver.
      if (viewingAA || viewingLanding) {
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
  // Text updates crossfade (200ms) instead of snapping — calm, not abrupt.
  function setNowPlayingText(title, artist) {
    var titleEl = document.getElementById('hub-np-title');
    var artistEl = document.getElementById('hub-np-artist');
    if (!titleEl || !artistEl) return;
    if (titleEl.textContent === title && artistEl.textContent === artist) return;
    titleEl.style.opacity = '0';
    artistEl.style.opacity = '0';
    setTimeout(function() {
      titleEl.textContent = title;
      artistEl.textContent = artist;
      titleEl.style.opacity = '1';
      artistEl.style.opacity = '1';
    }, 200);
  }

  // Update now-playing bar directly from a media object (from 'media' event or readMedia()).
  // Shared by both the event handler and the polling fallback.
  function updateNowPlayingFromMedia(media) {
    if (!media) {
      setNowPlayingText('Nothing playing', 'Browse apps on your phone');
      updatePlayPauseIcon(false);
      return;
    }
    if (media.MediaSongName && media.MediaSongName !== '—') {
      var artist = media.MediaArtistName || '';
      var app = media.MediaAPPName || '';
      var sub = '';
      if (artist && app) sub = artist + ' \u00b7 ' + app;
      else if (artist) sub = artist;
      else if (app) sub = app;
      setNowPlayingText(media.MediaSongName, sub);
    } else if (media.MediaPlayStatus === 1) {
      // Playing but no song name — some apps (Sirius) report status but not metadata
      var app = media.MediaAPPName || '';
      setNowPlayingText('Playing', app || 'AA Media');
    } else {
      setNowPlayingText('Nothing playing', 'Browse apps on your phone');
    }
    // Update play/pause icon: show pause icon when playing, play icon when paused/stopped
    updatePlayPauseIcon(media.MediaPlayStatus === 1);
  }

  // Toggle play/pause button icon based on playing state.
  // Also updates mediaIsPlaying so the click handler knows whether to send 'play' or 'pause'.
  function updatePlayPauseIcon(isPlaying) {
    mediaIsPlaying = isPlaying;
    var btn = document.getElementById('hub-ctrl-play');
    if (!btn) return;
    btn.innerHTML = isPlaying ? SVG.pauseIcon : SVG.playIcon;
  }

  function pollNowPlaying() {
    if (!window.projection || !window.projection.ipc || !window.projection.ipc.readMedia) return;
    if (!phoneConnected) return; // No point polling if no phone

    window.projection.ipc.readMedia().then(function(data) {
      var media = data && data.payload && data.payload.media;
      updateNowPlayingFromMedia(media);
    }).catch(function(e) { console.log('[HomeHub] readMedia error:', e); });
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
        // Don't clobber AA protocol ring state — only clear if the current
        // ring is from the sidecar (or there's no ring at all).
        if (ringState && ringState.ringing && ringState.source === 'aa-protocol') {
          // AA protocol is handling the ring — leave it alone
        } else {
          ringState = { ringing: false };
        }
      }

      if (newRinging !== wasRinging) {
        updateRingBanner();
      } else if (newRinging) {
        updateRingBanner();
      }

      sidecarFailures = 0;
      updateHealthDot();
    }, function() {
      sidecarFailures++;
      updateHealthDot();
    });
  }

  // --- AA protocol call detection via onEvent ---
  // The patched main.js emits a 'call' projection-event via onAaPresence
  // when the AA PhoneStatus protocol reports a call state change:
  //   {callState: 'ringing', caller: '...'}  — incoming call
  //   {callState: 'active'}                  — call answered
  //   {callState: 'idle'}                    — call ended
  // Only some phones send PhoneStatus over AA. For phones that don't,
  // the Bluetooth HFP sidecar handles call detection via the /status poll.
  // We listen for both 'call' and 'attention' events here.
  var aaCallRinging = false;
  var aaCallerId = '';
  function setupAaCallListener() {
    try {
      if (!window.projection || !window.projection.ipc || !window.projection.ipc.onEvent) {
        // Retry in 2s if projection.ipc isn't ready yet
        setTimeout(setupAaCallListener, 2000);
        return;
      }

      window.projection.ipc.onEvent(function(_evt, data) {
        var d = (data || {});
        var type = typeof d.type === 'string' ? d.type : undefined;

        // Call events from patched onAaPresence — carry the call state and caller ID.
        // Only some phones send PhoneStatus over AA; for phones that don't,
        // the Bluetooth HFP sidecar handles call detection instead.
        if (type === 'call') {
          var p = d.payload || {};
          if (p.callState === 'ringing') {
            aaCallRinging = true;
            aaCallerId = p.caller || '';
            // Show ring banner if not already ringing from sidecar
            if (!ringState || !ringState.ringing) {
              ringState = {
                ringing: true,
                caller: aaCallerId || 'Incoming Call',
                phone: '',
                phoneName: masterDeviceId ? getPhoneName(masterDeviceId, 'Phone') : 'Phone',
                slot: '1',
                source: 'aa-protocol'
              };
              updateRingBanner();
            } else if (ringState.source === 'aa-protocol' && aaCallerId) {
              // Update caller ID if we already showing the banner
              ringState.caller = aaCallerId;
              updateRingBanner();
            }
          } else if (p.callState === 'active') {
            // Call was answered — clear the ring banner
            if (aaCallRinging) {
              aaCallRinging = false;
              if (ringState && ringState.ringing && ringState.source === 'aa-protocol') {
                ringState = { ringing: false };
                updateRingBanner();
              }
            }
          } else if (p.callState === 'idle') {
            // Call ended — clear the ring banner
            if (aaCallRinging) {
              aaCallRinging = false;
              aaCallerId = '';
              if (ringState && ringState.ringing && ringState.source === 'aa-protocol') {
                ringState = { ringing: false };
                updateRingBanner();
              }
            }
          }
          return;
        }

        // Attention events from ProjectionAudio — emitted when handleAudioData
        // receives AudioAttentionRinging (cmd 14) or AudioAttentionStart (cmd 12)
        if (type === 'attention') {
          var p = d.payload || {};
          if (p.kind === 'call') {
            if (p.active && p.phase === 'incoming') {
              aaCallRinging = true;
              if (!ringState || !ringState.ringing) {
                ringState = {
                  ringing: true,
                  caller: aaCallerId || 'Incoming Call',
                  phone: '',
                  phoneName: masterDeviceId ? getPhoneName(masterDeviceId, 'Phone') : 'Phone',
                  slot: '1',
                  source: 'aa-protocol'
                };
                updateRingBanner();
              }
            } else if (!p.active) {
              if (aaCallRinging) {
                aaCallRinging = false;
                if (ringState && ringState.ringing && ringState.source === 'aa-protocol') {
                  ringState = { ringing: false };
                  updateRingBanner();
                }
              }
            }
          }
          return;
        }
      });
    } catch(e) {}
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

  // Send 'home' command to AA to leave Maps and go to the launcher, and
  // 'pause' to stop auto-playing music from the previous session.
  // IMPORTANT: this is called when the device becomes ACTIVE (dock time),
  // while the screensaver still covers the screen — never on bubble tap.
  // Sending these on tap caused a visible dashboard->launcher flip ~2-3s
  // after the user was already watching, which looked broken.
  var homeCommandSent = false;
  function sendHomeCommand() {
    if (homeCommandSent) return;
    homeCommandSent = true;
    // Give the AA session a moment to finish negotiating before pressing home
    setTimeout(function() { sendCmd('home'); }, 1500);
    // Pause any auto-resumed music so the dock stays silent until asked
    setTimeout(function() { sendCmd('pause'); }, 2500);
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
    } else if (active) {
      // A phone is projecting: make sure LIVI sits on the '/' route so the
      // projection layer + native video plane are already live behind the
      // screensaver when the user taps the bubble.
      navToProjection();
      // Settle AA onto its launcher + pause autoplay NOW, behind the
      // screensaver, so the bubble tap reveals a calm, settled screen.
      sendHomeCommand();
      // Mark phone as connected so pollNowPlaying() will poll media info.
      // Only call showHomeView() on the initial connection (when phoneConnected
      // was false) — not on every device list update, which would disrupt AA viewing.
      if (!phoneConnected) {
        setPhoneConnected(true);
      } else {
        phoneConnected = true;
      }
    }
    if (!masterDeviceId && active) handleActiveDevice(active);
    renderDevices();
  }

  function setupDeviceDetection() {
    if (!window.projection || !window.projection.ipc || !window.projection.ipc.onEvent) return;

    window.projection.ipc.onEvent(function(_evt, data) {
      var d = (data || {});
      var type = typeof d.type === 'string' ? d.type : undefined;
      var payload = d.payload;

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
      } else if (type === 'media') {
        // 'media' = full snapshot arrived — update now-playing bar directly from payload.
        // This is the real-time event (no polling delay). Payload shape:
        // { payload: { media: { MediaSongName, MediaArtistName, MediaAPPName, MediaPlayStatus, ... } } }
        var mediaPayload = d.payload && d.payload.payload ? d.payload.payload : d.payload;
        var media = mediaPayload && mediaPayload.media;
        if (media) {
          updateNowPlayingFromMedia(media);
        }
      } else if (type === 'media-reset') {
        // State cleared (session switch, phone disconnect) — call readMedia() for fresh state
        pollNowPlaying();
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

    // Top bar with re-calibrate button (shown above the settings iframe)
    var topBar = document.createElement('div');
    topBar.style.cssText = [
      'display:flex', 'align-items:center', 'justify-content:space-between',
      'padding:16px 24px',
      'background:rgba(22,27,34,0.95)',
      'border-bottom:1px solid #21262d',
      'flex-shrink:0'
    ].join(';');

    var title = document.createElement('div');
    title.style.cssText = 'font-size:18px;font-weight:500;color:#f0f6fc;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif';
    title.textContent = 'Settings';
    topBar.appendChild(title);

    var btnGroup = document.createElement('div');
    btnGroup.style.cssText = 'display:flex;gap:12px;align-items:center';

    // Re-calibrate button (only show if a phone is connected)
    if (phoneConnected) {
      var recalBtn = document.createElement('button');
      recalBtn.textContent = 'Re-calibrate Apps';
      recalBtn.style.cssText = [
        'padding:10px 20px', 'border-radius:10px',
        'background:rgba(88,166,255,0.12)',
        'border:1px solid rgba(88,166,255,0.3)',
        'color:#58a6ff', 'font-family:inherit',
        'font-size:14px', 'font-weight:500',
        'cursor:pointer', 'transition:all 200ms'
      ].join(';');
      recalBtn.addEventListener('click', homehubRecalibrate);
      btnGroup.appendChild(recalBtn);

      // Forget phone button — clears name and calibration
      var forgetBtn = document.createElement('button');
      forgetBtn.textContent = 'Forget Phone';
      forgetBtn.style.cssText = [
        'padding:10px 20px', 'border-radius:10px',
        'background:rgba(255,107,107,0.1)',
        'border:1px solid rgba(255,107,107,0.25)',
        'color:#ff6b6b', 'font-family:inherit',
        'font-size:14px', 'font-weight:500',
        'cursor:pointer', 'transition:all 200ms'
      ].join(';');
      forgetBtn.addEventListener('click', function() {
        if (masterDeviceId) {
          delete phoneNames[masterDeviceId];
          delete appPositions[masterDeviceId];
          savePhoneNames();
          saveAppPositions();
        }
        homehubCloseSettings();
        showHomeView();
      });
      btnGroup.appendChild(forgetBtn);
    }

    // Close button
    var closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText = [
      'padding:10px 20px', 'border-radius:10px',
      'background:rgba(255,255,255,0.06)',
      'border:1px solid rgba(255,255,255,0.1)',
      'color:#8b949e', 'font-family:inherit',
      'font-size:14px', 'font-weight:500',
      'cursor:pointer', 'transition:all 200ms'
    ].join(';');
    closeBtn.addEventListener('click', homehubCloseSettings);
    btnGroup.appendChild(closeBtn);

    // Calibrate Notifications button — always visible (works whenever AA is showing)
    var notifBtn = document.createElement('button');
    notifBtn.textContent = 'Calibrate Notifications';
    notifBtn.style.cssText = [
      'padding:10px 20px', 'border-radius:10px',
      'background:rgba(63,185,80,0.1)',
      'border:1px solid rgba(63,185,80,0.25)',
      'color:#3fb950', 'font-family:inherit',
      'font-size:14px', 'font-weight:500',
      'cursor:pointer', 'transition:all 200ms'
    ].join(';');
    notifBtn.addEventListener('click', function() {
      homehubCloseSettings();
      startNotifsCalibration();
    });
    btnGroup.appendChild(notifBtn);

    topBar.appendChild(btnGroup);
    settingsOverlayEl.appendChild(topBar);

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
  window.sendCmd = sendCmd;

  // --- Start ---
  function start() {
    loadPhoneNames();
    loadAppPositions();
    createHub();
    createScreensaver();
    createLandingPage();
    createRingBanner();
    createHealthDot();
    updateClock();
    fetchWeather();
    setupDeviceDetection();
    setupAaCallListener();
    refreshPhotos();

    // Clock: update every 10s (seconds not shown)
    clockTimer = setInterval(updateClock, 10000);

    // Weather: refresh every 10 min
    setInterval(fetchWeather, 600000);

    // Photos: rotate every 15s, re-scan the folder every 10 min
    setInterval(showNextPhoto, 15000);
    setInterval(refreshPhotos, 600000);

    // Ring status: poll every 2s
    pollTimer = setInterval(pollStatus, 2000);
    pollStatus();

    // Now playing: poll every 3s as fallback (media events handle real-time updates)
    setInterval(pollNowPlaying, 3000);

    console.log('[HomeHub v2] Master Phone Layout started');
  }

  // Wait for React to mount, then start
  setTimeout(start, 1500);
})();
"""

# Append the overlay script to the renderer JS
renderer_js += OVERLAY_SCRIPT
print(f"Appended overlay script: {len(OVERLAY_SCRIPT)} chars")

# --- Patch main.js: AA PhoneStatus call detection ---
# The AA protocol sends PhoneStatus messages with a calls array that includes
# call state (INCOMING=4, IN_CALL=1, etc.) and caller ID. LIVI's compiled
# code only extracts signalStrength and ignores calls. We patch it to also
# detect incoming calls and emit AudioAttentionRinging (same as CarPlay does),
# so the renderer and our overlay can show a call notification.
main_path = 'out/main/main.js'
main_js = None
for path, offset, size in files:
    if path == main_path:
        with open(asar_path, 'rb') as f:
            f.seek(data_offset + offset)
            main_js = f.read(size).decode('utf-8')
        print(f"Read {main_path}: {len(main_js)} chars")
        break

if main_js:
    # message and extracts signalStrength. We need to insert call detection
    # code between the decode and the signalStrength check.
    #
    # The handler looks like:
    #   let e=sl(this._proto.PhoneStatus,r),t=typeof e.signalStrength==`number`?e.signalStrength:void 0;if(t!==void 0){
    #
    # If we've already patched it (previous deployment), the string between
    # the decode and `if(t!==void 0){` contains our _hhR/_hhC code.
    # We use a regex to match both cases and replace with the new patch.
    #
    # The regex matches from the PhoneStatus decode up to (and including) `if(t!==void 0){`
    # This is idempotent — it works whether or not a previous patch is present.
    phonestatus_pattern = re.compile(
        r"let e=sl\(this\._proto\.PhoneStatus,r\),t=typeof e\.signalStrength==`number`\?e\.signalStrength:void 0;"
        r".*?"
        r"if\(t!==void 0\)\{",
        re.DOTALL
    )

    # The patch: after decoding PhoneStatus, check the calls array for call states.
    # AA PhoneStatus.Call.State: UNKNOWN=0, IN_CALL=1, ON_HOLD=2, INACTIVE=3,
    # INCOMING=4, CONFERENCED=5, MUTED=6
    #
    # Call lifecycle (incoming):
    #   INCOMING (4) → emit AudioAttentionRinging (14), set _hhR=true
    #   IN_CALL (1) when _hhR → call answered → emit AudioPhonecallStart (4),
    #     clear _hhR, set _hhC=true
    #   No calls when _hhR or _hhC → call ended → emit AudioPhonecallStop (5),
    #     clear both flags
    #
    # Outgoing calls (IN_CALL without prior INCOMING) are not reported to the
    # overlay — the phone's own UI handles those. We only detect incoming calls.
    #
    # Uses block scope { } to avoid leaking temp variables. Uses _hh prefix to avoid collisions.
    # So=AudioData class, Vo=MessageHeader class, q.AudioData=MessageType, all module-level.
    new_phonestatus = (
        "let e=sl(this._proto.PhoneStatus,r),t=typeof e.signalStrength==`number`?e.signalStrength:void 0;"
        "{let _ca=e.calls,_ri=false,_ic=false;if(_ca&&_ca.length>0){for(let _i=0;_i<_ca.length;_i++){let _s=_ca[_i].phone_state;if(_s===4){_ri=true;let _cl=_ca[_i].caller_id||_ca[_i].caller_number||``;if(!this._hhR){this._hhR=true;let _b=Buffer.allocUnsafeSlow(13);_b.writeUInt32LE(5,0);_b.writeFloatLE(0,4);_b.writeUInt32LE(2,8);_b.writeUInt8(14,12);this.emit(`message`,new So(new Vo(_b.length,q.AudioData),_b));this.emit(`device-status`,{callState:`ringing`,caller:_cl})}}else if(_s===1||_s===5){_ic=true}break}}"
        "if(_ic&&this._hhR){this._hhR=false;this._hhC=true;let _b=Buffer.allocUnsafeSlow(13);_b.writeUInt32LE(5,0);_b.writeFloatLE(0,4);_b.writeUInt32LE(2,8);_b.writeUInt8(4,12);this.emit(`message`,new So(new Vo(_b.length,q.AudioData),_b));this.emit(`device-status`,{callState:`active`})}"
        "if(!_ri&&!_ic&&(this._hhR||this._hhC)){this._hhR=false;this._hhC=false;let _b=Buffer.allocUnsafeSlow(13);_b.writeUInt32LE(5,0);_b.writeFloatLE(0,4);_b.writeUInt32LE(2,8);_b.writeUInt8(5,12);this.emit(`message`,new So(new Vo(_b.length,q.AudioData),_b));this.emit(`device-status`,{callState:`idle`})}}"
        "if(t!==void 0){"
    )

    match = phonestatus_pattern.search(main_js)
    if match:
        old_text = match.group(0)
        main_js = main_js[:match.start()] + new_phonestatus + main_js[match.end():]
        print(f"Patched PhoneStatus handler: call detection added (replaced {len(old_text)} chars)")
    else:
        print(f"WARNING: Could not find PhoneStatus handler in main.js — call patch skipped")

    # --- Patch onAaPresence to forward callState/caller to the renderer ---
    # The PhoneStatus handler emits device-status events with {callState, caller},
    # which reach onAaPresence via the device-presence event chain. But the
    # compiled onAaPresence only extracts battery/signal and ignores callState.
    # We patch it to also emit a projection-event with type 'call' so the
    # overlay can display the actual caller ID.
    #
    # Idempotent: uses regex to match whether or not the patch is already present.
    aapresence_pattern = re.compile(
        r"(signalStrength:typeof t\.signalStrength==`number`\?t\.signalStrength:void 0\}\);)"
        r"(?:if\(t\.callState\)\{this\.emitProjectionEvent\(\{type:`call`,payload:\{callState:t\.callState,caller:t\.caller\|\|``\}\}\)\})?"
        r"(return\})"
    )
    aapresence_replacement = (
        r"\1"
        "if(t.callState){this.emitProjectionEvent({type:`call`,payload:{callState:t.callState,caller:t.caller||``}})}"
        r"\2"
    )

    aamatch = aapresence_pattern.search(main_js)
    if aamatch:
        main_js = aapresence_pattern.sub(aapresence_replacement, main_js, count=1)
        print(f"Patched onAaPresence: callState/caller forwarding added")
    else:
        print(f"WARNING: Could not find onAaPresence handler — caller ID patch skipped")

# --- Rebuild the ASAR ---
all_files_sorted = sorted(files, key=lambda x: x[1])
new_data = bytearray()
offset_map = {}

for path, old_offset, old_size in all_files_sorted:
    if path == renderer_path:
        content = renderer_js.encode('utf-8')
    elif path == main_path and main_js is not None:
        content = main_js.encode('utf-8')
        print(f"Using patched main.js: {len(content)} bytes")
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

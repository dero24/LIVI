#!/bin/bash
# Setup script for the LIVI home phone hub on Raspberry Pi.
# Run on the Raspberry Pi as the normal user (raspberry).
# It will ask for the sudo password when writing udev rules / lightdm config.
set -e

USER="${USER:-raspberry}"
HOME_DIR="${HOME:-/home/$USER}"
LIVI_DIR="$HOME_DIR/LIVI"
CONFIG_DIR="$HOME_DIR/.config"
SERVICE_DIR="$CONFIG_DIR/systemd/user"
LABWC_DIR="$CONFIG_DIR/labwc"
KANSHI_DIR="$CONFIG_DIR/kanshi"

mkdir -p "$SERVICE_DIR" "$LABWC_DIR" "$KANSHI_DIR" "$LIVI_DIR" "$CONFIG_DIR/LIVI"
# Support either a pre-placed LIVI.AppImage or an extracted AppDir.
[ -f "$LIVI_DIR/LIVI.AppImage" ] && chmod +x "$LIVI_DIR/LIVI.AppImage" || true
[ -f "$LIVI_DIR/extracted/AppRun" ] && chmod +x "$LIVI_DIR/extracted/AppRun" || true

# --- 1. labwc configuration: touch mouse emulation + calibration matrix ---
cat > "$LABWC_DIR/rc.xml" <<'EOF'
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <touch deviceName="" mapToOutput="" mouseEmulation="yes"/>
  <libinput>
    <device category="touch">
      <calibrationMatrix>0 -1 1 1 0 0</calibrationMatrix>
    </device>
  </libinput>
</openbox_config>
EOF

# --- 2. kanshi profile for persistent portrait output ---
# Use --custom because this HDMI panel does not advertise a 1024x600 EDID mode.
cat > "$KANSHI_DIR/config" <<'EOF'
profile {
  output HDMI-A-1 mode --custom 1024x600@60Hz transform 90
}
EOF

# --- 3. labwc autostart: kanshi + wlr-randr fallback + LIVI ---
cat > "$LABWC_DIR/autostart" <<'EOF'
#!/bin/bash
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000
export DISPLAY=:0

# Restart kanshi with our portrait profile
pkill kanshi 2>/dev/null || true
sleep 1
kanshi &

# Fallback: force the first connected output to 1024x600 portrait
(
  sleep 2
  for out in HDMI-A-1 HDMI-A-2 DSI-1 DP-1 DP-2; do
    if wlr-randr --output "$out" --custom-mode 1024x600@60Hz --transform 90 >/dev/null 2>&1; then
      logger -t livi-autostart "set $out to 1024x600 portrait"
      break
    fi
  done
) &

# Wait for the portrait 1024x600 output to be current before starting LIVI
(
  for i in $(seq 1 20); do
    if wlr-randr | grep -qE '1024x600.*current' && wlr-randr | grep -q 'Transform: 90'; then
      logger -t livi-autostart 'output is 1024x600 portrait, starting LIVI'
      systemctl --user start livi.service
      break
    fi
    sleep 1
  done
) &

# Log CPU temperature every 30s so we can spot thermal throttling
( while true; do
    temp=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 | cut -d"'" -f1)
    logger -t pi-thermal "CPU: ${temp:-unknown}C"
    sleep 30
done ) &
EOF
chmod +x "$LABWC_DIR/autostart"

# --- 4. systemd user service for LIVI ---
cat > "$SERVICE_DIR/livi.service" <<EOF
[Unit]
Description=LIVI home phone hub
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DISPLAY=:0
Environment=ELECTRON_OZONE_PLATFORM_HINT=wayland
Environment=XDG_SESSION_TYPE=wayland
Environment=LIVI_KIOSK=1
WorkingDirectory=$LIVI_DIR
ExecStart=$LIVI_DIR/extracted/AppRun
ExecStop=/bin/sh -c 'pkill -x livi 2>/dev/null || true; pkill -x livi-compositor 2>/dev/null || true; exit 0'

[Install]
WantedBy=graphical-session.target
EOF

# --- 5. Health watchdog ---
HEALTH_SCRIPT="$LIVI_DIR/livi-health.sh"
cat > "$HEALTH_SCRIPT" <<'EOF'
#!/bin/bash
if ! pgrep -x livi >/dev/null && ! pgrep -f "LIVI.AppImage" >/dev/null; then
    logger -t livi-health "livi process missing, restarting"
    systemctl --user restart livi.service
    exit 0
fi

STATUS="$HOME/.config/LIVI/statusData.json"
if [ -f "$STATUS" ]; then
    mtime=$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)
    now=$(date +%s)
    if [ $((now - mtime)) -gt 300 ]; then
        export STATUS
        isConnected=false
        if command -v python3 >/dev/null; then
            isConnected=$(python3 - <<'PY' 2>/dev/null
import json, os
status_path = os.environ.get('STATUS', '')
if not status_path:
    print('false')
else:
    try:
        with open(status_path) as f:
            d = json.load(f)
        payload = d.get('payload', d)
        usb = payload.get('usb', {})
        projection = payload.get('projection', {})
        print('true' if (usb.get('phoneConnected') or projection.get('active')) else 'false')
    except Exception:
        print('false')
PY
)
        fi
        if [ "$isConnected" = "true" ]; then
            logger -t livi-health "status stale while connected, restarting livi"
            systemctl --user restart livi.service
        fi
    fi
fi
EOF
chmod +x "$HEALTH_SCRIPT"

cat > "$SERVICE_DIR/livi-health.service" <<EOF
[Unit]
Description=LIVI health watchdog

[Service]
Type=oneshot
ExecStart=$HEALTH_SCRIPT
EOF

cat > "$SERVICE_DIR/livi-health.timer" <<EOF
[Unit]
Description=Run LIVI health check every 10 seconds

[Timer]
# Give labwc + kanshi time to set the portrait output before the first health check.
OnBootSec=40s
OnUnitActiveSec=10s
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF

# --- 6. cdc_acm unbind udev rule ---
# This unbinds the kernel cdc_acm driver from the ACM interface after it binds,
# so LIVI can claim the phone's data interface instead.
sudo tee /etc/udev/rules.d/99-livi-cdc-acm.rules >/dev/null <<'EOF'
# Samsung
ACTION=="add|bind", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_interface", DRIVER=="cdc_acm", ATTRS{idVendor}=="04e8", RUN+="/bin/sh -c 'echo %k > /sys/bus/usb/drivers/cdc_acm/unbind'"
# Google Pixel / Android accessory mode
ACTION=="add|bind", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_interface", DRIVER=="cdc_acm", ATTRS{idVendor}=="18d1", RUN+="/bin/sh -c 'echo %k > /sys/bus/usb/drivers/cdc_acm/unbind'"
EOF

# --- 6a. Upstream LIVI udev rule + touch filter ---
# LIVI's USBService on Linux only probes vendors in this allowlist and needs
# these OWNER / UDISKS_IGNORE / MTP rules so the desktop does not grab phones.
# Try the AppImage first, but fall back to a pre-extracted AppDir if extraction fails.
UDEV_TEMPLATE=""
TOUCH_FILTER_TEMPLATE=""
EXTRACT_DIR=""
if [ -f "$LIVI_DIR/LIVI.AppImage" ]; then
  EXTRACT_DIR=$(mktemp -d)
  ( cd "$EXTRACT_DIR" && "$LIVI_DIR/LIVI.AppImage" --appimage-extract "resources/99-LIVI.rules.template" >/dev/null 2>&1 ) || true
  ( cd "$EXTRACT_DIR" && "$LIVI_DIR/LIVI.AppImage" --appimage-extract "resources/livi-touch-filter" >/dev/null 2>&1 ) || true
  UDEV_TEMPLATE="$EXTRACT_DIR/squashfs-root/resources/99-LIVI.rules.template"
  TOUCH_FILTER_TEMPLATE="$EXTRACT_DIR/squashfs-root/resources/livi-touch-filter"
fi

if { [ -z "$UDEV_TEMPLATE" ] || [ ! -f "$UDEV_TEMPLATE" ]; } && [ -d "$LIVI_DIR/extracted/resources" ]; then
  [ -n "$EXTRACT_DIR" ] && rm -rf "$EXTRACT_DIR" || true
  UDEV_TEMPLATE="$LIVI_DIR/extracted/resources/99-LIVI.rules.template"
  TOUCH_FILTER_TEMPLATE="$LIVI_DIR/extracted/resources/livi-touch-filter"
fi

if [ -n "$UDEV_TEMPLATE" ] && [ -f "$UDEV_TEMPLATE" ]; then
  sed "s/__USERNAME__/$USER/g" "$UDEV_TEMPLATE" | sudo tee /etc/udev/rules.d/99-LIVI.rules >/dev/null
  echo "Installed /etc/udev/rules.d/99-LIVI.rules"
else
  echo "Warning: could not find 99-LIVI.rules.template" >&2
fi

if [ -n "$TOUCH_FILTER_TEMPLATE" ] && [ -f "$TOUCH_FILTER_TEMPLATE" ]; then
  sudo mkdir -p /usr/local/lib/livi
  sudo install -m 0755 -o root -g root "$TOUCH_FILTER_TEMPLATE" /usr/local/lib/livi/livi-touch-filter
  echo "Installed /usr/local/lib/livi/livi-touch-filter"
else
  echo "Warning: could not find livi-touch-filter" >&2
fi
[ -n "$EXTRACT_DIR" ] && rm -rf "$EXTRACT_DIR" || true

# --- 7. Touchscreen udev calibration ---
sudo tee /etc/udev/rules.d/99-livi-touch.rules >/dev/null <<'EOF'
# WCH/QinHeng USB2IIC_CTP_CONTROL touch controller (1a86:e5e3)
# Same 90-degree clockwise matrix used in labwc rc.xml as a hot-plug fallback.
ACTION=="add|change", SUBSYSTEM=="input", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="e5e3", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 -1 1 1 0 0"
EOF

# --- 8. LIVI config for portrait ---
LIVI_CONFIG="$CONFIG_DIR/LIVI/config.json"
python3 - <<PY
import json, os
p = '$LIVI_CONFIG'
d = {}
if os.path.exists(p):
    try:
        with open(p) as f:
            d = json.load(f)
    except Exception:
        pass
# 600x1024 portrait screen; 720x1280 is the nearest Android Auto/CarPlay tier.
d['mainScreenWidth'] = 600
d['mainScreenHeight'] = 1024
d['mainScreenBounds'] = {'x': 0, 'y': 0, 'width': 600, 'height': 1024}
# Make LIVI/compositor set the host HDMI mode to 1024x600 (rotated to 600x1024 logically).
d['displayMode'] = '1024x600'
d['projectionWidth'] = 720
d['projectionHeight'] = 1280
d['projectionDpi'] = d.get('projectionDpi', 180)
# Start on the custom home hub instead of jumping straight to projection.
d['startPage'] = 'home'
# Make LIVI fill the portrait display.
d.setdefault('kiosk', {})
d['kiosk']['main'] = True
d['kiosk'].setdefault('dash', False)
d['kiosk'].setdefault('aux', False)
with open(p, 'w') as f:
    json.dump(d, f, indent=2)
PY

# --- 9. LightDM autologin into labwc ---
if [ -f /etc/lightdm/lightdm.conf ]; then
  sudo sed -i 's/^#\?user-session=.*/user-session=rpd-labwc/' /etc/lightdm/lightdm.conf
  sudo sed -i 's/^#\?autologin-session=.*/autologin-session=rpd-labwc/' /etc/lightdm/lightdm.conf
  sudo sed -i 's/^#\?autologin-user=.*/autologin-user=raspberry/' /etc/lightdm/lightdm.conf
  sudo sed -i 's/^#\?autologin-user-timeout=.*/autologin-user-timeout=0/' /etc/lightdm/lightdm.conf
  if ! grep -q '^user-session=' /etc/lightdm/lightdm.conf; then
    sudo sed -i '/^\[Seat:\*\]$/a user-session=rpd-labwc' /etc/lightdm/lightdm.conf
  fi
  if ! grep -q '^autologin-session=' /etc/lightdm/lightdm.conf; then
    sudo sed -i '/^\[Seat:\*\]$/a autologin-session=rpd-labwc' /etc/lightdm/lightdm.conf
  fi
  if ! grep -q '^autologin-user=' /etc/lightdm/lightdm.conf; then
    sudo sed -i '/^\[Seat:\*\]$/a autologin-user=raspberry' /etc/lightdm/lightdm.conf
  fi
  if ! grep -q '^autologin-user-timeout=' /etc/lightdm/lightdm.conf; then
    sudo sed -i '/^\[Seat:\*\]$/a autologin-user-timeout=0' /etc/lightdm/lightdm.conf
  fi
fi

# --- 10. Apply and enable ---
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input --attr-match=idVendor=1a86 2>/dev/null || true
sudo udevadm trigger --subsystem-match=usb 2>/dev/null || true

systemctl --user daemon-reload
systemctl --user enable livi.service livi-health.timer
systemctl --user start livi-health.timer

echo "Setup applied. Reboot to start the LIVI home hub."

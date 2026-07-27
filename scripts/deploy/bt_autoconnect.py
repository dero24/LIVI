#!/usr/bin/env python3
"""
Bluetooth Auto-Connect — automatically connects to trusted/paired phones.

Watches BlueZ for paired devices that are disconnected and tries to connect
to them. This means once a phone is paired, the Pi will auto-connect to it
whenever it's in range — no manual "connect" needed on the touchscreen or phone.

Runs as a systemd user service.
"""
import subprocess
import time
import re
import sys

POLL_INTERVAL = 5  # check every 5 seconds
CONNECT_TIMEOUT = 10  # give up on a connect attempt after 10s

def log(*args):
    print(f'[bt-autoconnect] {", ".join(str(a) for a in args)}', flush=True)

def get_paired_devices():
    """Get list of paired Bluetooth devices from bluetoothctl.
    Only returns devices that are phones (Icon: phone in bluetoothctl info)."""
    try:
        r = subprocess.run(
            ['bluetoothctl', 'devices'],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in r.stdout.strip().split('\n'):
            # Format: "Device AA:BB:CC:DD:EE:FF Device Name"
            m = re.match(r'Device\s+([0-9A-Fa-f:]{17})\s+(.*)', line.strip())
            if m:
                mac = m.group(1)
                name = m.group(2)
                # Only auto-connect to phones (not headsets, speakers, etc.)
                info = get_device_info(mac)
                if 'Icon: phone' in info:
                    devices.append((mac, name))
                else:
                    icon = re.search(r'Icon:\s*(\S+)', info)
                    icon_name = icon.group(1) if icon else 'unknown'
                    log(f'Skipping non-phone device: {mac} ({name}, icon={icon_name})')
        return devices
    except Exception as e:
        log(f'get_paired_devices error: {e}')
        return []

def get_device_info(mac):
    """Get bluetoothctl info output for a device."""
    try:
        r = subprocess.run(
            ['bluetoothctl', 'info', mac],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout
    except Exception:
        return ''

def is_connected(mac):
    """Check if a Bluetooth device is currently connected."""
    try:
        r = subprocess.run(
            ['bluetoothctl', 'info', mac],
            capture_output=True, text=True, timeout=5
        )
        return 'Connected: yes' in r.stdout
    except Exception:
        return False

def is_trusted(mac):
    """Check if a Bluetooth device is trusted."""
    try:
        r = subprocess.run(
            ['bluetoothctl', 'info', mac],
            capture_output=True, text=True, timeout=5
        )
        return 'Trusted: yes' in r.stdout
    except Exception:
        return False

def trust_device(mac):
    """Trust a paired device so it auto-reconnects."""
    try:
        subprocess.run(
            ['bluetoothctl', 'trust', mac],
            capture_output=True, text=True, timeout=5
        )
        log(f'Trusted: {mac}')
    except Exception as e:
        log(f'Trust error for {mac}: {e}')

def connect_device(mac):
    """Try to connect to a Bluetooth device."""
    try:
        log(f'Connecting to {mac}...')
        r = subprocess.run(
            ['bluetoothctl', 'connect', mac],
            capture_output=True, text=True, timeout=CONNECT_TIMEOUT
        )
        if 'Connection successful' in r.stdout:
            log(f'Connected: {mac}')
            return True
        else:
            log(f'Connect failed for {mac}: {r.stdout.strip()[:100]}')
            return False
    except subprocess.TimeoutExpired:
        log(f'Connect timeout for {mac}')
        return False
    except Exception as e:
        log(f'Connect error for {mac}: {e}')
        return False

def main():
    log('Bluetooth Auto-Connect started')

    # Track which devices we've recently tried to connect to
    # (to avoid spamming connect attempts every 5 seconds)
    recent_attempts = {}  # mac -> timestamp
    RETRY_COOLDOWN = 30  # wait 30s between retry attempts for the same device

    while True:
        try:
            devices = get_paired_devices()
            for mac, name in devices:
                # Skip if already connected
                if is_connected(mac):
                    continue

                # Trust the device if not already trusted
                if not is_trusted(mac):
                    trust_device(mac)

                # Check cooldown
                now = time.time()
                last_attempt = recent_attempts.get(mac, 0)
                if now - last_attempt < RETRY_COOLDOWN:
                    continue

                # Try to connect
                recent_attempts[mac] = now
                connect_device(mac)

        except Exception as e:
            log(f'Main loop error: {e}')

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log('Stopping')
        sys.exit(0)

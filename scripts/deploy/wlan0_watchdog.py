#!/usr/bin/env python3
"""
wlan0 watchdog — monitors wlan0 connectivity and bounces the interface
when it goes unreachable. The brcmfmac firmware on Pi 5 has a known issue
where bgscan signal-strength monitoring fails and the link silently dies
while the Pi stays alive (touchscreen works, but SSH/HTTP unreachable).

Strategy:
  - Every 15s, ping the default gateway via wlan0.
  - If 3 consecutive pings fail (45s), bounce wlan0:
      nmcli device disconnect wlan0  (or ip link set down)
      nmcli device connect wlan0     (or ip link set up)
  - Also re-apply power_save off after the bounce.
  - Log all actions to /home/raspberry/wlan0_watchdog.log

Runs as a systemd user service.
"""
import subprocess, time, os, sys

LOG_FILE = '/home/raspberry/wlan0_watchdog.log'
CHECK_INTERVAL = 15      # seconds between checks
MAX_FAILURES = 3         # consecutive failures before bouncing
GATEWAY = None           # auto-detected

def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except:
        pass

def get_gateway():
    """Get the default gateway for wlan0."""
    try:
        r = subprocess.run(['ip', 'route', 'show', 'dev', 'wlan0'],
                       capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            if 'default' in line:
                parts = line.split()
                # "default via 192.168.1.1 ..." or "default via fe80::..."
                if 'via' in parts:
                    idx = parts.index('via')
                    return parts[idx + 1]
    except:
        pass
    return None

def ping_ok():
    """Ping the gateway via wlan0. Returns True if reachable."""
    global GATEWAY
    if not GATEWAY:
        GATEWAY = get_gateway()
    if not GATEWAY:
        log('No gateway found, cannot check')
        return True  # Don't bounce if we can't even find the gateway
    try:
        r = subprocess.run(
            ['ping', '-I', 'wlan0', '-c', '1', '-W', '5', GATEWAY],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except:
        return False

def apply_power_save_off():
    """Re-apply power_save off to wlan0."""
    try:
        subprocess.run(['/usr/sbin/iw', 'dev', 'wlan0', 'set', 'power_save', 'off'],
                      capture_output=True, timeout=5)
    except:
        pass

def bounce_wlan0():
    """Bounce the wlan0 interface to recover connectivity."""
    log('Bouncing wlan0...')
    # Method 1: nmcli (preferred, handles DHCP reconnection)
    try:
        r = subprocess.run(['nmcli', 'device', 'disconnect', 'wlan0'],
                          capture_output=True, text=True, timeout=10)
        log(f'  disconnect: rc={r.returncode} {r.stderr.strip()}')
    except Exception as e:
        log(f'  disconnect failed: {e}')
        # Method 2: ip link
        subprocess.run(['sudo', '-n', 'ip', 'link', 'set', 'wlan0', 'down'],
                      capture_output=True, timeout=5)

    time.sleep(3)

    try:
        r = subprocess.run(['nmcli', 'device', 'connect', 'wlan0'],
                          capture_output=True, text=True, timeout=30)
        log(f'  connect: rc={r.returncode} {r.stderr.strip()}')
    except Exception as e:
        log(f'  connect failed: {e}')
        subprocess.run(['sudo', '-n', 'ip', 'link', 'set', 'wlan0', 'up'],
                      capture_output=True, timeout=5)

    time.sleep(5)
    apply_power_save_off()

    # Re-detect gateway after bounce
    global GATEWAY
    GATEWAY = get_gateway()
    log(f'  Gateway after bounce: {GATEWAY}')

def main():
    log(f'wlan0 watchdog starting (check every {CHECK_INTERVAL}s, bounce after {MAX_FAILURES} failures)')
    GATEWAY = get_gateway()  # noqa: F841 — reassigns global
    log(f'Initial gateway: {GATEWAY}')

    failures = 0
    while True:
        if ping_ok():
            if failures > 0:
                log(f'Link recovered after {failures} failures')
            failures = 0
        else:
            failures += 1
            log(f'Ping failed ({failures}/{MAX_FAILURES})')
            if failures >= MAX_FAILURES:
                log(f'Max failures reached, bouncing wlan0')
                bounce_wlan0()
                failures = 0
                # Wait extra after bounce for DHCP to settle
                time.sleep(10)

        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Deploy sidecar + overlay patch with BT and settings UI fixes."""
import subprocess, sys, os, time

# 1. Deploy sidecar
print('=== Deploying sidecar ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'put', 'homephone-sidecar.py', '/home/raspberry/homephone-sidecar.py'],
                   capture_output=True, text=True, timeout=30)
print(r.stdout)
if r.returncode != 0:
    print(f'FAIL: {r.stderr}')
    sys.exit(1)

# 2. Deploy overlay patch script
print('=== Deploying overlay patch ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'put', 'patch_homehub_v2.py', '/home/raspberry/patch_homehub_v2.py'],
                   capture_output=True, text=True, timeout=30)
print(r.stdout)
if r.returncode != 0:
    print(f'FAIL: {r.stderr}')
    sys.exit(1)

# 3. Restart sidecar
print('=== Restarting sidecar ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'systemctl --user restart homephone-sidecar.service && sleep 2 && systemctl --user is-active homephone-sidecar.service',
    '-t', '15'], capture_output=True, text=True, timeout=20)
print(r.stdout)

# 4. Run the overlay patch
print('=== Running overlay patch ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'python3 /home/raspberry/patch_homehub_v2.py', '-t', '30'],
    capture_output=True, text=True, timeout=35)
print(r.stdout[-500:])
if r.returncode != 0:
    print(f'  stderr: {r.stderr[-300:]}')

# 5. Restart LIVI to pick up the patched overlay
print('=== Restarting LIVI ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'systemctl --user restart livi.service && sleep 10 && systemctl --user is-active livi.service',
    '-t', '20'], capture_output=True, text=True, timeout=25)
print(r.stdout)

# 6. Verify sidecar settings page has the new BT info card
print('=== Verifying settings page ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'curl -s http://localhost:8123/settings | grep -c "Wireless Android Auto"',
    '-t', '10'], capture_output=True, text=True, timeout=15)
print(f'  Wireless AA info card: {"PASS" if r.stdout.strip() == "1" else "FAIL"} (found {r.stdout.strip()})')

r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'curl -s http://localhost:8123/settings | grep -c "Paired Audio Devices"',
    '-t', '10'], capture_output=True, text=True, timeout=15)
print(f'  Paired Audio Devices: {"PASS" if r.stdout.strip() == "1" else "FAIL"} (found {r.stdout.strip()})')

r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'curl -s http://localhost:8123/settings | grep -c "in-iframe"',
    '-t', '10'], capture_output=True, text=True, timeout=15)
print(f'  iframe detection CSS: {"PASS" if r.stdout.strip() == "1" else "FAIL"} (found {r.stdout.strip()})')

# 7. Verify BT API filters phones
print('=== Verifying BT API ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'curl -s http://localhost:8123/api/bluetooth/devices | python3 -c "import sys,json; d=json.load(sys.stdin); print([(x[\"name\"],x.get(\"is_phone\"),x.get(\"icon\")) for x in d[\"devices\"]])"',
    '-t', '10'], capture_output=True, text=True, timeout=15)
print(f'  Devices: {r.stdout.strip()}')

# 8. Check hostapd is still running (wireless AA AP)
print('=== Wireless AA AP ===')
r = subprocess.run([sys.executable, 'pi_ctl.py', 'run',
    'pgrep -a hostapd; echo ---; systemctl --user is-active livi.service; systemctl --user is-active homephone-sidecar.service',
    '-t', '10'], capture_output=True, text=True, timeout=15)
print(r.stdout)

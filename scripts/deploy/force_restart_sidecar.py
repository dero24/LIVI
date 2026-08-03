#!/usr/bin/env python3
"""Force restart sidecar and verify."""
import subprocess, time, os, signal

# Find and kill any existing sidecar processes
result = subprocess.run(['pgrep', '-f', 'homephone-sidecar'], capture_output=True, text=True)
for pid in result.stdout.strip().split('\n'):
    if pid:
        try:
            os.kill(int(pid), signal.SIGKILL)
            print(f'Killed sidecar PID {pid}')
        except:
            pass

time.sleep(2)

# Reset and start
subprocess.run(['systemctl', '--user', 'reset-failed', 'homephone-sidecar.service'], capture_output=True)
subprocess.run(['systemctl', '--user', 'start', 'homephone-sidecar.service'], capture_output=True)
time.sleep(3)

# Check status
r = subprocess.run(['systemctl', '--user', 'is-active', 'homephone-sidecar.service'], capture_output=True, text=True)
print(f'Sidecar: {r.stdout.strip()}')

r = subprocess.run(['systemctl', '--user', 'is-active', 'livi.service'], capture_output=True, text=True)
print(f'LIVI: {r.stdout.strip()}')

#!/usr/bin/env python3
from pyudev import Context, Monitor, MonitorObserver

def print_event(action, device):
    if device.subsystem == 'usb':
        vid = device.get('ID_VENDOR_ID', '?')
        pid = device.get('ID_MODEL_ID', '?')
        print(f'udev {action} {vid}:{pid} {device.device_path}')

ctx = Context()
mon = Monitor.from_netlink(ctx)
mon.filter_by('usb')
observer = MonitorObserver(mon, print_event, name='udev-mon')
observer.start()
print('monitoring udev for 10s...')
import time
time.sleep(10)
observer.stop()
print('done')

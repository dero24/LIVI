#!/usr/bin/env python3
"""
HFP Call Monitor — watches oFono VoiceCallManager for incoming calls
and notifies the homephone-sidecar via HTTP POST to /ring.

When a call comes in:
  - oFono emits org.ofono.VoiceCallManager.CallAdded(path, properties)
  - properties includes: State, LineIdentification (caller ID), Name, etc.
  - State "incoming" = ringing, "active" = answered, "disconnected" = ended

We POST to the sidecar:
  /ring?slot=1&caller=<name_or_number>&phone=<number>  (on incoming)
  /ring?slot=1&clear=1                                  (on disconnect)

Runs as a systemd user service.
"""
import dbus
import dbus.mainloop.glib
import urllib.request
import urllib.parse
import threading
import json
import time
import sys
from gi.repository import GLib

SIDECAR_URL = 'http://127.0.0.1:8123'
POLL_INTERVAL = 2  # fallback poll every 2s in case signals are missed

def log(*args):
    print(f'[hfp-monitor] {", ".join(str(a) for a in args)}', flush=True)

def post_to_sidecar(path, params):
    """POST to the sidecar without blocking."""
    def _post():
        try:
            url = SIDECAR_URL + path + '?' + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, method='POST')
            urllib.request.urlopen(req, timeout=3)
            log(f'POST {path} {params} -> OK')
        except Exception as e:
            log(f'POST {path} {params} -> {e}')
    threading.Thread(target=_post, daemon=True).start()

def format_caller(props):
    """Extract a readable caller string from oFono call properties."""
    name = props.get('Name', '')
    line_id = props.get('LineIdentification', '')
    if name and line_id:
        return f'{name} ({line_id})'
    if name:
        return name
    if line_id:
        return line_id
    return 'Unknown Caller'

class HfpCallMonitor:
    def __init__(self, bus):
        self.bus = bus
        self.modem_path = None
        self.active_calls = {}  # call_path -> {state, caller, ...}

    def find_modem(self):
        """Find the HFP modem if one exists."""
        try:
            manager = dbus.Interface(
                self.bus.get_object('org.ofono', '/'),
                'org.ofono.Manager'
            )
            modems = manager.GetModems()
            for path, props in modems:
                if props.get('Type') == 'hfp':
                    return path
            return None
        except Exception as e:
            log(f'find_modem error: {e}')
            return None

    def get_existing_calls(self):
        """Get calls that already exist (e.g. if phone was ringing when we started)."""
        if not self.modem_path:
            return
        try:
            vc = dbus.Interface(
                self.bus.get_object('org.ofono', self.modem_path),
                'org.ofono.VoiceCallManager'
            )
            calls = vc.GetCalls()
            for call_path, call_props in calls:
                self.on_call_added(call_path, call_props)
        except Exception as e:
            log(f'get_existing_calls error: {e}')

    def on_call_added(self, call_path, props):
        """Called when a new call appears."""
        props = dict(props)
        state = props.get('State', '')
        caller = format_caller(props)
        self.active_calls[call_path] = {'state': state, 'caller': caller}
        log(f'CallAdded: {call_path} state={state} caller={caller}')

        if state == 'incoming':
            post_to_sidecar('/ring', {
                'slot': '1',
                'caller': caller,
                'phone': props.get('LineIdentification', '')
            })

    def on_call_removed(self, call_path):
        """Called when a call is removed."""
        info = self.active_calls.pop(call_path, None)
        if info:
            log(f'CallRemoved: {call_path} was {info["state"]}')
            # Only clear the ring if there are no other active/incoming calls
            has_incoming = any(
                c['state'] in ('incoming', 'active', 'held', 'waiting')
                for c in self.active_calls.values()
            )
            if not has_incoming:
                post_to_sidecar('/ring', {'slot': '1', 'clear': '1'})

    def on_call_property_changed(self, call_path, name, value):
        """Called when a call property changes (e.g. incoming -> active)."""
        if call_path in self.active_calls:
            old_state = self.active_calls[call_path]['state']
            self.active_calls[call_path]['state'] = value
            log(f'CallChanged: {call_path} {name}={value} (was {old_state})')
            if name == 'State' and value in ('disconnected', 'ended'):
                self.on_call_removed(call_path)

    def attach_signals(self):
        """Attach D-Bus signals for call events."""
        if not self.modem_path:
            return False
        try:
            vc = dbus.Interface(
                self.bus.get_object('org.ofono', self.modem_path),
                'org.ofono.VoiceCallManager'
            )
            vc.connect_to_signal('CallAdded', self.on_call_added)
            vc.connect_to_signal('CallRemoved', self.on_call_removed)
            log(f'Signals attached on {self.modem_path}')
            return True
        except Exception as e:
            log(f'attach_signals error: {e}')
            return False

    def poll_calls(self):
        """Fallback: poll for call state changes every few seconds."""
        if not self.modem_path:
            new_modem = self.find_modem()
            if new_modem and new_modem != self.modem_path:
                self.modem_path = new_modem
                log(f'Modem found: {self.modem_path}')
                self.attach_signals()
                self.get_existing_calls()
            return

        # Check if modem still exists
        try:
            vc = dbus.Interface(
                self.bus.get_object('org.ofono', self.modem_path),
                'org.ofono.VoiceCallManager'
            )
            calls = vc.GetCalls()
            current = {str(p): dict(cp) for p, cp in calls}

            # New calls
            for cp in current:
                if cp not in self.active_calls:
                    self.on_call_added(cp, current[cp])

            # Removed calls
            for cp in list(self.active_calls.keys()):
                if cp not in current:
                    self.on_call_removed(cp)

            # State changes
            for cp in current:
                if cp in self.active_calls:
                    new_state = current[cp].get('State', '')
                    if new_state != self.active_calls[cp]['state']:
                        self.on_call_property_changed(cp, 'State', new_state)

        except Exception as e:
            log(f'poll error: {e}')
            self.modem_path = None

    def start(self):
        """Start monitoring."""
        self.modem_path = self.find_modem()
        if self.modem_path:
            log(f'Starting with modem: {self.modem_path}')
            self.attach_signals()
            self.get_existing_calls()
        else:
            log('No HFP modem found yet, will poll...')

        # Start fallback poll timer
        def poll_timer():
            while True:
                self.poll_calls()
                time.sleep(POLL_INTERVAL)
        threading.Thread(target=poll_timer, daemon=True).start()


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    monitor = HfpCallMonitor(bus)
    monitor.start()

    # Also watch for modem add/remove
    def on_modem_added(path, props):
        props = dict(props)
        if props.get('Type') == 'hfp':
            log(f'HFP modem added: {path}')
            monitor.modem_path = path
            monitor.attach_signals()
            monitor.get_existing_calls()

    def on_modem_removed(path):
        if path == monitor.modem_path:
            log(f'HFP modem removed: {path}')
            monitor.modem_path = None
            monitor.active_calls.clear()
            post_to_sidecar('/ring', {'slot': '1', 'clear': '1'})

    manager = dbus.Interface(bus.get_object('org.ofono', '/'), 'org.ofono.Manager')
    manager.connect_to_signal('ModemAdded', on_modem_added)
    manager.connect_to_signal('ModemRemoved', on_modem_removed)

    log('HFP Call Monitor started')
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        log('Stopping')
        sys.exit(0)


if __name__ == '__main__':
    main()

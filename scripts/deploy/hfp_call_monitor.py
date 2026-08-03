#!/usr/bin/env python3
"""
HFP Call Monitor — watches oFono VoiceCallManager on EVERY connected phone
(multi-modem) for incoming calls and notifies the homephone-sidecar via
HTTP POST to /ring.

When a call comes in on any phone:
  - oFono emits org.ofono.VoiceCallManager.CallAdded(path, properties)
  - properties includes: State, LineIdentification (caller ID), Name, etc.
  - State "incoming" = ringing, "active" = answered, "disconnected" = ended

Each HFP modem path embeds the phone's BT MAC
(/org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX), which we use as the ring slot so the
hub knows WHICH phone is ringing. We also resolve the phone's BT alias via
org.bluez.Device1 and pass it as phone_name.

We POST to the sidecar:
  /ring?slot=<mac>&caller=<name_or_number>&phone=<number>&phone_name=<bt_alias>  (on incoming)
  /ring?slot=<mac>&clear=1                                                      (on end/answer)

Runs as a systemd user service.
"""
import dbus
import dbus.mainloop.glib
import urllib.request
import urllib.parse
import threading
import time
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

def mac_from_modem_path(modem_path):
    """.../dev_XX_XX_XX_XX_XX_XX -> XX:XX:XX:XX:XX:XX (or None)."""
    if '/dev_' not in modem_path:
        return None
    tail = modem_path.rsplit('/dev_', 1)[1]
    parts = tail.split('_')
    if len(parts) != 6:
        return None
    return ':'.join(p.upper() for p in parts)

class HfpCallMonitor:
    def __init__(self, bus):
        self.bus = bus
        # modem_path -> {'mac': str, 'name': str, 'signals': bool}
        self.modems = {}
        # call_path -> {'state', 'caller', 'modem_path'}
        self.active_calls = {}

    # ----- modem tracking -----

    def find_modems(self):
        """Return a list of all HFP modem paths."""
        try:
            manager = dbus.Interface(
                self.bus.get_object('org.ofono', '/'),
                'org.ofono.Manager'
            )
            return [p for p, props in manager.GetModems() if props.get('Type') == 'hfp']
        except Exception as e:
            log(f'find_modems error: {e}')
            return []

    def resolve_phone_name(self, modem_path):
        """Look up the BT alias of the phone behind this modem via org.bluez.Device1."""
        mac = mac_from_modem_path(modem_path)
        if not mac:
            return ''
        dev_path = '/org/bluez/hci0/dev_' + mac.replace(':', '_')
        try:
            props = dbus.Interface(
                self.bus.get_object('org.bluez', dev_path),
                'org.freedesktop.DBus.Properties'
            )
            alias = str(props.Get('org.bluez.Device1', 'Alias'))
            if alias:
                return alias
            return str(props.Get('org.bluez.Device1', 'Name'))
        except Exception:
            return ''

    def add_modem(self, modem_path):
        if modem_path in self.modems:
            return
        mac = mac_from_modem_path(modem_path) or modem_path
        name = self.resolve_phone_name(modem_path)
        self.modems[modem_path] = {'mac': mac, 'name': name, 'signals': False}
        log(f'Modem added: {modem_path} mac={mac} name={name!r}')
        self.attach_signals(modem_path)
        self.get_existing_calls(modem_path)

    def remove_modem(self, modem_path):
        info = self.modems.pop(modem_path, None)
        if not info:
            return
        log(f'Modem removed: {modem_path}')
        # Clear any calls that belonged to this modem
        for call_path in [p for p, c in self.active_calls.items()
                          if c['modem_path'] == modem_path]:
            self.on_call_removed(call_path)

    # ----- call tracking -----

    def ring_params(self, modem_path, props=None):
        info = self.modems.get(modem_path) or {}
        params = {
            'slot': info.get('mac') or mac_from_modem_path(modem_path) or '1',
            'mac': info.get('mac', ''),
            'phone_name': info.get('name', ''),
        }
        if props is not None:
            params['caller'] = format_caller(props)
            params['phone'] = props.get('LineIdentification', '')
        return params

    def get_existing_calls(self, modem_path):
        """Get calls that already exist (e.g. if phone was ringing when we started)."""
        try:
            vc = dbus.Interface(
                self.bus.get_object('org.ofono', modem_path),
                'org.ofono.VoiceCallManager'
            )
            for call_path, call_props in vc.GetCalls():
                self.on_call_added(modem_path, call_path, call_props)
        except Exception as e:
            log(f'get_existing_calls error: {e}')

    def on_call_added(self, modem_path, call_path, props):
        props = dict(props)
        state = props.get('State', '')
        caller = format_caller(props)
        self.active_calls[call_path] = {
            'state': state, 'caller': caller, 'modem_path': modem_path,
        }
        log(f'CallAdded: {call_path} state={state} caller={caller} modem={modem_path}')
        if state == 'incoming':
            post_to_sidecar('/ring', self.ring_params(modem_path, props))

    def on_call_removed(self, call_path):
        info = self.active_calls.pop(call_path, None)
        if not info:
            return
        log(f'CallRemoved: {call_path} was {info["state"]}')
        # Clear the ring for this phone if it has no other live calls
        same_modem = [c for c in self.active_calls.values()
                      if c['modem_path'] == info['modem_path']]
        if not any(c['state'] in ('incoming', 'active', 'held', 'waiting')
                   for c in same_modem):
            post_to_sidecar('/ring', self.ring_params(info['modem_path']) | {'clear': '1'})

    def on_call_property_changed(self, call_path, name, value):
        if call_path not in self.active_calls:
            return
        call = self.active_calls[call_path]
        old_state = call['state']
        call['state'] = value
        log(f'CallChanged: {call_path} {name}={value} (was {old_state})')
        if name != 'State':
            return
        if value in ('disconnected', 'ended'):
            self.on_call_removed(call_path)
        elif value == 'active' and old_state == 'incoming':
            # Call was answered (on the phone or via the hub) — hide the banner
            post_to_sidecar('/ring', self.ring_params(call['modem_path']) | {'clear': '1'})

    def attach_signals(self, modem_path):
        info = self.modems.get(modem_path)
        if not info or info['signals']:
            return False
        try:
            vc = dbus.Interface(
                self.bus.get_object('org.ofono', modem_path),
                'org.ofono.VoiceCallManager'
            )
            vc.connect_to_signal(
                'CallAdded',
                lambda path, props, mp=modem_path: self.on_call_added(mp, path, props))
            vc.connect_to_signal('CallRemoved', self.on_call_removed)
            info['signals'] = True
            log(f'Signals attached on {modem_path}')
            return True
        except Exception as e:
            log(f'attach_signals error: {e}')
            return False

    def poll(self):
        """Fallback: discover new modems, prune dead ones, sync call state."""
        current_modems = set(self.find_modems())
        for mp in current_modems - set(self.modems):
            self.add_modem(mp)
        for mp in set(self.modems) - current_modems:
            self.remove_modem(mp)

        for modem_path in list(self.modems):
            try:
                vc = dbus.Interface(
                    self.bus.get_object('org.ofono', modem_path),
                    'org.ofono.VoiceCallManager'
                )
                calls = vc.GetCalls()
                current = {str(p): dict(cp) for p, cp in calls}

                for cp in current:
                    if cp not in self.active_calls:
                        self.on_call_added(modem_path, cp, current[cp])
                for cp in list(self.active_calls):
                    if (self.active_calls[cp]['modem_path'] == modem_path
                            and cp not in current):
                        self.on_call_removed(cp)
                for cp in current:
                    if cp in self.active_calls:
                        new_state = current[cp].get('State', '')
                        if new_state != self.active_calls[cp]['state']:
                            self.on_call_property_changed(cp, 'State', new_state)
            except Exception as e:
                log(f'poll error on {modem_path}: {e}')
                self.remove_modem(modem_path)

    def start(self):
        for mp in self.find_modems():
            self.add_modem(mp)
        if not self.modems:
            log('No HFP modem found yet, will poll...')

        def poll_timer():
            while True:
                self.poll()
                time.sleep(POLL_INTERVAL)
        threading.Thread(target=poll_timer, daemon=True).start()


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    monitor = HfpCallMonitor(bus)
    monitor.start()

    manager = dbus.Interface(bus.get_object('org.ofono', '/'), 'org.ofono.Manager')
    manager.connect_to_signal(
        'ModemAdded',
        lambda path, props: monitor.add_modem(path) if dict(props).get('Type') == 'hfp' else None)
    manager.connect_to_signal('ModemRemoved', monitor.remove_modem)

    log('Running (multi-modem).')
    GLib.MainLoop().run()


if __name__ == '__main__':
    main()

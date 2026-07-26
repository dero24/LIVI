#!/usr/bin/env python3
"""Simple Bluetooth agent that auto-accepts pairing (NoInputNoOutput capability).
Runs as a systemd user service so Bluetooth pairing works from the settings page."""
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

AGENT_PATH = '/org/bluez/auto_agent'
CAPABILITY = 'NoInputNoOutput'


class AutoAgent(dbus.service.Object):
    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Release(self):
        pass

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        return '0000'

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def DisplayPasskey(self, device, passkey):
        pass

    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def DisplayPinCode(self, device, pincode):
        pass

    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        # Auto-accept — NoInputNoOutput means we don't interact
        pass

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        pass

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Cancel(self):
        pass


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    agent = AutoAgent(bus, AGENT_PATH)

    manager = dbus.Interface(bus.get_object('org.bluez', '/org/bluez'),
                             'org.bluez.AgentManager1')
    manager.RegisterAgent(AGENT_PATH, CAPABILITY)
    manager.RequestDefaultAgent(AGENT_PATH)
    print('[bt-agent] Registered as default agent (NoInputNoOutput)')

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        manager.UnregisterAgent(AGENT_PATH)
        print('[bt-agent] Unregistered')


if __name__ == '__main__':
    main()

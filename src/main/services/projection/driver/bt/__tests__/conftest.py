"""Pytest configuration for aa_handler contract tests.

Mocks the system-level imports (dbus, gi) so aa_handler can be imported
in a test environment without the Bluetooth stack installed.
"""
import sys
import types


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_dbus():
    dbus = _stub_module('dbus')
    dbus.service = types.ModuleType('dbus.service')
    dbus.service.Object = type('Object', (), {'__init__': lambda self, *a, **k: None})
    dbus.service.BusName = lambda *a, **k: None
    dbus.Interface = lambda *a, **k: None
    dbus.SystemBus = lambda: None
    dbus.ByteArray = bytes
    dbus.mainloop = types.ModuleType('dbus.mainloop')
    dbus.mainloop.glib = types.ModuleType('dbus.mainloop.glib')
    dbus.mainloop.glib.DBusGMainLoop = lambda *a, **k: None


def _stub_gi():
    gi = _stub_module('gi')
    gi.repository = types.ModuleType('gi.repository')
    glib = types.ModuleType('gi.repository.GLib')
    glib.MainLoop = type('MainLoop', (), {
        '__init__': lambda self, *a, **k: None,
        'run': lambda self: None,
        'quit': lambda self: None,
    })
    glib.timeout_add_seconds = lambda *a, **k: 0
    glib.idle_add = lambda *a, **k: 0
    glib.IO_IN = 0
    gi.repository.GLib = glib


_stubs_installed = False


def _install_stubs():
    global _stubs_installed
    if _stubs_installed:
        return
    _stub_dbus()
    _stub_gi()
    _stubs_installed = True


def pytest_configure(config):
    _install_stubs()

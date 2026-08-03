#!/usr/bin/env python3
"""Check if overlay markers are in the ASAR."""
with open('/home/raspberry/LIVI/extracted/resources/app.asar', 'rb') as f:
    data = f.read().decode('utf-8', 'ignore')
print('homehubOpenSettings:', 'homehubOpenSettings' in data)
print('Calibrate Notifications:', 'Calibrate Notifications' in data)
print('in-iframe:', 'in-iframe' in data)
print('Re-calibrate Apps:', 'Re-calibrate Apps' in data)
print('Forget Phone:', 'Forget Phone' in data)
print('Name Phone button:', 'Rename Phone' in data)
print('settings cache-buster:', '/settings?_=' in data)
print('settings retry logic:', 'MAX_SETTINGS_ATTEMPTS' in data)
print('header-hide injection:', '.header{display:none!important}' in data)
print('registration force mode:', 'showRegistrationPrompt(deviceId, defaultName, onComplete, force)' in data)

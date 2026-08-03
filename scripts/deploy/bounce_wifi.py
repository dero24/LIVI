#!/usr/bin/env python3
"""
Playwright script: bounce wlan0 on the Pi via the settings page API.
Use this when the Pi is reachable but wlan0 is flaky, or proactively
to prevent drops.

Usage:
  python bounce_wifi.py              # Uses default Pi IP
  python bounce_wifi.py 192.168.1.X  # Custom IP

Requires: pip install playwright && playwright install chromium
"""
import sys
import time
import urllib.request
import urllib.error

# Default Pi IP — change if different
PI_IP = sys.argv[1] if len(sys.argv) > 1 else '192.168.1.80'
SIDECAR_URL = f'http://{PI_IP}:8123'

def bounce_wifi_api():
    """Bounce WiFi via the sidecar API (no browser needed)."""
    print(f'Bouncing WiFi on {PI_IP} via API...')
    try:
        # POST /api/wifi/reconnect
        url = f'{SIDECAR_URL}/api/wifi/reconnect'
        req = urllib.request.Request(url, method='POST', data=b'{}')
        req.add_header('Content-Type', 'application/json')
        print(f'  POST {url}')
        resp = urllib.request.urlopen(req, timeout=45)
        import json
        result = json.loads(resp.read())
        print(f'  Response: {result}')
        if result.get('status') == 'ok':
            print('  WiFi bounced successfully!')
            return True
        else:
            print(f'  Failed: {result.get("message", "unknown")}')
            return False
    except urllib.error.URLError as e:
        print(f'  Network error: {e}')
        print('  Pi may be unreachable. Try rebooting.')
        return False
    except Exception as e:
        print(f'  Error: {e}')
        return False

def bounce_wifi_playwright():
    """Bounce WiFi via the settings page UI using Playwright.
    This is the fallback if the API doesn't work."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright not installed. Install with:')
        print('  pip install playwright && playwright install chromium')
        return False

    print(f'Bouncing WiFi on {PI_IP} via Playwright (UI)...')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to settings page
        url = f'{SIDECAR_URL}/settings'
        print(f'  Navigating to {url}')
        try:
            page.goto(url, timeout=15000)
        except Exception as e:
            print(f'  Failed to load settings page: {e}')
            browser.close()
            return False

        # Click the WiFi tab
        try:
            wifi_tab = page.locator('button[data-tab="wifi"]')
            if wifi_tab.count() > 0:
                wifi_tab.click()
                print('  Clicked WiFi tab')
                time.sleep(2)
        except Exception as e:
            print(f'  Could not click WiFi tab: {e}')

        # Click the Disconnect & Reconnect button
        try:
            reconnect_btn = page.locator('#wifi-reconnect-btn')
            if reconnect_btn.count() > 0:
                reconnect_btn.click()
                print('  Clicked Disconnect & Reconnect')
                # Wait for it to complete
                time.sleep(35)
                print('  WiFi bounce complete')
                browser.close()
                return True
            else:
                print('  Reconnect button not found')
                browser.close()
                return False
        except Exception as e:
            print(f'  Could not click reconnect: {e}')
            browser.close()
            return False

if __name__ == '__main__':
    print(f'=== WiFi Bounce Tool ===')
    print(f'Pi IP: {PI_IP}')
    print()

    # Try API first (faster, no browser)
    if bounce_wifi_api():
        print('\nDone! WiFi bounced via API.')
        sys.exit(0)

    # Fall back to Playwright UI
    print('\nAPI failed, trying Playwright UI...')
    if bounce_wifi_playwright():
        print('\nDone! WiFi bounced via UI.')
        sys.exit(0)

    print('\nFailed to bounce WiFi. Pi may need a reboot.')
    sys.exit(1)

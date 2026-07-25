#!/usr/bin/env python3
"""
Upload photos to the Raspberry Pi for the home hub screensaver/background.

Usage:
  python upload_photos.py photo1.jpg photo2.png /path/to/folder/*.jpg

Photos are uploaded to /home/raspberry/photos/ on the Pi.
Supported formats: .jpg .jpeg .png .gif .webp .bmp
"""
import sys
import os

# Add pi_ctl functions
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pi_ctl import put_file, run_command

PHOTOS_DIR = '/home/raspberry/photos'

def main():
    if len(sys.argv) < 2:
        print("Usage: python upload_photos.py <photo files...>")
        print("Example: python upload_photos.py vacation/*.jpg family.png")
        print(f"\nPhotos are uploaded to {PHOTOS_DIR} on the Pi.")
        print("They will appear as the home hub background and in the screensaver slideshow.")
        sys.exit(1)

    # Ensure photos directory exists
    run_command(f'mkdir -p {PHOTOS_DIR}')

    uploaded = 0
    for path in sys.argv[1:]:
        if not os.path.isfile(path):
            print(f"  Skipping {path} — not a file")
            continue

        ext = os.path.splitext(path)[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
            print(f"  Skipping {path} — unsupported format ({ext})")
            continue

        filename = os.path.basename(path)
        remote_path = f'{PHOTOS_DIR}/{filename}'
        print(f"  Uploading {filename}...", end=' ', flush=True)
        try:
            put_file(path, remote_path)
            print("OK")
            uploaded += 1
        except Exception as e:
            print(f"FAILED: {e}")

    print(f"\nUploaded {uploaded} photo(s) to {PHOTOS_DIR}")

    # List what's there now
    print(f"\nPhotos on Pi:")
    run_command(f'ls -1 {PHOTOS_DIR} 2>/dev/null | head -20')

if __name__ == '__main__':
    main()

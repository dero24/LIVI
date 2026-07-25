#!/usr/bin/env python3
import json, struct, sys
p = '/home/raspberry/LIVI/extracted/resources/app.asar'
with open(p, 'rb') as f:
    header_size = struct.unpack('<I', f.read(4))[0]
    print('header_size (raw 4 bytes):', header_size)
    header_bytes = f.read(header_size)
    # Try json parse
    try:
        header = json.loads(header_bytes)
        print('parsed header len', len(header_bytes))
        # print first 500 chars
        print(json.dumps(header)[:500])
    except Exception as e:
        print('json parse failed', e)
        # try stripping trailing nulls
        header = json.loads(header_bytes.rstrip(b'\x00'))
        print('parsed after strip, len', len(header_bytes.rstrip(b'\x00')))

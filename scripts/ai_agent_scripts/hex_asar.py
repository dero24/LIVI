#!/usr/bin/env python3
p = '/home/raspberry/LIVI/extracted/resources/app.asar'
print(open(p, 'rb').read(64).hex())

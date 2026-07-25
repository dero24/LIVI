import re
p = '/home/raspberry/LIVI/extracted/resources/app.asar.unpacked/out/main/main.js'
d = open(p, 'rb').read().decode('utf-8', 'ignore')
for m in re.finditer(r'\.sendTouch\(', d):
    s = m.start()
    print('---', s)
    print(d[s-100:s+150])
    print()

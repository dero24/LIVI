#!/usr/bin/env python3
"""Add touch logging to the unpacked main.js."""
p = '/home/raspberry/LIVI/extracted/resources/app.asar.unpacked/out/main/main.js'
data = open(p, 'rb').read().decode('utf-8', 'ignore')

changes = 0

# 1. Single-touch: log before sendTouch call
old1 = 'let s={id:0,x:Math.round(a),y:Math.round(o)};return this._aa.sendTouch(Pl(e.action),[s]),!0'
new1 = 'let s={id:0,x:Math.round(a),y:Math.round(o)};console.log("[TOUCH] single action="+e.action+" x="+s.x+" y="+s.y+" usable="+t+"x"+n);return this._aa.sendTouch(Pl(e.action),[s]),!0'
if old1 in data:
    data = data.replace(old1, new1, 1)
    changes += 1
    print('patched single-touch sendTouch')
else:
    print('WARN: single-touch pattern not found')

# 2. Single-touch drop: log when out of bounds
old2 = 'if(a<0||o<0||a>=t||o>=n)return!0;let s={id:0'
new2 = 'if(a<0||o<0||a>=t||o>=n){console.log("[TOUCH] single DROPPED ux="+a+" uy="+o+" usable="+t+"x"+n);return!0}let s={id:0'
if old2 in data:
    data = data.replace(old2, new2, 1)
    changes += 1
    print('patched single-touch drop')
else:
    print('WARN: single-touch drop pattern not found')

# 3. Multi-touch: log before sendTouch call
old3 = 'return c.length===0||this._aa.sendTouch(i,c,a),!0'
new3 = 'if(c.length>0)console.log("[TOUCH] multi action="+i+" count="+c.length+" idx="+a+" pts="+JSON.stringify(c.map(function(p){return{id:p.id,x:p.x,y:p.y}})));return c.length===0||this._aa.sendTouch(i,c,a),!0'
if old3 in data:
    data = data.replace(old3, new3, 1)
    changes += 1
    print('patched multi-touch sendTouch')
else:
    print('WARN: multi-touch pattern not found')

if changes > 0:
    open(p, 'wb').write(data.encode('utf-8'))
    print(f'wrote patched main.js ({changes} changes)')
else:
    print('ERROR: no changes made')

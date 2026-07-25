import json, struct
p = "/home/raspberry/LIVI/extracted/resources/app.asar"
with open(p, "rb") as f:
    f.read(4)
    s = struct.unpack("<I", f.read(4))[0] - 8
    f.read(8)
    d = f.read(s)
end = d.rfind(b"}")
d = d[:end+1]
bl = d.count(b"{")
br = d.count(b"}")
print(br - bl, "braces unmatched")
try:
    h = json.loads(d)
    info = h["files"]["out"]["files"]["main"]["files"]["main.js"]
    print("main.js:", json.dumps(info))
except Exception as e:
    print("parse error:", e)
    print("tail:", d[-200:])

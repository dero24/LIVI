import json
d = json.load(open("/home/raspberry/.config/LIVI/config.json"))
for k in ["projectionWidth","projectionHeight","projectionDpi","projectionFps",
          "mainScreenWidth","mainScreenHeight","displayMode",
          "projectionViewAreaTop","projectionViewAreaBottom",
          "projectionViewAreaLeft","projectionViewAreaRight",
          "projectionSafeAreaTop","projectionSafeAreaBottom",
          "projectionSafeAreaLeft","projectionSafeAreaRight"]:
    print(k, "=", d.get(k))

#!/usr/bin/env python3
p = '/home/raspberry/LIVI/extracted/resources/app.asar.unpacked/out/main/main.js'
data = open(p, 'rb').read().decode('utf-8', 'ignore')

# 1. Replace waitForAccessoryAttach (lu) with a version that polls usb.getDevices()
old_lu = "function lu(e){return new Promise((t,n)=>{let r=e=>{let d=e.device;d.vendorId==6353&&d.productId>>8==45&&(clearTimeout(i),t(d))},i=setTimeout(()=>n('t'),e);A.usb.getDevices().then(d=>{d=d.find(x=>x.vendorId==6353&&x.productId>>8==45);d?(clearTimeout(i),t(d)):A.usb.addEventListener('connect',r)})})}"
new_lu = """function lu(e){return new Promise((t,n)=>{let r=null,i=null;const a=e=>{let n=e.device;n.vendorId===6353&&Rl.includes(n.productId)&&(s(),t(n))},o=()=>{A.usb.getDevices().then(e=>{let n=e.find(e=>e.vendorId===6353&&Rl.includes(e.productId));n&&(s(),t(n))}).catch(()=>{})},s=()=>{r&&(clearTimeout(r),r=null),i&&(clearInterval(i),i=null);try{A.usb.removeEventListener('connect',a)}catch{}};r=setTimeout(()=>{s(),n(new Error('AOAP re-enumerate timeout'))},e),i=setInterval(o,100),o(),A.usb.addEventListener('connect',a)})}"""
if old_lu not in data:
    print('old lu not found')
    raise SystemExit(1)
data = data.replace(old_lu, new_lu, 1)
print('patched lu')

# 2. Replace _switchAndOpenAccessory to reset an already-accessory device before starting AA
old_switch = "async _switchAndOpenAccessory(){let e,t=Yl(this._device);if(console.log(`[UsbAoapBridge] switchAndOpen isAccessoryMode=${t} vid=0x${this._device.vendorId?.toString(16)} pid=0x${this._device.productId?.toString(16)}`),t)e=this._device,await this._openWithRetry(e,`AOAP accessory device`);else{await this._openWithRetry(this._device,`AOAP device`);let t=lu(ql);t.catch(()=>{}),this._onWillReenumerate?.(ql+2e3),console.log(`[UsbAoapBridge] AOAP handshake starting`);try{await iu(this._device),console.log(`[UsbAoapBridge] AOAP handshake sent — awaiting accessory re-enumeration`)}finally{try{await this._device.close()}catch{}}e=await t,console.log(`[UsbAoapBridge] accessory re-enumerated — opening`),await this._openWithRetry(e,`AOAP accessory device (post-handshake)`)}try{e.configuration?.configurationValue!==1"
new_switch = "async _switchAndOpenAccessory(){let e;const t=Yl(this._device);console.log(`[UsbAoapBridge] switchAndOpen isAccessoryMode=${t} vid=0x${this._device.vendorId?.toString(16)} pid=0x${this._device.productId?.toString(16)}`);this._onWillReenumerate?.(ql+2e3);if(t){console.log(`[UsbAoapBridge] accessory device at startup — opening for reset`);await this._openWithRetry(this._device,`AOAP accessory device`);console.log(`[UsbAoapBridge] resetting accessory device for clean AA session`);try{await this._device.reset()}catch(e){console.warn(`[UsbAoapBridge] reset failed: ${String(e)}`)}try{await this._device.close()}catch{}}else{await this._openWithRetry(this._device,`AOAP device`);console.log(`[UsbAoapBridge] AOAP handshake starting`);try{await iu(this._device),console.log(`[UsbAoapBridge] AOAP handshake sent — awaiting accessory re-enumeration`)}finally{try{await this._device.close()}catch{}}}let n=lu(ql);n.catch(()=>{});e=await n,console.log(`[UsbAoapBridge] accessory re-enumerated — opening`),await this._openWithRetry(e,`AOAP accessory device (post-handshake)`);try{e.configuration?.configurationValue!==1"
if old_switch not in data:
    print('old switch not found')
    raise SystemExit(1)
data = data.replace(old_switch, new_switch, 1)
print('patched switch')

open(p, 'wb').write(data.encode('utf-8'))
print('wrote patched main.js')

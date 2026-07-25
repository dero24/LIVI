#!/usr/bin/env python3
import shutil

path = '/home/raspberry/LIVI/extracted/resources/app.asar'
backup = path + '.orig'

old = b"function lu(e){return new Promise((t,n)=>{let r=e=>{let n=e.device;n.vendorId===6353&&Rl.includes(n.productId)&&(a(),t(n))},i=setTimeout(()=>{a(),n(Error(`AOAP re-enumerate timeout`))},e),a=()=>{clearTimeout(i);try{A.usb.removeEventListener(`connect`,r)}catch{}};A.usb.addEventListener(`connect`,r)})}"

# Same length (301 bytes). Scans already-present devices before listening.
new_body = b"function lu(e){return new Promise((t,n)=>{let r=e=>{let d=e.device;d.vendorId==6353&&d.productId>>8==45&&(clearTimeout(i),t(d))},i=setTimeout(()=>n('t'),e);A.usb.getDevices().then(d=>{d=d.find(x=>x.vendorId==6353&&x.productId>>8==45);d?(clearTimeout(i),t(d)):A.usb.addEventListener('connect',r)})})}"

pad = len(old) - len(new_body)
if pad < 0:
    raise ValueError(f'new function is {-pad} bytes too long')
new = new_body + b' ' * pad

print('old len', len(old), 'new len', len(new))
assert len(old) == len(new)

shutil.copy(path, backup)
data = open(path, 'rb').read()
count = data.count(old)
print('occurrences:', count)
if count != 1:
    raise ValueError('expected exactly one occurrence')
new_data = data.replace(old, new)
open(path, 'wb').write(new_data)
print('patched')

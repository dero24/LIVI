#!/usr/bin/env python3
"""Trace the full touch coordinate pipeline for the current config."""

# Config
proj_w, proj_h = 600, 1024  # portrait display
screen_w, screen_h = 600, 988  # after compositor fullscreen (1024-36=988)

# AA tiers (all landscape 16:9)
tiers = [(800,480), (1280,720), (1920,1080), (2560,1440), (3840,2160)]
h264_only = False
max_tier_w = 1920 if h264_only else 999999
max_upscale = 1.2

def round_even(n):
    return max(2, int(n) & ~1)

def aa_content_area(frame_w, frame_h, user_w, user_h):
    user_ar = max(1, user_w) / max(1, user_h)
    frame_ar = max(1, frame_w) / max(1, frame_h)
    if user_ar <= frame_ar:
        return round_even(frame_h * user_ar), frame_h
    return frame_w, round_even(frame_w / user_ar)

# matchFittingAAResolution
chosen = tiers[0]
for tier in tiers:
    if tier[0] > max_tier_w:
        break
    chosen = tier
    cw, ch = aa_content_area(tier[0], tier[1], proj_w, proj_h)
    upscale = max(proj_w / cw, proj_h / ch)
    if upscale <= max_upscale:
        break

tier_w, tier_h = chosen
content_w, content_h = aa_content_area(tier_w, tier_h, proj_w, proj_h)

print("=== AA Resolution Selection ===")
print(f"Display: {proj_w}x{proj_h} (AR={proj_w/proj_h:.3f} portrait)")
print(f"AA tier: {tier_w}x{tier_h} (AR={tier_w/tier_h:.3f} landscape)")
print(f"Content area: {content_w}x{content_h} (AR={content_w/content_h:.3f})")
print(f"Letterbox: left/right={(tier_w-content_w)//2}/{tier_w-content_w-(tier_w-content_w)//2} px, top/bottom=0/0")
print(f"Content uses {content_w/tier_w*100:.1f}% of frame width")
print()

# AaSession touch mapping
ar_w_margin = tier_w - content_w
ar_left = ar_w_margin // 2
ar_right = ar_w_margin - ar_left
touch_w, touch_h = tier_w, tier_h
inset_left, inset_right = ar_left, ar_right
inset_top, inset_bottom = 0, 0
usable_w = touch_w - inset_left - inset_right
usable_h = touch_h - inset_top - inset_bottom

print("=== AaSession Touch Mapping ===")
print(f"touchW={touch_w}, touchH={touch_h}")
print(f"insets: L={inset_left} R={inset_right} T={inset_top} B={inset_bottom}")
print(f"usable: {usable_w}x{usable_h}")
print(f"Touchscreen advertised to phone: {usable_w}x{usable_h}")
print()

# Renderer touch transform
# streamWidth=negotiatedWidth(=tierW), streamHeight=negotiatedHeight(=tierH)
# visibleWidth=contentWidth, visibleHeight=contentHeight
# cropLeft=(tierW-contentW)/2, cropTop=(tierH-contentH)/2
stream_w, stream_h = tier_w, tier_h
visible_w, visible_h = content_w, content_h
crop_left = (tier_w - content_w) / 2
crop_top = (tier_h - content_h) / 2

print("=== Renderer Touch Transform ===")
print(f"streamWidth={stream_w}, streamHeight={stream_h}")
print(f"visibleWidth={visible_w}, visibleHeight={visible_h}")
print(f"cropLeft={crop_left}, cropTop={crop_top}")
print()

# Simulate: what does the phone receive for various screen touches?
print("=== Touch Simulation (screen -> phone coord) ===")
content_ar = visible_w / visible_h
for sy_pct in [0.1, 0.5, 0.9]:
    for sx_pct in [0.05, 0.5, 0.95]:
        sx = sx_pct * screen_w
        sy = sy_pct * screen_h

        # norm() in useProjectionTouch
        container_ar = screen_w / screen_h
        if container_ar > content_ar:
            disp_w = screen_h * content_ar
            disp_h = screen_h
            off_x = (screen_w - disp_w) / 2
            off_y = 0
        else:
            disp_w = screen_w
            disp_h = screen_w / content_ar
            off_x = 0
            off_y = (screen_h - disp_h) / 2

        lx = sx - off_x
        ly = sy - off_y
        if lx < 0 or lx > disp_w or ly < 0 or ly > disp_h:
            print(f"  screen({sx:.0f},{sy:.0f}) -> OUTSIDE content area (dropped by renderer)")
            continue

        stream_x = crop_left + (lx / disp_w) * visible_w
        stream_y = crop_top + (ly / disp_h) * visible_h
        norm_x = max(0, min(1, stream_x / stream_w))
        norm_y = max(0, min(1, stream_y / stream_h))

        # AaSession.send(SendTouch)
        tier_x = max(0, min(1, norm_x)) * touch_w
        tier_y = max(0, min(1, norm_y)) * touch_h
        ux = tier_x - inset_left
        uy = tier_y - inset_top

        if ux < 0 or uy < 0 or ux >= usable_w or uy >= usable_h:
            print(f"  screen({sx:.0f},{sy:.0f}) -> norm=({norm_x:.3f},{norm_y:.3f}) -> tier=({tier_x:.0f},{tier_y:.0f}) -> ux,uy=({ux:.0f},{uy:.0f}) DROPPED by AaSession")
        else:
            print(f"  screen({sx:.0f},{sy:.0f}) -> norm=({norm_x:.3f},{norm_y:.3f}) -> tier=({tier_x:.0f},{tier_y:.0f}) -> phone=({ux:.0f},{uy:.0f}) OK")

print()
print("=== KEY INSIGHT ===")
print(f"The phone renders into a {content_w}x{content_h} portrait strip")
print(f"centered in a {tier_w}x{tier_h} landscape frame.")
print(f"Only {content_w/tier_w*100:.0f}% of the frame width is content.")
print(f"If Maps renders fullscreen at {tier_w}x{tier_h} (ignoring margins),")
print(f"the touchable content area ({content_w}x{content_h}) won't cover")
print(f"the full Maps UI, and coordinates will be wrong.")
print()
print(f"=== ALTERNATIVE: landscape projection ===")
alt_w, alt_h = 1024, 600
alt_tier = tiers[0]
for tier in tiers:
    if tier[0] > max_tier_w:
        break
    alt_tier = tier
    cw, ch = aa_content_area(tier[0], tier[1], alt_w, alt_h)
    upscale = max(alt_w / cw, alt_h / ch)
    if upscale <= max_upscale:
        break
alt_cw, alt_ch = aa_content_area(alt_tier[0], alt_tier[1], alt_w, alt_h)
print(f"If projection={alt_w}x{alt_h} (landscape):")
print(f"  AA tier: {alt_tier[0]}x{alt_tier[1]}")
print(f"  Content: {alt_cw}x{alt_ch} ({alt_cw/alt_tier[0]*100:.1f}% of frame)")
print(f"  Letterbox: L/R={(alt_tier[0]-alt_cw)//2}/{alt_tier[0]-alt_cw-(alt_tier[0]-alt_cw)//2}")

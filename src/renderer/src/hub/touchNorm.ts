// [hub] Touch coordinate conversion: display px → normalized tier coords.
//
// The AA video is rendered into a 16:9 "tier" frame (e.g. 1920×1080) with the
// portrait content letterboxed inside it (e.g. 632×1080 centered with 644px
// margins). The GStreamer pipeline crops the content area from the tier and
// stretches it to fill the physical display (600×1024).
//
// The AaSession's SendTouch handler expects normalized coordinates (0-1)
// relative to the FULL tier, then subtracts the letterbox+view-area insets
// internally (_touchInsetTop = arTop + projectionViewAreaTop, _touchInsetLeft
// = arLeft, etc.). So the renderer must map display px → tier content px →
// normalized 0-1, WITHOUT offsetting for the bar — AaSession handles that.
//
// [hub] CRITICAL: Do NOT offset Y by viewAreaTop here. AaSession already
// subtracts _touchInsetTop (which includes projectionViewAreaTop) from tierY.
// Offsetting Y in the renderer too causes a DOUBLE offset — touches land too
// low or are silently dropped (uy < 0 in AaSession). The old project
// (patch_homehub_v2.py:174-178) does NOT offset Y: tierY = (dispY/1024)*1080.
//
// [hub] The tier is computed from the projection config using
// matchFittingAAResolution — the same function AaSession._buildStackConfig
// uses. This avoids depending on negotiatedWidth/Height which are never set
// in the renderer store (no IPC channel sends them from main). For 600×1024
// the fitting tier is always 1920×1080 (H.264 max, HEVC doesn't change it
// because the next tier 2560×1440 would be 2.5× upscale).

import { aaContentArea, matchFittingAAResolution } from '@shared/utils'

export interface TouchTransform {
  // Canonical 16:9 tier dimensions
  streamWidth: number
  streamHeight: number
  // Content area within the tier (letterboxed)
  cropLeft: number
  cropTop: number
  visibleWidth: number
  visibleHeight: number
  // Bar height in display px (projectionViewAreaTop)
  viewAreaTop: number
}

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v)

// Build a TouchTransform from projection config. Returns null if projection
// settings are not available. The tier is computed via matchFittingAAResolution
// (same as AaSession), so this works without negotiatedWidth/Height.
export function buildTouchTransform(params: {
  projectionWidth: number
  projectionHeight: number
  projectionViewAreaTop: number
}): TouchTransform | null {
  const { projectionWidth, projectionHeight, projectionViewAreaTop } = params
  if (projectionWidth <= 0 || projectionHeight <= 0) return null

  // Compute the AA tier the same way AaSession does. h264Only defaults to
  // false (the Pi supports HEVC); for 600×1024 the result is 1920×1080
  // regardless because the next tier is too much upscaling.
  const tier = matchFittingAAResolution(
    { width: projectionWidth, height: projectionHeight },
    { h264Only: false }
  )
  const tierW = tier.width
  const tierH = tier.height

  const content = aaContentArea(
    { width: tierW, height: tierH },
    { width: projectionWidth, height: projectionHeight }
  )
  if (content.contentWidth <= 0 || content.contentHeight <= 0) return null

  return {
    streamWidth: tierW,
    streamHeight: tierH,
    cropLeft: Math.max(0, (tierW - content.contentWidth) / 2),
    cropTop: Math.max(0, (tierH - content.contentHeight) / 2),
    visibleWidth: content.contentWidth,
    visibleHeight: content.contentHeight,
    viewAreaTop: Math.max(0, projectionViewAreaTop)
  }
}

// Convert display px (e.clientX, e.clientY) to normalized touch coords (0-1)
// relative to the full AA tier. Returns null if the touch is outside the
// display bounds. AaSession handles the letterbox inset + view-area top
// subtraction internally — this function does NOT offset by viewAreaTop.
//
// This matches the old project's coordinate conversion
// (patch_homehub_v2.py:174-178):
//   tierX = cropLeft + (dispX / displayWidth) * visibleWidth
//   tierY = (dispY / displayHeight) * streamHeight
//   normX = tierX / streamWidth
//   normY = tierY / streamHeight
//
// The display shows the AA content area (e.g. 632×1080) stretched to fill
// the full display (e.g. 600×1024). The letterbox margins (644px left/right)
// are IN the tier, not in the display — the display has no letterbox bars.
// The bar offset (viewAreaTop) is handled by AaSession's _touchInsetTop
// subtraction. Offsetting Y here would double-offset (renderer + AaSession
// both subtract the bar height), causing touches to land too low or be
// dropped entirely (Bug A/B, work-log 23).
export function displayToTouchNorm(
  dispX: number,
  dispY: number,
  transform: TouchTransform,
  displayWidth: number,
  displayHeight: number
): { x: number; y: number } | null {
  if (displayWidth <= 0 || displayHeight <= 0) return null
  if (dispX < 0 || dispX > displayWidth || dispY < 0 || dispY > displayHeight) return null

  // Map display px → tier content px (linear, no display-side letterbox).
  // X: full display width maps to the content area width within the tier.
  // Y: full display height maps to the full tier height (NOT the content
  //    area height — the bar offset is handled by AaSession's _touchInsetTop).
  const tierX = transform.cropLeft + (dispX / displayWidth) * transform.visibleWidth
  const tierY = (dispY / displayHeight) * transform.streamHeight
  return {
    x: clamp01(tierX / transform.streamWidth),
    y: clamp01(tierY / transform.streamHeight)
  }
}

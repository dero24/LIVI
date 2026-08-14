// [hub] Touch coordinate conversion: display px → normalized tier coords.
//
// The AA video is rendered into a 16:9 "tier" frame (e.g. 1920×1080) with the
// portrait content letterboxed inside it (e.g. 632×1080 centered with 644px
// margins). The GStreamer pipeline stretches this tier to fill the physical
// display (600×1024), minus the bar inset (projectionViewAreaTop).
//
// The AaSession's SendTouch handler expects normalized coordinates (0-1)
// relative to the FULL tier, then subtracts the letterbox insets internally.
// So the renderer must map display px → tier px (accounting for letterboxing
// and the view-area top offset) → normalized 0-1.
//
// This is the same logic as useProjectionTouch.ts's `norm` function, but
// simplified for the hub's use case where the video container fills the full
// screen (r.left = 0, r.top = 0, r.width = innerWidth, r.height = innerHeight).

import { aaContentArea } from '@shared/utils'

export interface TouchTransform {
  // Canonical 16:9 tier dimensions (negotiatedWidth/Height from the AA session)
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

// Build a TouchTransform from LIVI store values. Returns null if the
// negotiated resolution or projection settings are not yet available.
export function buildTouchTransform(params: {
  negotiatedWidth: number | null
  negotiatedHeight: number | null
  projectionWidth: number
  projectionHeight: number
  projectionViewAreaTop: number
}): TouchTransform | null {
  const { negotiatedWidth, negotiatedHeight, projectionWidth, projectionHeight, projectionViewAreaTop } = params
  if (
    !negotiatedWidth ||
    !negotiatedHeight ||
    projectionWidth <= 0 ||
    projectionHeight <= 0
  ) {
    return null
  }

  const content = aaContentArea(
    { width: negotiatedWidth, height: negotiatedHeight },
    { width: projectionWidth, height: projectionHeight }
  )
  if (content.contentWidth <= 0 || content.contentHeight <= 0) return null

  return {
    streamWidth: negotiatedWidth,
    streamHeight: negotiatedHeight,
    cropLeft: Math.max(0, (negotiatedWidth - content.contentWidth) / 2),
    cropTop: Math.max(0, (negotiatedHeight - content.contentHeight) / 2),
    visibleWidth: content.contentWidth,
    visibleHeight: content.contentHeight,
    viewAreaTop: Math.max(0, projectionViewAreaTop)
  }
}

// Convert display px (e.clientX, e.clientY) to normalized touch coords (0-1)
// relative to the full AA tier. Returns null if the touch is outside the
// content area (letterboxed region below the bar).
export function displayToTouchNorm(
  dispX: number,
  dispY: number,
  transform: TouchTransform,
  displayWidth: number,
  displayHeight: number
): { x: number; y: number } | null {
  // The video container fills the full screen.
  const rLeft = 0
  const rTop = 0
  const rWidth = displayWidth
  const rHeight = displayHeight

  // Content area on the display: from viewAreaTop to bottom.
  const vat = transform.viewAreaTop
  const contentAreaHeight = rHeight - vat
  if (contentAreaHeight <= 0) return null

  // Letterbox the content within the available area based on content AR.
  const contentAR = transform.visibleWidth / transform.visibleHeight
  let dispW = rWidth
  let dispH = contentAreaHeight
  let offX = 0
  let offY = vat
  if (rWidth / contentAreaHeight > contentAR) {
    dispW = contentAreaHeight * contentAR
    offX = (rWidth - dispW) / 2
  } else {
    dispH = rWidth / contentAR
    offY = vat + (contentAreaHeight - dispH) / 2
  }

  const lx = dispX - rLeft - offX
  const ly = dispY - rTop - offY
  if (lx < 0 || lx > dispW || ly < 0 || ly > dispH) return null

  // Map from display content area to tier content area, then normalize.
  const streamX = transform.cropLeft + (lx / dispW) * transform.visibleWidth
  const streamY = transform.cropTop + (ly / dispH) * transform.visibleHeight
  return {
    x: clamp01(streamX / transform.streamWidth),
    y: clamp01(streamY / transform.streamHeight)
  }
}

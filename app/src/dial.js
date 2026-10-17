// Brightness dial geometry: a 270° arc open at the bottom, like a thermostat.
// Angles are in screen degrees: 0° points right and values grow clockwise.

export const MIN = 1
export const MAX = 100
export const START_ANGLE = 135
export const SWEEP = 270

export function clampBrightness(value) {
  return Math.min(MAX, Math.max(MIN, Math.round(value)))
}

export function valueToAngle(value) {
  return START_ANGLE + ((clampBrightness(value) - MIN) / (MAX - MIN)) * SWEEP
}

export function pointOnCircle(cx, cy, radius, angle) {
  const radians = (angle * Math.PI) / 180
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) }
}

/** SVG path of the whole dial arc (clockwise from START_ANGLE). */
export function arcPath(cx, cy, radius) {
  const start = pointOnCircle(cx, cy, radius, START_ANGLE)
  const end = pointOnCircle(cx, cy, radius, START_ANGLE + SWEEP)
  const round = (n) => Math.round(n * 1000) / 1000
  return `M ${round(start.x)} ${round(start.y)} A ${radius} ${radius} 0 1 1 ${round(end.x)} ${round(end.y)}`
}

export function pointerAngle(x, y, cx, cy) {
  return (Math.atan2(y - cy, x - cx) * 180) / Math.PI
}

/**
 * Value for a pointer angle. Inside the open gap at the bottom the nearer end
 * is used. While dragging (`previous` given) the value never jumps across the
 * gap from one end to the other: if the shortest way from the previous
 * position passes through the gap, it stops at that end (100 % stays 100 %).
 */
export function angleToValue(angle, previous = null) {
  let relative = (((angle - START_ANGLE) % 360) + 360) % 360
  if (previous !== null) {
    const from = ((clampBrightness(previous) - MIN) / (MAX - MIN)) * SWEEP
    const delta = ((((relative - from) % 360) + 540) % 360) - 180
    if (from + delta > SWEEP) return MAX
    if (from + delta < 0) return MIN
  } else if (relative > SWEEP) {
    relative = relative < SWEEP + (360 - SWEEP) / 2 ? SWEEP : 0
  }
  return clampBrightness(MIN + (relative / SWEEP) * (MAX - MIN))
}

/** Arrow/Page/Home/End handling shared by keyboard users of the dial. */
export function keyToValue(key, value, { shift = false } = {}) {
  const step = shift ? 10 : 1
  switch (key) {
    case 'ArrowUp':
    case 'ArrowRight':
      return clampBrightness(value + step)
    case 'ArrowDown':
    case 'ArrowLeft':
      return clampBrightness(value - step)
    case 'PageUp':
      return clampBrightness(value + 10)
    case 'PageDown':
      return clampBrightness(value - 10)
    case 'Home':
      return MIN
    case 'End':
      return MAX
    default:
      return null
  }
}

import { Capacitor } from '@capacitor/core'
import { Haptics, ImpactStyle } from '@capacitor/haptics'

// Only on the phone: in a browser the plugin falls back to long vibrations.
const native = Capacitor.isNativePlatform()

function run(action) {
  if (!native) return
  action().catch(() => {})
}

export const tap = () => run(() => Haptics.impact({ style: ImpactStyle.Light }))
export const ticksStart = () => run(() => Haptics.selectionStart())
export const tick = () => run(() => Haptics.selectionChanged())
export const ticksEnd = () => run(() => Haptics.selectionEnd())

/** A tick each time the value crosses a multiple of `step` while dragging. */
export function tickOnStep(previous, next, step = 10) {
  if (previous !== null && Math.floor(previous / step) !== Math.floor(next / step)) tick()
}

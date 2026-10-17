<script setup>
import { computed, ref, watch } from 'vue'
import {
  MAX, MIN, START_ANGLE, SWEEP,
  angleToValue, arcPath, clampBrightness, keyToValue, pointOnCircle, pointerAngle, valueToAngle,
} from '../dial.js'
import { tickOnStep, ticksEnd, ticksStart } from '../haptics.js'

const props = defineProps({
  value: { type: Number, required: true },
  on: { type: Boolean, default: false },
  label: { type: String, required: true },
})
const emit = defineEmits(['update'])

const SIZE = 260
const CENTER = SIZE / 2
const RADIUS = 104
const STROKE = 24
const track = arcPath(CENTER, CENTER, RADIUS)
const ticks = Array.from({ length: 11 }, (_, index) => {
  const angle = START_ANGLE + (index * SWEEP) / 10
  return {
    from: pointOnCircle(CENTER, CENTER, RADIUS - STROKE / 2 - 9, angle),
    to: pointOnCircle(CENTER, CENTER, RADIUS - STROKE / 2 - (index % 5 ? 13 : 17), angle),
  }
})

const root = ref(null)
const dragValue = ref(null)
// Last value sent by keyboard, until the parent passes a new value back.
const keyValue = ref(null)
const shown = computed(() => dragValue.value ?? keyValue.value ?? clampBrightness(props.value))
watch(() => props.value, () => {
  keyValue.value = null
})
const fraction = computed(() => (shown.value - MIN) / (MAX - MIN))
const knob = computed(() => pointOnCircle(CENTER, CENTER, RADIUS, valueToAngle(shown.value)))
let pointerId = null

function measure(event, previous) {
  const rect = root.value.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  return {
    value: angleToValue(pointerAngle(event.clientX, event.clientY, cx, cy), previous),
    distance: Math.hypot(event.clientX - cx, event.clientY - cy) * (SIZE / rect.width),
  }
}

function onPointerDown(event) {
  if (event.button > 0) return
  const { value, distance } = measure(event, null)
  // Only the ring area starts a drag; the centre just shows the value.
  if (distance < RADIUS - STROKE * 2.2) return
  event.preventDefault()
  pointerId = event.pointerId
  root.value.setPointerCapture(pointerId)
  root.value.focus({ preventScroll: true })
  ticksStart()
  dragValue.value = value
  emit('update', value)
}

function onPointerMove(event) {
  if (event.pointerId !== pointerId) return
  const { value } = measure(event, dragValue.value)
  if (value === dragValue.value) return
  tickOnStep(dragValue.value, value, 5)
  dragValue.value = value
  emit('update', value)
}

function onPointerEnd(event) {
  if (event.pointerId !== pointerId) return
  pointerId = null
  ticksEnd()
  dragValue.value = null
}

function onKeydown(event) {
  const next = keyToValue(event.key, shown.value, { shift: event.shiftKey })
  if (next === null) return
  event.preventDefault()
  if (next === shown.value && props.on) return
  keyValue.value = next
  emit('update', next)
}
</script>

<template>
  <div
    ref="root"
    class="dial"
    :class="{ 'is-on': on, 'is-dragging': dragValue !== null }"
    :style="{ '--level': on ? 0.15 + 0.85 * fraction : 0 }"
    role="slider"
    tabindex="0"
    :aria-label="label"
    aria-valuemin="1"
    aria-valuemax="100"
    :aria-valuenow="shown"
    :aria-valuetext="on ? `${shown} %` : `${shown} %, isključeno`"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerEnd"
    @pointercancel="onPointerEnd"
    @lostpointercapture="onPointerEnd"
    @keydown="onKeydown"
  >
    <div class="dial-glow" aria-hidden="true"></div>
    <svg :viewBox="`0 0 ${SIZE} ${SIZE}`" aria-hidden="true">
      <defs>
        <linearGradient id="dial-gradient" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" class="dial-stop-from" />
          <stop offset="100%" class="dial-stop-to" />
        </linearGradient>
      </defs>
      <line
        v-for="(tick, index) in ticks"
        :key="index"
        class="dial-tick"
        :x1="tick.from.x" :y1="tick.from.y" :x2="tick.to.x" :y2="tick.to.y"
      />
      <path class="dial-track" :d="track" :stroke-width="STROKE" />
      <path
        class="dial-arc"
        :d="track"
        pathLength="100"
        :stroke-width="STROKE"
        :stroke-dasharray="`${fraction * 100} 200`"
      />
      <circle class="dial-knob" :cx="knob.x" :cy="knob.y" :r="STROKE / 2 + 4" />
    </svg>
    <div class="dial-center" aria-hidden="true">
      <span class="dial-number">{{ shown }}<small>%</small></span>
      <span class="dial-caption">{{ on ? 'Svjetlina' : 'Isključeno' }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { clampBrightness } from '../dial.js'
import { tap, tickOnStep, ticksEnd, ticksStart } from '../haptics.js'

const props = defineProps({
  light: { type: Object, required: true },
  syncing: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'dim', 'open'])

const DRAG_THRESHOLD = 8
const unavailable = computed(() => props.light.available === false)
const dimmable = computed(() => typeof props.light.brightness === 'number')
const brightness = computed(() => clampBrightness(props.light.brightness ?? 100))
const isOn = computed(() => props.light.on && !unavailable.value)
const dragValue = ref(null)
// How much of the tile is filled with warm light: 0 (off) … 1 (100 %).
const level = computed(() => {
  if (dragValue.value !== null) return dragValue.value / 100
  if (!isOn.value) return 0
  return dimmable.value ? brightness.value / 100 : 1
})
const stateText = computed(() => {
  if (unavailable.value) return 'Nedostupno'
  if (dragValue.value !== null) return `${dragValue.value} %`
  if (!props.light.on) return 'Isključeno'
  return dimmable.value ? `${brightness.value} %` : 'Uključeno'
})

let gesture = null
let suppressClick = false

// Swiping a dimmable tile sideways sets brightness relative to where it started;
// a vertical move is left to page scrolling (touch-action: pan-y).
function onPointerDown(event) {
  suppressClick = false
  if (!dimmable.value || unavailable.value || event.button > 0) return
  gesture = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    width: event.currentTarget.getBoundingClientRect().width,
    start: props.light.on ? brightness.value : 0,
    dragging: false,
  }
}

function onPointerMove(event) {
  if (!gesture || event.pointerId !== gesture.id) return
  const dx = event.clientX - gesture.x
  const dy = event.clientY - gesture.y
  if (!gesture.dragging) {
    if (Math.abs(dy) > DRAG_THRESHOLD && Math.abs(dy) > Math.abs(dx)) {
      gesture = null
      return
    }
    if (Math.abs(dx) < DRAG_THRESHOLD) return
    gesture.dragging = true
    event.currentTarget.setPointerCapture(event.pointerId)
    ticksStart()
  }
  const raw = gesture.start + (dx / gesture.width) * 100
  // Swiping left on a light that is off does not turn it on.
  if (!props.light.on && dragValue.value === null && raw < 1) return
  const value = clampBrightness(raw)
  if (value === dragValue.value) return
  tickOnStep(dragValue.value, value)
  dragValue.value = value
  emit('dim', value)
}

function onPointerEnd(event) {
  if (!gesture || event.pointerId !== gesture.id) return
  if (gesture.dragging) {
    suppressClick = true
    ticksEnd()
  }
  gesture = null
  dragValue.value = null
}

function onClick() {
  if (suppressClick) {
    suppressClick = false
    return
  }
  tap()
  emit('toggle', !props.light.on)
}
</script>

<template>
  <div
    class="light-tile"
    :class="{ 'is-on': isOn, 'is-unavailable': unavailable, 'is-dragging': dragValue !== null, 'is-dimmable': dimmable }"
    :style="{ '--level': level }"
  >
    <span class="tile-fill" aria-hidden="true"></span>
    <button
      type="button"
      role="switch"
      class="tile-main"
      :aria-checked="light.on ? 'true' : 'false'"
      :aria-label="light.name"
      :aria-describedby="`state-${light.id}`"
      :aria-busy="syncing ? 'true' : undefined"
      :disabled="unavailable"
      :title="unavailable ? 'Bridge prijavljuje da svjetlo nije dostupno.' : undefined"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerEnd"
      @pointercancel="onPointerEnd"
      @click="onClick"
    >
      <span class="bulb-icon" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <path d="M9 18h6M9.5 21h5M8 13.5a6 6 0 1 1 8 0c-1 .8-1.5 1.8-1.5 3h-5c0-1.2-.5-2.2-1.5-3Z" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <span class="tile-name">{{ light.name }}</span>
      <span :id="`state-${light.id}`" class="tile-state">{{ stateText }}</span>
    </button>
    <button
      v-if="dimmable && !unavailable"
      type="button"
      class="tile-dial-button"
      :aria-label="`Svjetlina: ${light.name}`"
      @click="emit('open')"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M6.3 17.7A8 8 0 1 1 17.7 17.7" stroke-linecap="round" />
        <circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none" />
      </svg>
    </button>
  </div>
</template>

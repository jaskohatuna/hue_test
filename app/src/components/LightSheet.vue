<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import BrightnessDial from './BrightnessDial.vue'
import { tap } from '../haptics.js'

const props = defineProps({
  light: { type: Object, default: null },
})
const emit = defineEmits(['close', 'set-on', 'brightness'])

const PRESETS = [10, 30, 50, 75, 100]
const CLOSE_DISTANCE = 90
const sheet = ref(null)
const dragOffset = ref(0)
let grab = null
let returnFocus = null

const brightness = computed(() => Math.max(1, Math.round(props.light?.brightness ?? 1)))
const stateText = computed(() => (props.light?.on ? `Uključeno · ${brightness.value} %` : 'Isključeno'))

function focusables() {
  return [...(sheet.value?.querySelectorAll('button, [tabindex="0"]') ?? [])].filter((element) => !element.disabled)
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  } else if (event.key === 'Tab') {
    // Keep keyboard focus inside the open sheet.
    const items = focusables()
    if (!items.length) return
    const first = items[0]
    const last = items.at(-1)
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }
}

function cleanup() {
  document.removeEventListener('keydown', onKeydown)
  document.body.classList.remove('sheet-open')
}

watch(() => props.light?.id ?? null, async (id, previous) => {
  if (id && !previous) {
    returnFocus = document.activeElement
    document.body.classList.add('sheet-open')
    document.addEventListener('keydown', onKeydown)
    await nextTick()
    sheet.value?.querySelector('.dial')?.focus({ preventScroll: true })
  } else if (!id && previous) {
    cleanup()
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true })
    returnFocus = null
  }
})
onBeforeUnmount(cleanup)

function setPower(on) {
  tap()
  emit('set-on', on)
}

// Swipe down on the handle or title to close, like a native bottom sheet.
function onGrabStart(event) {
  if (event.button > 0) return
  grab = { id: event.pointerId, y: event.clientY }
  event.currentTarget.setPointerCapture(event.pointerId)
}

function onGrabMove(event) {
  if (grab?.id !== event.pointerId) return
  dragOffset.value = Math.max(0, event.clientY - grab.y)
}

function onGrabEnd(event) {
  if (grab?.id !== event.pointerId) return
  const close = dragOffset.value > CLOSE_DISTANCE
  grab = null
  dragOffset.value = 0
  if (close) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet" :duration="320">
      <div v-if="light" class="sheet-backdrop" @click.self="emit('close')">
        <section
          ref="sheet"
          class="sheet"
          role="dialog"
          aria-modal="true"
          aria-labelledby="sheet-title"
          :class="{ 'is-dragging': dragOffset > 0 }"
          :style="dragOffset ? { transform: `translateY(${dragOffset}px)` } : undefined"
        >
          <div
            class="sheet-grab"
            aria-hidden="true"
            @pointerdown="onGrabStart" @pointermove="onGrabMove" @pointerup="onGrabEnd" @pointercancel="onGrabEnd"
          >
            <span class="sheet-handle"></span>
          </div>

          <header class="sheet-header">
            <div
              class="sheet-title"
              @pointerdown="onGrabStart" @pointermove="onGrabMove" @pointerup="onGrabEnd" @pointercancel="onGrabEnd"
            >
              <h2 id="sheet-title">{{ light.name }}</h2>
              <p :class="{ 'is-on': light.on }">{{ stateText }}</p>
            </div>
            <button type="button" class="icon-button sheet-close" aria-label="Zatvori" @click="emit('close')">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
              </svg>
            </button>
          </header>

          <BrightnessDial
            :value="brightness"
            :on="light.on"
            :label="`Svjetlina: ${light.name}`"
            @update="(value) => emit('brightness', value)"
          />

          <div class="preset-row" role="group" aria-label="Brzi izbor svjetline">
            <button
              v-for="preset in PRESETS"
              :key="preset"
              type="button"
              class="preset"
              :class="{ 'is-active': light.on && brightness === preset }"
              :aria-pressed="light.on && brightness === preset ? 'true' : 'false'"
              @click="emit('brightness', preset)"
            >
              {{ preset }} %
            </button>
          </div>

          <button
            type="button"
            class="power-button"
            :class="{ 'is-on': light.on }"
            :aria-pressed="light.on ? 'true' : 'false'"
            @click="setPower(!light.on)"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 3v8" stroke-linecap="round" />
              <path d="M7.05 6.6a7 7 0 1 0 9.9 0" stroke-linecap="round" />
            </svg>
            {{ light.on ? 'Ugasi' : 'Upali' }}
          </button>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

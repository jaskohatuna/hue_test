<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { App as NativeApp } from '@capacitor/app'
import BridgeSetup from './components/BridgeSetup.vue'
import LightSheet from './components/LightSheet.vue'
import LightTile from './components/LightTile.vue'
import ServerSetup from './components/ServerSetup.vue'
import SettingsScreen from './components/SettingsScreen.vue'
import { useHue } from './useHue.js'

const {
  screen, serverUrl, setup, configured, connected, busy,
  checkingServer, serverError, savingSetup, setupError,
  lights, syncingIds, loading, refreshing, error, liveState, liveDetail,
  boot, connectServer, connectBridge, refreshLights, setLightOn, setBrightness, navigate,
  pause, resume, dispose,
} = useHue()

const sheetLightId = ref(null)
// The sheet closes by itself when its light disappears or becomes unreachable.
const sheetLight = computed(() => {
  const light = lights.value.find((item) => item.id === sheetLightId.value)
  return light && light.available !== false && typeof light.brightness === 'number' ? light : null
})
watch(sheetLight, (light) => {
  if (!light) sheetLightId.value = null
})
watch(screen, () => {
  sheetLightId.value = null
})

const parentScreen = computed(() => {
  if (screen.value === 'settings') return 'lights'
  if (screen.value === 'server' && connected.value) return 'settings'
  if (screen.value === 'bridge' && configured.value) return 'settings'
  return null
})
const title = computed(() => {
  if (screen.value === 'lights' || !parentScreen.value) return 'Moja svjetla'
  return 'Postavke'
})
const onCount = computed(() => lights.value.filter((light) => light.on && light.available !== false).length)
const hasDimmable = computed(() => lights.value.some((light) => typeof light.brightness === 'number' && light.available !== false))
// Warm glow behind the title grows with the share of lights that are on.
const ambient = computed(() => (screen.value === 'lights' && lights.value.length ? onCount.value / lights.value.length : 0))

function goBack() {
  if (parentScreen.value) navigate(parentScreen.value)
}

function clearSetupError() {
  setupError.value = ''
}

function onBackButton() {
  if (sheetLightId.value) sheetLightId.value = null
  else if (parentScreen.value) goBack()
  else NativeApp.exitApp()
}

let listeners = []
onMounted(async () => {
  boot()
  try {
    listeners = await Promise.all([
      // On the web this follows the tab's visibility.
      NativeApp.addListener('appStateChange', ({ isActive }) => (isActive ? resume() : pause())),
      // Android back button: close the sheet, return to the previous screen, or exit.
      NativeApp.addListener('backButton', onBackButton),
    ])
  } catch {
    listeners = []
  }
})
onUnmounted(() => {
  dispose()
  for (const listener of listeners) listener.remove()
})
</script>

<template>
  <div class="app" :style="{ '--ambient': ambient }">
    <header class="app-bar">
      <button v-if="parentScreen" type="button" class="icon-button back-button" :disabled="busy" aria-label="Natrag" @click="goBack">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <path d="M15 5l-7 7 7 7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <p class="eyebrow"><span class="brand-mark" aria-hidden="true"></span>PHILIPS HUE · LOKALNO</p>
      <div v-if="screen === 'lights' && configured" class="app-bar-actions">
        <button type="button" class="icon-button" :disabled="busy" :aria-label="refreshing ? 'Osvježavanje…' : 'Osvježi'" @click="refreshLights()">
          <svg :class="{ spinning: refreshing }" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path d="M20 7v5h-5M4 17v-5h5" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M6.1 7a7 7 0 0 1 11.6-.8L20 9M4 15l2.3 2.8A7 7 0 0 0 17.9 17" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button type="button" class="icon-button" :disabled="busy" aria-label="Postavke" @click="navigate('settings')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path d="M4 7h10M18 7h2M4 17h2M10 17h10" stroke-linecap="round" />
            <circle cx="16" cy="7" r="2" />
            <circle cx="8" cy="17" r="2" />
          </svg>
        </button>
      </div>
    </header>

    <main class="page">
      <h1>{{ title }}</h1>
      <div v-if="screen === 'lights'" class="summary-row">
        <p class="intro">{{ lights.length ? `${onCount} od ${lights.length} uključeno` : 'Upali, ugasi i prigušaj svoja svjetla.' }}</p>
        <p class="live-chip" :class="{ 'is-live': liveState === 'live' }" role="status">
          <span aria-hidden="true"></span>{{ liveState === 'live' ? 'Uživo' : liveDetail }}
        </p>
      </div>
      <p v-else-if="!parentScreen" class="intro">Upali, ugasi i prigušaj svoja svjetla.</p>

      <p v-if="screen === 'boot'" class="empty-message" role="status">Učitavanje…</p>

      <ServerSetup
        v-else-if="screen === 'server'"
        :server-url="serverUrl"
        :error="serverError"
        :checking="checkingServer"
        :can-cancel="connected"
        @connect="connectServer"
        @cancel="navigate('settings')"
      />

      <BridgeSetup
        v-else-if="screen === 'bridge'"
        :bridge-ip="setup?.bridge_ip ?? ''"
        :configured="configured"
        :error="setupError"
        :saving="savingSetup"
        :disabled="busy"
        @submit="connectBridge"
        @cancel="navigate('settings')"
        @clear-error="clearSetupError"
      />

      <SettingsScreen
        v-else-if="screen === 'settings'"
        :server-url="serverUrl"
        :bridge-ip="setup?.bridge_ip ?? ''"
        :configured="configured"
        :live-state="liveState"
        :live-detail="liveDetail"
        :disabled="busy"
        @change-server="navigate('server')"
        @change-bridge="navigate('bridge')"
      />

      <template v-else>
        <div v-if="error" class="error-message" role="alert">
          <p>{{ error }}</p>
          <button type="button" :disabled="busy" @click="refreshLights()">Pokušaj ponovo</button>
        </div>

        <p v-if="loading" class="empty-message" role="status">Učitavanje svjetala…</p>
        <p v-else-if="!lights.length && !error" class="empty-message">Na Bridgeu nema povezanih svjetala.</p>

        <section v-if="lights.length" class="light-grid" aria-label="Povezana svjetla">
          <LightTile
            v-for="light in lights"
            :key="light.id"
            :light="light"
            :syncing="syncingIds.has(light.id)"
            @toggle="(on) => setLightOn(light, on)"
            @dim="(value) => setBrightness(light, value)"
            @open="sheetLightId = light.id"
          />
        </section>
        <p v-if="hasDimmable" class="gesture-hint">Dodirni za paljenje · prevuci lijevo-desno za svjetlinu</p>
      </template>

      <p class="footer-note">Tvoja svjetla. Tvoja kućna mreža.</p>
    </main>

    <LightSheet
      :light="sheetLight"
      @close="sheetLightId = null"
      @set-on="(on) => sheetLight && setLightOn(sheetLight, on)"
      @brightness="(value) => sheetLight && setBrightness(sheetLight, value)"
    />
  </div>
</template>

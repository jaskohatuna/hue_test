<script setup>
import { displayServer } from '../server.js'

defineProps({
  serverUrl: { type: String, required: true },
  bridgeIp: { type: String, default: '' },
  configured: { type: Boolean, default: false },
  liveState: { type: String, required: true },
  liveDetail: { type: String, required: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['change-server', 'change-bridge'])
</script>

<template>
  <section class="settings" aria-labelledby="settings-title">
    <h2 id="settings-title" class="visually-hidden">Postavke</h2>
    <ul class="card settings-list">
      <li>
        <div>
          <p class="settings-label">Server</p>
          <p class="settings-value">{{ displayServer(serverUrl) }}</p>
        </div>
        <button type="button" class="link-button" :disabled="disabled" @click="emit('change-server')">Promijeni</button>
      </li>
      <li>
        <div>
          <p class="settings-label">Hue Bridge</p>
          <p class="settings-value">{{ configured ? bridgeIp : 'Nije povezan' }}</p>
        </div>
        <button type="button" class="link-button" :disabled="disabled" @click="emit('change-bridge')">Promijeni</button>
      </li>
      <li>
        <div>
          <p class="settings-label">Praćenje promjena</p>
          <p class="live-status" :class="{ 'is-live': liveState === 'live' }"><span aria-hidden="true"></span>{{ liveDetail }}</p>
        </div>
      </li>
    </ul>
    <p class="settings-note">Server čuva API ključ Bridgea. Telefon pamti samo adresu servera.</p>
  </section>
</template>

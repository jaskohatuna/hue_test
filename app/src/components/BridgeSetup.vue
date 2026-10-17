<script setup>
import { ref } from 'vue'

const props = defineProps({
  bridgeIp: { type: String, default: '' },
  configured: { type: Boolean, default: false },
  error: { type: String, default: '' },
  saving: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['submit', 'cancel', 'clear-error'])

const ip = ref(props.bridgeIp)
const mode = ref('pair')
const appKey = ref('')

function changeMode() {
  appKey.value = ''
  emit('clear-error')
}

function submit() {
  const key = mode.value === 'key' ? appKey.value.trim() : null
  // The key is only sent to the backend, never kept in the form.
  appKey.value = ''
  emit('submit', { ip: ip.value.trim(), mode: mode.value, key })
}
</script>

<template>
  <form class="card setup-card" novalidate autocomplete="off" :aria-busy="saving" @submit.prevent="submit">
    <h2>{{ configured ? 'Postavke Bridgea' : 'Poveži Hue Bridge' }}</h2>
    <p class="setup-intro">Unesi IP adresu Bridgea u svojoj kućnoj mreži.</p>

    <fieldset :disabled="disabled">
      <label class="field-label" for="bridge-ip">IP adresa Bridgea</label>
      <input
        id="bridge-ip"
        v-model="ip"
        class="text-input"
        type="text"
        inputmode="url"
        placeholder="192.168.1.100"
        autocomplete="off"
        autocapitalize="off"
        autocorrect="off"
        spellcheck="false"
        required
        :aria-invalid="error ? 'true' : undefined"
      />

      <p id="connection-label" class="field-label mode-label">Način povezivanja</p>
      <div class="connection-modes" role="radiogroup" aria-labelledby="connection-label">
        <label :class="{ selected: mode === 'pair' }">
          <input v-model="mode" type="radio" name="connection-mode" value="pair" @change="changeMode" />
          Dugme na Bridgeu
        </label>
        <label :class="{ selected: mode === 'key' }">
          <input v-model="mode" type="radio" name="connection-mode" value="key" @change="changeMode" />
          Imam API ključ
        </label>
      </div>

      <p v-if="mode === 'pair'" class="pairing-hint">Pritisni fizičko dugme na Hue Bridgeu, a zatim dodirni <strong>Poveži Bridge</strong>.</p>
      <div v-else class="key-field">
        <label class="field-label" for="app-key">API ključ</label>
        <input id="app-key" v-model="appKey" class="text-input" type="password" autocomplete="new-password" autocapitalize="off" spellcheck="false" required aria-describedby="key-hint" />
        <p id="key-hint" class="field-hint">Ključ se šalje samo tvom serveru i ne čuva se na telefonu.</p>
      </div>

      <p v-if="error" class="form-error" role="alert">{{ error }}</p>

      <div class="form-actions">
        <button type="submit" class="primary-button">{{ saving ? 'Povezivanje…' : 'Poveži Bridge' }}</button>
        <button v-if="configured" type="button" class="secondary-button" @click="emit('cancel')">Odustani</button>
      </div>
    </fieldset>
  </form>
</template>

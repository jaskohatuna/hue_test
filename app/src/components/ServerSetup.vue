<script setup>
import { ref } from 'vue'
import { displayServer } from '../server.js'

const props = defineProps({
  serverUrl: { type: String, default: '' },
  error: { type: String, default: '' },
  checking: { type: Boolean, default: false },
  canCancel: { type: Boolean, default: false },
})
const emit = defineEmits(['connect', 'cancel'])

const address = ref(displayServer(props.serverUrl))
</script>

<template>
  <form class="card setup-card" novalidate autocomplete="off" :aria-busy="checking" @submit.prevent="emit('connect', address)">
    <h2>{{ canCancel ? 'Promijeni server' : 'Poveži se sa serverom' }}</h2>
    <p class="setup-intro">Aplikacija upravlja svjetlima preko Hue servera koji radi na računaru u tvojoj kućnoj mreži.</p>

    <fieldset :disabled="checking">
      <label class="field-label" for="server-url">Adresa servera</label>
      <input
        id="server-url"
        v-model="address"
        class="text-input"
        type="text"
        inputmode="url"
        enterkeyhint="go"
        placeholder="192.168.1.20:8000"
        autocomplete="off"
        autocapitalize="off"
        autocorrect="off"
        spellcheck="false"
        required
        aria-describedby="server-hint"
        :aria-invalid="error ? 'true' : undefined"
      />
      <p id="server-hint" class="field-hint">Lokalna IP adresa računara. Ako ne upišeš port, koristi se 8000.</p>

      <p v-if="error" class="form-error" role="alert">{{ error }}</p>

      <div class="form-actions">
        <button type="submit" class="primary-button">{{ checking ? 'Provjera…' : 'Poveži' }}</button>
        <button v-if="canCancel" type="button" class="secondary-button" @click="emit('cancel')">Odustani</button>
      </div>
    </fieldset>
  </form>
</template>

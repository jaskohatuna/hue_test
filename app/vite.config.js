import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// No /api proxy: like the native app, the page calls the backend address
// entered on the first screen (CORS is allowed for localhost:5173).
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
})

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  // Relative asset paths so the same build loads from app://keyfinder (desktop) or the engine's web server.
  base: './',
  plugins: [react()],
  server: {
    // npm run dev:web: the engine runs as a web server on :8000.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})

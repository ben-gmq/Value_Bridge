import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev only: proxy the API so the browser talks to one origin. In Azure the Static Web App
// links the backend and sets the CSP headers (§14.5, §15.2 — staticwebapp.config.json).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: { '/api': 'http://localhost:8100', '/auth': 'http://localhost:8100' },
  },
});

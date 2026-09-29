import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev only: proxy the API so the browser talks to one origin. In Azure the Static Web App
// links the backend and sets the CSP headers (§14.5, §15.2 — staticwebapp.config.json).
// Defaults are VB's ports (8100 / 5180). A parallel slice session overrides both, e.g.
// VB_API_PORT=8111 VB_WEB_PORT=5181 npm run dev, so sessions never share a server.
const api = `http://localhost:${process.env.VB_API_PORT ?? 8100}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VB_WEB_PORT ?? 5180),
    strictPort: true,
    proxy: { '/api': api, '/auth': api },
  },
});

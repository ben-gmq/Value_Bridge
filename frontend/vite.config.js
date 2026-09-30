import { realpathSync } from 'node:fs';
import { defineConfig, searchForWorkspaceRoot } from 'vite';
import react from '@vitejs/plugin-react';

// Dev only: proxy the API so the browser talks to one origin. In Azure the Static Web App
// links the backend and sets the CSP headers (§14.5, §15.2 — staticwebapp.config.json).
// Defaults are VB's ports (8100 / 5180). A parallel slice session overrides both, e.g.
// VB_API_PORT=8111 VB_WEB_PORT=5181 npm run dev, so sessions never share a server.
const api = `http://localhost:${process.env.VB_API_PORT ?? 8100}`;
const port = Number(process.env.VB_WEB_PORT ?? 5180);
// A slice worktree symlinks node_modules to the main checkout's, so two dev servers would share
// one pre-bundle cache (each re-optimising under the other: "504 Outdated Optimize Dep"), and
// files resolved through the link sit outside this root (fonts 403). One cache per port, and
// the real node_modules folder is allowed.
let modules = 'node_modules';
try { modules = realpathSync('node_modules'); } catch { /* not installed yet */ }

export default defineConfig({
  plugins: [react()],
  cacheDir: `node_modules/.vite/${port}`,
  server: {
    port,
    strictPort: true,
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), modules] },
    proxy: { '/api': api, '/auth': api },
  },
});

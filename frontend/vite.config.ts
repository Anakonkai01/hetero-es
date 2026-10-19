import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Static assets only. `public/downloads` holds links to installers for the lab manager and must never be copied into a build.
  publicDir: 'static',
  server: {
    host: process.env.HETEROES_UI_HOST ?? '127.0.0.1',
    port: Number(process.env.HETEROES_UI_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': `http://${process.env.HETEROES_BACKEND_HOST ?? '127.0.0.1'}:${process.env.HETEROES_BACKEND_PORT ?? 8000}`,
    },
  },
});

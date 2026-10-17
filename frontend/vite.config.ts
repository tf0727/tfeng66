import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8888', changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, '') } } },
  build: {
    rollupOptions: {
      input: { consultation: 'index.html', admin: 'admin.html' },
    },
  },
})

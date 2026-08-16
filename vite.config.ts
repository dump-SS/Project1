import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 5173,
      open: true,
      // 后端联调时把 VITE_API_PROXY_TARGET 指向后端地址即可，
      // 前端代码里统一走 /api/v1 相对路径，不需要改任何 service 文件。
      proxy: env.VITE_API_PROXY_TARGET
        ? {
            '/api': {
              target: env.VITE_API_PROXY_TARGET,
              changeOrigin: true,
            },
          }
        : undefined,
    },
  };
});

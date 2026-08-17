import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  // 认证接口（登录/注册/验证码）由 ../mock-server 提供（端口 4000，sessionCookie 体系），
  // 业务接口由 backend FastAPI 提供（端口 8000）。代理按路径分流：
  //   /api/v1/auth/*  -> mock-server
  //   其余 /api/*     -> FastAPI backend
  const authTarget = env.VITE_API_AUTH_PROXY_TARGET || 'http://localhost:4000';
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      host: true,
      port: 5173,
      proxy: {
        '/api/v1/auth': {
          target: authTarget,
          changeOrigin: true,
        },
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

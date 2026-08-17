import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  // 双后端联调拓扑（auth 迁入 Python 后端前的过渡方案）：
  //   /api/v1/auth/*  → mock-server（登录/注册/验证码/会话，Node + SQLite + SMTP）
  //   其余 /api/*     → Python FastAPI（契约业务接口 + state_engine + AI 链路）
  // 两者都在 /api/v1 前缀下按 openapi.yaml 服务，Cookie（sid）跨后端共用
  // —— 登录在 mock-server 签发的 HttpOnly session，Python 后端的
  // current_user 暂为桩（不校验），所以业务接口实际不依赖这个 Cookie。
  // 等把 /auth/* 路由迁进 FastAPI 后，这里可退回单一 target。
  const authTarget = env.VITE_AUTH_PROXY_TARGET || 'http://localhost:4000';
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
        // 注意顺序：vite 按声明顺序匹配，更具体的 auth 前缀必须放前面
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

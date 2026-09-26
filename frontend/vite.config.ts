import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  // 单后端拓扑：auth 迁移完成后所有 /api/* 统一指向 Python FastAPI。
  // 业务接口 + /auth/* + state_engine + AI 链路全部在 8000 端口。
  // mock-server 已退役，仅保留作历史参考。
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

  return {
    // plugins 见文件底部数组（react + dev-login middleware）
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      host: true,
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          // 落地页重依赖（ogl，来自 React Bits Grainient / Prism；motion，来自 VariableProximity）
          // 单独成 chunk，只被落地页动态 import 引用，保证不进主包（dev-spec §2.3）。
          // TextType 已适配为 CSS 光标，gsap 未引入。
          manualChunks(id: string) {
            if (/[\\/]node_modules[\\/](gsap|ogl|motion)[\\/]/.test(id)) return 'landing-gfx';
            return undefined;
          },
        },
      },
    },
    // Tailwind v4：仅为落地页引入（utilities 层，preflight 不进——页面级 landing.css 只
    // @import "tailwindcss/utilities"，避免重置全站基础样式）。现有 CSS Modules 不动。
    // dev-only:GET /dev-login 一键登录本地演示账户(demo@epochx.local),
    // 写入 7 天 HttpOnly cookie 后 302 到目标页,跳过登录页。生产构建不生效。
    plugins: [
      react(),
      tailwindcss(),
      {
        name: 'dev-login',
        configureServer(server) {
          server.middlewares.use('/dev-login', async (req, res) => {
            try {
              const resp = await fetch(`${apiTarget}/api/v1/auth/login-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: 'demo@epochx.local', password: 'Demo@2026' }),
              });
              const cookie = resp.headers.get('set-cookie');
              if (!resp.ok || !cookie) throw new Error(`login failed: ${resp.status}`);
              res.setHeader('set-cookie', cookie);
              const to = new URL(req.url ?? '/', 'http://localhost').searchParams.get('to') || '/chat';
              res.writeHead(302, { Location: to });
              res.end();
            } catch (e) {
              res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
              res.end(`dev-login 失败(后端 ${apiTarget} 是否已启动?): ${e}`);
            }
          });
        },
      },
    ],
  };
});

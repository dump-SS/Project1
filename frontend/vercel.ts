import { routes, type VercelConfig } from '@vercel/config/v1';

/**
 * Vercel 侧部署配置（程序化 / IaC）。
 *
 * 为什么用 vercel.ts 而不是 vercel.json：Skyer 2026-10-05 定的前后端分离形态要求
 * Vercel 侧走 IaC，与本仓库 Railway 侧的 .railway/railway.py 同一思路。
 * 官方硬约束：vercel.ts 与 vercel.json 只能存在一个
 * （"Use only one configuration file: vercel.ts or vercel.json."）——
 * 所以仓库里绝不能同时出现，本文件与 vercel.json 互斥。
 *
 * 本文件位于 frontend/ 而非仓库根，因为 Vercel 项目的 Root Directory 设为 frontend；
 * 配置文件要放在 Root Directory 下（官方 monorepo 文档的用法是
 * "a vercel.json configuration file at the root of the app"，示例 apps/frontend/vercel.json）。
 *
 * 未提交，等 lead-2 review。
 */

export const config: VercelConfig = {
  /**
   * SPA history 回退。
   *
   * 前端是 react-router v6 的 SPA，路由在 src/App.jsx（22 处 path= 声明）。
   * 磁盘上只有 index.html 与 /assets/*，像 /study-timer、/goals、/chat 这些路径
   * 没有对应文件。Vercel 默认「拿路径找同名静态文件，找不到就 404，不会回退 index.html」，
   * 于是深链（刷新 / 外部分享 / 收藏夹）直接 404，而站内点击不受影响——很难漏测。
   *
   * 一条 /(.*) 就够，不需要为 /assets 单独开排除规则：rewrites 在文件系统检查
   * **之后**才应用（官方原文 "precedence is given to the filesystem prior to
   * rewrites being applied"），所以 /assets/index-*.js 这类真实存在的文件先被
   * 文件系统命中，永远走不到这条 rewrite。
   *
   * 刻意**不**把 /api 也 rewrite 进来：分离部署下前端基址是绝对地址
   * https://api.epochx.net/api/v1，浏览器直连 Railway，根本不经过 Vercel，
   * 加了是永不触发的死规则。详见 VERCEL_DEPLOY.md §3。
   *
   * 若将来真要把 /api 走 Vercel 代理，负向断言必须包在 capture group 里
   * （官方原文 "With rewrites, the regex needs to be wrapped in a capture group"），
   * 正确写法是 '/((?!api/).*)'，不是 '/(?!api/)'。配方见 VERCEL_DEPLOY.md §3。
   */
  rewrites: [routes.rewrite('/(.*)', '/index.html')],
};

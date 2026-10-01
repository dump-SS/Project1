/**
 * 监护人授权页（PRD 8.1 合规底线）—— **已归位，本路由只做重定向**。
 *
 * D41 定的是「入口两处、页面一处」：
 *   ① 激活式建档流程（未满 14 岁强制走到）；
 *   ② 设置 → 授权与隐私（常驻）。
 * 两处渲染的都是 `components/GuardianAuthorizationPanel`（状态卡 + 提交 + 确认链接 + 撤销）。
 *
 * 旧的独立页 `/guardian-auth` 曾是第三份实现（各自读状态、各自提交），
 * 三份 UI 迟早漂移——这里保留路由做兼容跳转（老书签、旧邮件链接仍能用），
 * 页面本体不再单独维护。
 */
import { Navigate } from 'react-router-dom'

export default function GuardianAuthPage() {
  return <Navigate to="/settings?tab=privacy" replace />
}

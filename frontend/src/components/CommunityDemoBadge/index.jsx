/**
 * 板块三演示数据水印（PRD 计划书 §7 3-A）
 *
 * 包在 /community 两个页面的路由外层，固定右下角「演示数据」水印，
 * 避免前端 localStorage 模拟的群体对比被误认为真实多用户数据。
 */
import React from 'react';

export default function CommunityDemoBadge({ children }) {
  return (
    <div style={{ position: 'relative', minHeight: '100vh' }}>
      {children}
      <div
        aria-label="演示数据"
        style={{
          position: 'fixed',
          right: 16,
          bottom: 16,
          zIndex: 9999,
          pointerEvents: 'none',
          padding: '6px 14px',
          borderRadius: 8,
          background: 'rgba(0,0,0,0.55)',
          color: '#fff',
          fontSize: 13,
          letterSpacing: 1,
        }}
      >
        演示数据 · 非真实群体
      </div>
    </div>
  );
}

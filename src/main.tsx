import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import App from './App';
import './styles/global.css';

// 日历里的「星期一」等中文表述依赖这个 locale
dayjs.locale('zh-cn');

const container = document.getElementById('root');
if (!container) {
  throw new Error('找不到 #root 挂载节点');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

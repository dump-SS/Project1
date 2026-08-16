/**
 * 应用根组件：注入 antd 主题令牌与中文 locale。
 * MVP 只有个人数据一个页面，暂不引入路由；后续加页面时在这里换成 react-router。
 */

import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import PersonalData from '@/pages/PersonalData';
import { antdThemeToken } from '@/styles/theme';

function App() {
  return (
    <ConfigProvider locale={zhCN} theme={{ token: antdThemeToken }}>
      <PersonalData />
    </ConfigProvider>
  );
}

export default App;

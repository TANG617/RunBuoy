import path from 'node:path';

import { defineConfig } from '@rspress/core';

export default defineConfig({
  root: path.join(__dirname, 'docs'),
  title: 'RunBuoy',
  description: '将 Mac 和 Linux 上的长任务状态，以只读方式送到 iPhone。',
  icon: '/brand/runbuoy-mark.svg',
  logo: {
    light: '/brand/runbuoy-mark.svg',
    dark: '/brand/runbuoy-mark-dark.svg',
  },
  logoText: 'RunBuoy',
  lang: 'zh',
  base: '/',
  siteOrigin: 'https://www.runbuoy.cloud',
  globalStyles: path.join(__dirname, 'styles/index.css'),
  themeConfig: {
    lastUpdated: true,
    socialLinks: [
      {
        icon: 'github',
        mode: 'link',
        content: 'https://github.com/TANG617/RunBuoy',
      },
    ],
  },
});

import path from 'node:path';

import { defineConfig } from '@rspress/core';

export default defineConfig({
  root: path.join(__dirname, 'docs'),
  title: 'RunBuoy',
  description: '在 iPhone 上随时掌握 Mac 和 Linux 长任务的进度与结果。',
  icon: '/brand/runbuoy-icon-light.png',
  logo: {
    light: '/brand/runbuoy-icon-light.png',
    dark: '/brand/runbuoy-icon-dark.png',
  },
  logoText: 'RunBuoy',
  lang: 'zh',
  locales: [
    {
      lang: 'zh',
      label: '简体中文',
      title: 'RunBuoy',
      description: '在 iPhone 上随时掌握 Mac 和 Linux 长任务的进度与结果。',
    },
    {
      lang: 'en',
      label: 'English',
      title: 'RunBuoy',
      description: 'Keep long-running tasks in sight on iPhone.',
    },
  ],
  base: '/',
  siteOrigin: 'https://www.runbuoy.cloud',
  globalStyles: path.join(__dirname, 'styles/index.css'),
  head: [
    [
      'link',
      {
        rel: 'icon',
        href: '/brand/runbuoy-icon-light.png',
        media: '(prefers-color-scheme: light)',
      },
    ],
    [
      'link',
      {
        rel: 'icon',
        href: '/brand/runbuoy-icon-dark.png',
        media: '(prefers-color-scheme: dark)',
      },
    ],
    [
      'link',
      {
        rel: 'apple-touch-icon',
        href: '/brand/apple-touch-icon.png',
      },
    ],
    [
      'meta',
      {
        property: 'og:image',
        content: 'https://www.runbuoy.cloud/og.png',
      },
    ],
    [
      'meta',
      {
        property: 'og:image:width',
        content: '1200',
      },
    ],
    [
      'meta',
      {
        property: 'og:image:height',
        content: '630',
      },
    ],
    [
      'meta',
      {
        name: 'twitter:card',
        content: 'summary_large_image',
      },
    ],
  ],
  languageParity: {
    enabled: true,
  },
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

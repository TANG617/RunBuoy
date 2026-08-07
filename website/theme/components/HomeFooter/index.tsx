import { useLang } from '@rspress/core/runtime';
import { Link } from '@rspress/core/theme-original';
import { GithubLogo } from '@phosphor-icons/react';

import { localizeHref } from '../../utils/localizeHref';
import './index.css';

const copy = {
  zh: {
    tagline: '让 Mac 与 Linux 长任务的进度，始终在手边。',
    product: '产品',
    resources: '资源',
    quickStart: '快速开始',
    download: '下载状态',
    docs: '使用文档',
    privacy: '隐私',
    security: '安全',
    status: '服务状态',
    support: '支持',
    selfHosting: '自托管',
    github: 'GitHub',
    copyright: '© 2026 RunBuoy。开源、可审计，并以隐私为先。',
  },
  en: {
    tagline: 'Keep long-running work on Mac and Linux within reach.',
    product: 'Product',
    resources: 'Resources',
    quickStart: 'Quick Start',
    download: 'Availability',
    docs: 'Docs',
    privacy: 'Privacy',
    security: 'Security',
    status: 'Service status',
    support: 'Support',
    selfHosting: 'Self-hosting',
    github: 'GitHub',
    copyright: '© 2026 RunBuoy. Open source, auditable, and privacy-first.',
  },
} as const;

function HomeFooter() {
  const lang = useLang();
  const value = lang.startsWith('en') ? copy.en : copy.zh;

  return (
    <footer className="runbuoy-footer">
      <div className="runbuoy-footer__inner">
        <div className="runbuoy-footer__brand">
          <Link href={localizeHref('/', lang)} aria-label="RunBuoy">
            <span className="runbuoy-footer__icon" aria-hidden="true">
              <img
                className="runbuoy-footer__icon-light"
                src="/brand/runbuoy-icon-light.png"
                width="36"
                height="36"
                alt=""
              />
              <img
                className="runbuoy-footer__icon-dark"
                src="/brand/runbuoy-icon-dark.png"
                width="36"
                height="36"
                alt=""
              />
            </span>
            <strong>RunBuoy</strong>
          </Link>
          <p>{value.tagline}</p>
        </div>

        <nav className="runbuoy-footer__links" aria-label="Footer">
          <div>
            <strong>{value.product}</strong>
            <Link href={localizeHref('/guide/', lang)}>{value.quickStart}</Link>
            <Link href={localizeHref('/download', lang)}>{value.download}</Link>
            <Link href={localizeHref('/privacy', lang)}>{value.privacy}</Link>
            <Link href={localizeHref('/status', lang)}>{value.status}</Link>
          </div>
          <div>
            <strong>{value.resources}</strong>
            <Link href={localizeHref('/docs/', lang)}>{value.docs}</Link>
            <Link href={localizeHref('/security', lang)}>{value.security}</Link>
            <Link href={localizeHref('/support', lang)}>{value.support}</Link>
            <Link href={localizeHref('/self-hosting', lang)}>
              {value.selfHosting}
            </Link>
            <Link href="https://github.com/TANG617/RunBuoy">
              <GithubLogo size={17} weight="bold" aria-hidden="true" />
              {value.github}
            </Link>
          </div>
        </nav>
      </div>
      <p className="runbuoy-footer__copyright">{value.copyright}</p>
    </footer>
  );
}

export { HomeFooter };

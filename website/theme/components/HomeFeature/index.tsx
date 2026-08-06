import type { Feature } from '@rspress/core';
import { useFrontmatter, useLang } from '@rspress/core/runtime';
import { Link, renderHtmlOrText } from '@rspress/core/theme-original';
import {
  ArrowRight,
  Pulse,
  Robot,
  ShieldCheck,
} from '@phosphor-icons/react';
import type { Icon } from '@phosphor-icons/react';

import { localizeHref } from '../../utils/localizeHref';
import './index.css';

function getGridClass(feature: Feature): string {
  return `runbuoy-home-feature__item--span-${feature.span ?? 4}`;
}

function HomeFeatureItem({ feature }: { feature: Feature }) {
  const lang = useLang();
  const { title, details, link } = feature;
  const Icon: Icon = link?.includes('privacy')
    ? ShieldCheck
    : link?.includes('agent')
      ? Robot
      : Pulse;
  const content = (
    <article className="runbuoy-home-feature__card">
      <div className="runbuoy-home-feature__icon" aria-hidden="true">
        <Icon size={24} weight="duotone" />
      </div>
      <h3 className="runbuoy-home-feature__title">{title}</h3>
      <p
        className="runbuoy-home-feature__detail"
        {...renderHtmlOrText(details)}
      />
      {link && (
        <span className="runbuoy-home-feature__more" aria-hidden="true">
          <ArrowRight size={18} weight="bold" />
        </span>
      )}
    </article>
  );

  return (
    <div className={`runbuoy-home-feature__item ${getGridClass(feature)}`}>
      {link ? (
        <Link
          href={localizeHref(link, lang)}
          className="runbuoy-home-feature-link"
        >
          {content}
        </Link>
      ) : (
        content
      )}
    </div>
  );
}

function HomeFeature({ features: featuresProp }: { features?: Feature[] }) {
  const { frontmatter } = useFrontmatter();
  const lang = useLang();
  const features = featuresProp ?? frontmatter?.features;
  const zh = lang.startsWith('zh');

  return (
    <section
      className="runbuoy-home-feature"
      aria-labelledby="runbuoy-home-feature-heading"
    >
      <header className="runbuoy-home-feature__header">
        <p className="runbuoy-section-eyebrow">
          {zh ? '为持续运行的工作而生' : 'Built for work that keeps running'}
        </p>
        <h2 id="runbuoy-home-feature-heading">
          {zh ? '重要状态，一眼看清' : 'The important status, at a glance'}
        </h2>
        <p>
          {zh
            ? '把需要关注的阶段、进度和结果送到手边，同时守住本地数据边界。'
            : 'Bring phases, progress, and results within reach while keeping local data boundaries intact.'}
        </p>
      </header>
      <div className="runbuoy-home-feature__grid">
        {features?.map(feature => (
          <HomeFeatureItem key={feature.title} feature={feature} />
        ))}
      </div>
    </section>
  );
}

export { HomeFeature };

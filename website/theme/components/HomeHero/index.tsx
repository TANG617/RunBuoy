import type { FrontMatterMeta } from '@rspress/core';
import { useFrontmatter, useLang } from '@rspress/core/runtime';
import { Button, Link, renderHtmlOrText } from '@rspress/core/theme-original';
import {
  AppStoreLogo,
  MagicWand,
  TerminalWindow,
  Waveform,
} from '@phosphor-icons/react';

import './index.css';
import clsx from 'clsx';

import { localizeHref } from '../../utils/localizeHref';

const DEFAULT_HERO = {
  badge: '',
  name: '',
  text: '',
  tagline: '',
  actions: [],
  image: undefined,
} satisfies FrontMatterMeta['hero'];

interface HomeHeroProps {
  beforeHeroActions?: React.ReactNode;
  afterHeroActions?: React.ReactNode;
  image?: React.ReactNode;
}

function HomeHero({
  beforeHeroActions,
  afterHeroActions,
  image,
}: HomeHeroProps) {
  const { frontmatter } = useFrontmatter();
  const lang = useLang();
  const hero = frontmatter?.hero || DEFAULT_HERO;
  const hasImage = hero.image !== undefined || image !== undefined;
  const multiHeroText = hero.text
    ? hero.text
        .toString()
        .split(/\n/g)
        .filter(text => text !== '')
    : [];

  return (
    <div
      className={clsx('runbuoy-home-hero', {
        'runbuoy-home-hero--no-image': !hasImage,
      })}
    >
      <div className="runbuoy-home-hero__container">
        {hero.badge &&
          (typeof hero.badge === 'string' ? (
            <div className="runbuoy-home-hero__badge">{hero.badge}</div>
          ) : hero.badge.link ? (
            <Link href={hero.badge.link} className="runbuoy-home-hero__badge">
              {hero.badge.text}
            </Link>
          ) : (
            <div className="runbuoy-home-hero__badge">{hero.badge.text}</div>
          ))}
        <div className="runbuoy-home-hero__content">
          <p className="runbuoy-home-hero__title">
            <span
              className="runbuoy-home-hero__title-brand"
              {...renderHtmlOrText(hero.name)}
            ></span>
          </p>

          {multiHeroText.length !== 0 && (
            <h1 className="runbuoy-home-hero__subtitle">
              {multiHeroText.map(heroText => (
                <span key={heroText} {...renderHtmlOrText(heroText)} />
              ))}
            </h1>
          )}
        </div>
        <p
          className="runbuoy-home-hero__tagline"
          {...renderHtmlOrText(hero.tagline)}
        ></p>

        <>
          {beforeHeroActions}
          <div className="runbuoy-home-hero__actions">
            {hero.actions?.map(action => {
              const isComingSoon = action.link.includes('download');
              const Icon = action.link.includes('#agent-install')
                ? MagicWand
                : isComingSoon
                  ? AppStoreLogo
                  : TerminalWindow;

              if (isComingSoon) {
                return (
                  <Link
                    key={action.link}
                    href={localizeHref(action.link, lang)}
                    className="runbuoy-home-hero__status-link"
                  >
                    <Icon size={17} weight="bold" aria-hidden="true" />
                    <span {...renderHtmlOrText(action.text)} />
                  </Link>
                );
              }

              return (
                <Button
                  type="a"
                  key={action.link}
                  href={localizeHref(action.link, lang)}
                  theme={action.theme}
                  className={clsx('runbuoy-home-hero__action', {
                    'runbuoy-home-hero__action--primary':
                      action.theme === 'brand',
                  })}
                >
                  <Icon size={19} weight="bold" aria-hidden="true" />
                  <span {...renderHtmlOrText(action.text)} />
                </Button>
              );
            })}
          </div>
          {afterHeroActions}
        </>
      </div>
      {image ? (
        <div className="runbuoy-home-hero__image">{image}</div>
      ) : hero.image ? (
        <div className="runbuoy-home-hero__image">
          <LiveActivityShowcase
            lang={lang}
            alt={hero.image?.alt || 'RunBuoy Live Activity'}
          />
        </div>
      ) : null}
    </div>
  );
}

function LiveActivityShowcase({ lang, alt }: { lang: string; alt: string }) {
  const zh = lang.startsWith('zh');
  return (
    <div className="runbuoy-live-preview" role="img" aria-label={alt}>
      <div className="runbuoy-live-preview__glow" />
      <div className="runbuoy-live-preview__phone">
        <div className="runbuoy-live-preview__island">
          <Waveform size={17} weight="bold" aria-hidden="true" />
          <span>72%</span>
        </div>
        <div className="runbuoy-live-preview__date">
          {zh ? '7 月 29 日 星期三' : 'Wednesday, July 29'}
        </div>
        <div className="runbuoy-live-preview__time">9:41</div>
        <div className="runbuoy-live-preview__activity">
          <div className="runbuoy-live-preview__activity-head">
            <span className="runbuoy-live-preview__app-icon" aria-hidden="true">
              <img
                className="runbuoy-live-preview__app-icon-light"
                src="/brand/runbuoy-icon-light.png"
                width="34"
                height="34"
                alt=""
              />
              <img
                className="runbuoy-live-preview__app-icon-dark"
                src="/brand/runbuoy-icon-dark.png"
                width="34"
                height="34"
                alt=""
              />
            </span>
            <div>
              <strong>Gurobi experiment</strong>
              <span>{zh ? '正在运行' : 'Running'}</span>
            </div>
            <b>72%</b>
          </div>
          <div
            className="runbuoy-live-preview__progress"
            aria-hidden="true"
          >
            <i />
          </div>
          <div className="runbuoy-live-preview__activity-foot">
            <span>{zh ? '正在优化 · Mac Studio' : 'Optimizing · Mac Studio'}</span>
            <span>10:20</span>
          </div>
        </div>
        <div className="runbuoy-live-preview__hint">
          <span>{zh ? '实时活动' : 'LIVE ACTIVITY'}</span>
          <span>{zh ? '进度持续更新' : 'PROGRESS AT A GLANCE'}</span>
        </div>
      </div>
    </div>
  );
}

export type { HomeHeroProps };
export { HomeHero };

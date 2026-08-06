import {
  HomeBackground,
  type HomeLayoutProps,
} from '@rspress/core/theme-original';

import { HomeContent } from '../HomeContent';
import { HomeFeature } from '../HomeFeature';
import { HomeFooter } from '../HomeFooter';
import { HomeHero } from '../HomeHero';

function HomeLayout({
  beforeHero,
  afterHero,
  beforeHeroActions,
  afterHeroActions,
  beforeFeatures,
  afterFeatures,
}: HomeLayoutProps) {
  return (
    <>
      <HomeBackground />
      <main id="main-content">
        {beforeHero}
        <HomeHero
          beforeHeroActions={beforeHeroActions}
          afterHeroActions={afterHeroActions}
        />
        {afterHero}
        {beforeFeatures}
        <HomeFeature />
        {afterFeatures}
        <HomeContent />
      </main>
      <HomeFooter />
    </>
  );
}

export { HomeLayout };

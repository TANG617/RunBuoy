import { useEffect } from 'react';
import { useLang } from '@rspress/core/runtime';
import { NavHamburger as OriginalNavHamburger } from '@rspress/core/theme-original';

function NavHamburger() {
  const lang = useLang();

  useEffect(() => {
    const buttons = Array.from(
      document.querySelectorAll<HTMLButtonElement>('.rp-nav-hamburger'),
    );
    const observers: MutationObserver[] = [];

    const update = (button: HTMLButtonElement) => {
      const active = button.classList.contains('rp-nav-hamburger--active');
      const isMobile = button.classList.contains('rp-nav-hamburger__sm');
      const zh = lang.startsWith('zh');

      if (isMobile) {
        button.setAttribute(
          'aria-label',
          zh
            ? active
              ? '关闭导航'
              : '打开导航'
            : active
              ? 'Close navigation'
              : 'Open navigation',
        );
        button.setAttribute('aria-expanded', String(active));
        button.setAttribute('aria-haspopup', 'dialog');
        button.setAttribute('aria-controls', '__rspress_modal_container');
      } else {
        button.setAttribute(
          'aria-label',
          zh
            ? '打开主题、语言和社区链接'
            : 'Open theme, language, and community links',
        );
        button.setAttribute('aria-haspopup', 'menu');
      }
    };

    buttons.forEach(button => {
      update(button);
      const observer = new MutationObserver(() => update(button));
      observer.observe(button, { attributes: true, attributeFilter: ['class'] });
      observers.push(observer);
    });

    return () => observers.forEach(observer => observer.disconnect());
  }, [lang]);

  return <OriginalNavHamburger />;
}

export { NavHamburger };

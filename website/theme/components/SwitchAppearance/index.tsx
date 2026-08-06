import { useContext } from 'react';
import { ThemeContext, useLang } from '@rspress/core/runtime';
import { Moon, Sun } from '@phosphor-icons/react';

import './index.css';

function SwitchAppearance({ onClick }: { onClick?: () => void }) {
  const { theme, setTheme = () => {} } = useContext(ThemeContext);
  const lang = useLang();
  const isDark = theme === 'dark';
  const label = lang.startsWith('zh')
    ? isDark
      ? '切换到浅色主题'
      : '切换到深色主题'
    : isDark
      ? 'Switch to light theme'
      : 'Switch to dark theme';

  return (
    <button
      type="button"
      className="rp-switch-appearance runbuoy-appearance-toggle"
      aria-label={label}
      aria-pressed={isDark}
      title={label}
      onClick={() => {
        setTheme(isDark ? 'light' : 'dark');
        onClick?.();
      }}
    >
      <Sun
        className="rp-switch-appearance__icon rp-switch-appearance__icon--sun"
        size={21}
        weight="fill"
        aria-hidden="true"
      />
      <Moon
        className="rp-switch-appearance__icon rp-switch-appearance__icon--moon"
        size={19}
        weight="fill"
        aria-hidden="true"
      />
    </button>
  );
}

export { SwitchAppearance };

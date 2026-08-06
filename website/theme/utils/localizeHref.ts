function localizeHref(href: string, lang: string): string {
  if (
    !href.startsWith('/') ||
    href.startsWith('//') ||
    href.startsWith('/en/') ||
    href === '/en'
  ) {
    return href;
  }

  if (!lang.startsWith('en')) {
    return href;
  }

  return href === '/' ? '/en/' : `/en${href}`;
}

export { localizeHref };

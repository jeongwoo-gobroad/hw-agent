/* i18next is bundled locally. Only explicit UI messages enter the catalog. */
(() => {
  let saved;
  try { saved = localStorage.getItem('alter-language'); } catch {}
  const language = ['en', 'ko'].includes(saved) ? saved :
    (navigator.language?.toLowerCase().startsWith('ko') ? 'ko' : 'en');
  i18next.init({lng: language, fallbackLng: 'ko', supportedLngs: ['en', 'ko'],
    resources: window.AlterLocales, initImmediate: false, keySeparator: false,
    nsSeparator: false, interpolation: {escapeValue: false}});
  window.tr = (key, values) => i18next.t(key, values);
  window.alterLanguage = language;
  document.documentElement.lang = language;
  document.cookie = `alter_language=${language}; Path=/; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-i18n]').forEach(node => {node.textContent = tr(node.dataset.i18n);});
    for (const attr of ['placeholder', 'aria-label', 'title', 'alt']) {
      document.querySelectorAll(`[data-i18n-${attr}]`).forEach(node =>
        node.setAttribute(attr, tr(node.getAttribute(`data-i18n-${attr}`))));
    }
    const select = document.createElement('select');
    select.id = 'language-select'; select.setAttribute('aria-label', 'Language / 언어');
    select.add(new Option('English', 'en')); select.add(new Option('한국어', 'ko'));
    select.value = language;
    select.addEventListener('change', () => {
      const unsent = document.querySelector('#chat-form input')?.value;
      if (unsent && !confirm(tr('언어를 변경하면 작성 중인 메시지가 사라집니다. 계속할까요?'))) {
        select.value = language; return;
      }
      try {localStorage.setItem('alter-language', select.value);} catch {}
      // Reload also updates dynamic labels without touching user-owned data.
      location.reload();
    });
    const host = document.querySelector('.header-actions') || document.querySelector('.login-card');
    host?.prepend(select);
  });
})();

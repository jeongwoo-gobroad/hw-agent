(() => {
  let saved;
  try { saved = localStorage.getItem("alter-theme"); } catch {}
  let theme = saved === "dark" || saved === "light" ? saved :
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  function apply() {
    document.documentElement.dataset.theme = theme;
    const toggle = document.querySelector("#theme-toggle");
    if (toggle) {
      toggle.textContent = theme === "dark" ? "라이트 모드" : "다크 모드";
      toggle.setAttribute("aria-label", toggle.textContent + "로 전환");
      toggle.setAttribute("aria-pressed", String(theme === "dark"));
    }
  }
  apply();
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.querySelector("#theme-toggle")?.addEventListener("click", () => {
      theme = theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("alter-theme", theme); } catch {}
      apply();
    });
  });
})();

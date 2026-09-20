import cssText from './styles.css';

export function installCss(ctx) {
  var cssInjected = false;
  function ensureCss() {
    if (typeof document === "undefined") return;
    var ver = "composer-106";
    if (cssInjected && document.querySelector("style[data-wb-cd-css='" + ver + "']")) return;
    document.querySelectorAll("style[data-plugin='@dsh-external/dsh-mes-bridge']").forEach(function (el) {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
    cssInjected = true;
    var s = document.createElement("style");
    s.dataset.plugin = "@dsh-external/dsh-mes-bridge";
    s.dataset.wbCdCss = ver;
    s.textContent = cssText;
    document.head.appendChild(s);
  }
  ctx.ensureCss = ensureCss;
}

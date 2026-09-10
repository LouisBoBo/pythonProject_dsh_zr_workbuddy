/**
 * ZR-WorkBuddy 客户端：
 * - 主聊天 toolview：审码/提交/写码选目录卡
 * - 宿主设置同级页：settings.section「WorkBuddy」配置中心（读写引擎 /api/config）
 * 引擎地址 RUNTIME 块由 plugin.sh 从 runtime.yaml 同步。
 */
/*RUNTIME_BEGIN*/
window.__APP_ENGINE__ = { host: "127.0.0.1", port: 8000 };
/*RUNTIME_END*/
window.__ModuleLoader__.load({
  id: "@dsh-external/dsh-mes-bridge",
  factory: (require) => {
    var module = { exports: {} };
    var React = require("react");
    var h = React.createElement;
    var useState = React.useState;
    var useMemo = React.useMemo;
    var useEffect = React.useEffect;
    var useRef = React.useRef;

    function engineHost() {
      try {
        var x = localStorage.getItem("dsh-mes-engine-host");
        if (x) return x;
      } catch (e) {}
      var cfg = window.__APP_ENGINE__ || {};
      return cfg.host || "127.0.0.1";
    }
    function enginePort() {
      try {
        var p = localStorage.getItem("dsh-mes-engine-port");
        if (p && /^\d+$/.test(p)) return p;
      } catch (e) {}
      var cfg = window.__APP_ENGINE__ || {};
      return String(cfg.port || 8000);
    }
    function engineBase() {
      return "http://" + engineHost() + ":" + enginePort();
    }

    /** 一体包走 Electron 原生选目录，避免 osascript→Finder 报 -1743。 */
    function pickLocalFolder(prompt, signal) {
      var p = prompt || "选择工程目录";
      try {
        var desk = typeof window !== "undefined" ? window.workbuddyDesktop : null;
        if (desk && typeof desk.pickFolder === "function") {
          return Promise.resolve(desk.pickFolder(p)).then(function (d) {
            if (d && typeof d === "object") return d;
            return { ok: false, path: "", error: "选文件夹失败" };
          });
        }
      } catch (e0) {}
      return fetch(engineBase() + "/api/pick-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: p }),
        signal: signal,
      }).then(function (r) {
        return r.json();
      });
    }

    /** 确认卡点击前签发一次性 HITL nonce；失败抛错（带 detail）。 */
    function issueHitl(action, bind) {
      var body = Object.assign({ action: action }, bind || {});
      return fetch(engineBase() + "/api/hitl/issue", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-WorkBuddy-Hitl": "ui",
        },
        body: JSON.stringify(body),
      }).then(function (r) {
        return r.json().then(function (d) {
          if (!r.ok || !d || !d.ok || !d.nonce) {
            var msg = (d && (d.detail || d.reply)) || "HITL 签发失败 HTTP " + r.status;
            var err = new Error(msg);
            err.hitl = d;
            throw err;
          }
          return d.nonce;
        });
      });
    }

    function discoverEngine() {
      fetch(engineBase() + "/api/runtime")
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d && d.ok && d.port) {
            try {
              if (d.host) localStorage.setItem("dsh-mes-engine-host", String(d.host));
              localStorage.setItem("dsh-mes-engine-port", String(d.port));
            } catch (e) {}
          }
        })
        .catch(function () {});
    }

    var cssInjected = false;
    function ensureCss() {
      if (typeof document === "undefined") return;
      var ver = "composer-17";
      if (cssInjected && document.querySelector("style[data-wb-cd-css='" + ver + "']")) return;
      document.querySelectorAll("style[data-plugin='@dsh-external/dsh-mes-bridge']").forEach(function (el) {
        if (el.parentNode) el.parentNode.removeChild(el);
      });
      cssInjected = true;
      var s = document.createElement("style");
      s.dataset.plugin = "@dsh-external/dsh-mes-bridge";
      s.dataset.wbCdCss = ver;
      s.textContent =
        ".wb-cr{font:13px/1.5 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#111827;border:1px solid #e5e7eb;border-radius:12px;background:#fff;overflow:hidden;margin:4px 0 8px;width:100%;max-width:100%;box-sizing:border-box;min-width:0}" +
        ".wb-cr-head{padding:10px 12px;border-bottom:1px solid #eef0f3;display:flex;align-items:center;gap:8px}" +
        ".wb-cr-badge{font-size:11px;font-weight:700;color:#0f766e;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:999px;padding:2px 8px}" +
        ".wb-cr-hint{font-size:11px;color:#64748b}" +
        ".wb-cr-body{padding:12px;min-width:0;width:100%;box-sizing:border-box}" +
        ".wb-cr-label{display:block;font-size:11px;font-weight:600;color:#374151;margin:0 0 6px}" +
        ".wb-cr-row{display:flex;gap:8px;align-items:center;margin-bottom:10px}" +
        ".wb-cr-input{flex:1;min-width:0;border:1px solid #d1d5db;border-radius:8px;padding:8px 10px;font:12px/1.4 ui-monospace,Menlo,monospace}" +
        ".wb-cr-btn{border:1px solid #d1d5db;background:#f9fafb;border-radius:8px;padding:7px 12px;font-size:12px;cursor:pointer;white-space:nowrap}" +
        ".wb-cr-btn:hover{border-color:#0ea5e9;color:#0369a1}" +
        ".wb-cr-btn:disabled{opacity:.5;cursor:not-allowed}" +
        ".wb-cr-btn.primary{background:linear-gradient(135deg,#0f766e,#0ea5e9);border:none;color:#fff;font-weight:600}" +
        ".wb-cr-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}" +
        ".wb-cr-chip{border:1px solid #e5e7eb;border-radius:999px;padding:4px 10px;font-size:11px;background:#f8fafc;cursor:pointer;max-width:100%;overflow:hidden;text-overflow:ellipsis}" +
        ".wb-cr-chip:hover{border-color:#0ea5e9;color:#0369a1}" +
        ".wb-cr-err{color:#b91c1c;font-size:12px;margin:8px 0 0;white-space:pre-wrap}" +
        ".wb-cr-warn{color:#b45309;background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:8px 10px;font-size:12px;margin:8px 0 0;white-space:pre-wrap}" +
        ".wb-cr-dsh{font-size:11px;color:#64748b;margin:0 0 8px}" +
        ".wb-cr-dsh code{font-size:11px;word-break:break-all}" +
        ".wb-cr-files{max-height:220px;overflow:auto;border:1px solid #e5e7eb;border-radius:10px;padding:8px;margin:8px 0;font-size:12px}" +
        ".wb-cr-file{display:flex;gap:8px;align-items:flex-start;margin:4px 0;cursor:pointer}" +
        ".wb-cr-file span{word-break:break-all;font-family:ui-monospace,Menlo,monospace}" +
        ".wb-cr-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}" +
        ".wb-set{font:13px/1.5 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:var(--ds-color-text-primary,#111827);max-width:720px;padding:4px 4px 24px}" +
        ".wb-set-lead{font-size:12px;color:var(--ds-color-text-secondary,#64748b);margin:0 0 14px}" +
        ".wb-set-eng{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 14px;padding:10px 12px;border:1px solid var(--ds-color-border-subtle,#e5e7eb);border-radius:10px;background:var(--ds-color-bg-secondary,#f8fafc)}" +
        ".wb-set-eng label{font-size:11px;font-weight:600;color:#374151}" +
        ".wb-set-eng input{width:110px;border:1px solid #d1d5db;border-radius:8px;padding:6px 8px;font:12px/1.4 ui-monospace,Menlo,monospace}" +
        ".wb-set-card{border:1px solid var(--ds-color-border-subtle,#e5e7eb);border-radius:12px;background:#fff;margin:0 0 12px;overflow:hidden}" +
        ".wb-set-card h3{margin:0;padding:10px 12px;font-size:13px;font-weight:700;border-bottom:1px solid #eef0f3;background:#fafbfc}" +
        ".wb-set-card .body{padding:12px}" +
        ".wb-set-hint{font-size:11px;color:#64748b;margin:0 0 10px}" +
        ".wb-set-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px}" +
        ".wb-set-grid .full{grid-column:1/-1}" +
        ".wb-set-field label{display:block;font-size:11px;font-weight:600;color:#374151;margin:0 0 4px}" +
        ".wb-set-field input,.wb-set-field select{width:100%;box-sizing:border-box;border:1px solid #d1d5db;border-radius:8px;padding:7px 9px;font:12px/1.4 inherit}" +
        ".wb-set-check{display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:12px}" +
        ".wb-set-radios{display:flex;flex-wrap:wrap;gap:10px 14px;margin:0 0 10px;font-size:12px}" +
        ".wb-set-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;position:sticky;bottom:0;padding:10px 0 0;background:linear-gradient(180deg,transparent,var(--ds-color-bg-primary,#fff) 28%)}" +
        ".wb-set-btn{border:1px solid #d1d5db;background:#f9fafb;border-radius:8px;padding:7px 12px;font-size:12px;cursor:pointer}" +
        ".wb-set-btn:hover{border-color:#0ea5e9;color:#0369a1}" +
        ".wb-set-btn:disabled{opacity:.5;cursor:not-allowed}" +
        ".wb-set-btn.primary{background:linear-gradient(135deg,#0f766e,#0ea5e9);border:none;color:#fff;font-weight:600}" +
        ".wb-set-msg{font-size:12px;color:#64748b}" +
        ".wb-set-msg.ok{color:#047857}" +
        ".wb-set-msg.err{color:#b91c1c}" +
        ".wb-set-test{font-size:11px;margin:8px 0 0;white-space:pre-wrap;color:#64748b}" +
        "@media (max-width:640px){.wb-set-grid{grid-template-columns:1fr}}" +
        ".wb-cr-progress{font-size:12px;color:#475569;white-space:pre-wrap;max-height:280px;overflow:auto;background:#f8fafc;border-radius:8px;padding:10px;margin-top:8px}" +
        ".wb-cd-plan{border:1px solid #e5e7eb;border-radius:10px;background:#f8fafc;padding:10px;margin:8px 0}" +
        ".wb-cd-plan-head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 8px;font-size:12px}" +
        ".wb-cd-plan-head .sum{color:#64748b}" +
        ".wb-cd-plan-head .dur{margin-left:auto;font-variant-numeric:tabular-nums;color:#0f766e;font-weight:600}" +
        ".wb-cd-ol{list-style:none;margin:0;padding:0}" +
        ".wb-cd-li{display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-top:1px solid #eef2f7;font-size:12px}" +
        ".wb-cd-li:first-child{border-top:none}" +
        ".wb-cd-ico{width:18px;height:18px;flex:none;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;font-size:11px;font-weight:700}" +
        ".wb-cd-li.is-pending .wb-cd-ico{background:#e5e7eb;color:#6b7280}" +
        ".wb-cd-li.is-running .wb-cd-ico{background:#dcfce7;color:#15803d}" +
        ".wb-cd-li.is-done .wb-cd-ico{background:#d1fae5;color:#047857}" +
        ".wb-cd-li.is-error .wb-cd-ico{background:#fee2e2;color:#b91c1c}" +
        ".wb-cd-title{font-weight:600;color:#111827;display:block}" +
        ".wb-cd-state{color:#64748b;font-size:11px}" +
        ".wb-cd-pulse{display:inline-block;width:8px;height:8px;border-radius:999px;background:#06b6d4;animation:wbCdPulse 1s ease-in-out infinite}" +
        "@keyframes wbCdPulse{0%,100%{opacity:.35;transform:scale(.85)}50%{opacity:1;transform:scale(1)}}" +
        ".wb-cd-dot-live{display:inline-block;width:8px;height:8px;border-radius:999px;background:#16a34a;box-shadow:0 0 0 2px rgba(22,163,74,.18)}" +
        ".wb-cd-spin{display:inline-block;width:12px;height:12px;box-sizing:border-box;border:2px solid #bae6fd;border-top-color:#0284c7;border-radius:999px;animation:wbCdSpin .65s linear infinite;vertical-align:middle}" +
        "@keyframes wbCdSpin{to{transform:rotate(360deg)}}" +
        ".wb-cd-pipecard-h .hint .wb-cd-spin{display:block}" +
        ".wb-cd-act ul{list-style:none;margin:0;padding:0}" +
        ".wb-cd-act li{display:flex;align-items:flex-start;gap:8px}" +
        ".wb-cd-act li::before{content:'';flex:none;width:8px;height:8px;margin-top:5px;border-radius:999px;background:#94a3b8}" +
        ".wb-cd-act li.is-live::before{background:#16a34a;box-shadow:0 0 0 2px rgba(22,163,74,.18)}" +
        ".wb-cd-flow{width:100%;min-width:0;max-width:100%;overflow:visible;background:transparent;border:none;padding:0;margin:8px 0;box-sizing:border-box}" +
        ".wb-cd-composer{width:100%;min-width:0;margin:4px 0 8px;padding:0}" +
        ".wb-cd-composer-bar{display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:12px;color:#64748b}" +
        ".wb-cd-composer-bar .ws{margin-left:auto;max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:ui-monospace,Menlo,monospace;font-size:11px}" +
        ".wb-cd-toolchip{display:inline-flex;align-items:center;gap:6px;margin:0 0 12px;padding:5px 10px;border:1px solid #e2e8f0;border-radius:999px;background:#f8fafc;font-size:12px;color:#475569;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        ".wb-cd-codewrap{margin:12px 0 16px;border-radius:12px;overflow:hidden;background:#f4f4f4;border:1px solid #e5e5e5;box-shadow:none}" +
        ".wb-cd-codebar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 14px;background:#f4f4f4;border-bottom:1px solid #e5e5e5;min-height:40px;box-sizing:border-box}" +
        ".wb-cd-codelang{font:13px/1.4 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#666;text-transform:lowercase;letter-spacing:.01em;flex-shrink:0}" +
        ".wb-cd-codeacts{display:flex;align-items:center;gap:2px;flex-shrink:0}" +
        ".wb-cd-codebtn{display:inline-flex;align-items:center;gap:5px;margin:0;padding:5px 8px;border:none;border-radius:8px;background:transparent;color:#666;font:13px/1.4 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;cursor:pointer;white-space:nowrap}" +
        ".wb-cd-codebtn:hover{background:#e8e8e8;color:#333}" +
        ".wb-cd-codebtn svg{width:16px;height:16px;flex-shrink:0;display:block}" +
        ".wb-cd-codebtn.is-copied{color:#0f766e}" +
        ".wb-cd-codewrap-streaming .wb-cd-codelang::after{content:' · 写入中';margin-left:6px;color:#999;font-size:12px;text-transform:none}" +
        ".wb-cd-md .wb-cd-codewrap pre.wb-cd-code,.wb-cd-doc .wb-cd-codewrap pre.wb-cd-code,.wb-cd-stream .wb-cd-codewrap pre.wb-cd-code{background:#fafafa!important;color:#1f2328!important;padding:14px 16px!important;margin:0!important;overflow:auto;font:13px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace!important;max-height:min(70vh,640px);white-space:pre!important;word-break:normal!important;overflow-wrap:normal!important;tab-size:4;-webkit-overflow-scrolling:touch;border-radius:0}" +
        ".wb-cd-md .wb-cd-codewrap pre.wb-cd-code code,.wb-cd-doc .wb-cd-codewrap pre.wb-cd-code code,.wb-cd-stream .wb-cd-codewrap pre.wb-cd-code code{background:none!important;color:#1f2328!important;padding:0!important;margin:0!important;font:inherit!important;white-space:pre!important;display:block;user-select:text}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-op{color:#1f2328!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-kw{color:#9538b3!important;font-weight:500!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-fn{color:#0550ae!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-builtin{color:#116329!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-str{color:#0a3069!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-doc{color:#116329!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-cmt{color:#6e7781!important;font-style:italic!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-num{color:#0550ae!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-name{color:#116329!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-attr{color:#0550ae!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-punct{color:#59636e!important}" +
        ".wb-cd-codewrap pre.wb-cd-code .wb-hl-tag{color:#59636e!important}" +
        ".wb-cd-md{font:15px/1.85 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#0f172a;white-space:normal;width:100%;max-width:100%;min-width:0;box-sizing:border-box;overflow:visible;background:transparent;border:none;padding:0;margin:4px 0 0;overflow-wrap:break-word;word-break:normal}" +
        ".wb-cd-proc{list-style:none;margin:6px 0 12px;padding:0!important;position:relative;border-left:none}" +
        ".wb-cd-proc-li{display:flex;gap:12px;align-items:flex-start;margin:0;padding:0 0 16px;position:relative;border-top:none}" +
        ".wb-cd-proc-li:last-child{padding-bottom:0}" +
        ".wb-cd-proc-rail{flex:none;width:22px;position:relative;display:flex;justify-content:center;align-items:flex-start;padding-top:3px;align-self:stretch}" +
        ".wb-cd-proc-li:not(:last-child) .wb-cd-proc-rail::before{content:'';position:absolute;left:50%;top:14px;bottom:-16px;width:1px;transform:translateX(-50%);background:#e5e7eb;pointer-events:none;z-index:0}" +
        ".wb-cd-proc-node{flex:none;width:22px;height:22px;border-radius:999px;background:#fff;border:1px solid #e5e7eb;display:inline-flex;align-items:center;justify-content:center;position:relative;z-index:1;box-sizing:border-box;color:#64748b}" +
        ".wb-cd-proc-node.is-dot{border-color:transparent;background:transparent}" +
        ".wb-cd-proc-node.is-live{border-color:#86efac;color:#15803d;box-shadow:0 0 0 2px rgba(22,163,74,.14)}" +
        ".wb-cd-proc-node.is-dot.is-live{border-color:transparent;box-shadow:none;color:#64748b}" +
        ".wb-cd-proc-node.is-dot::after{content:'';width:8px;height:8px;border-radius:999px;background:#94a3b8;box-shadow:0 0 0 3px #fff}" +
        ".wb-cd-proc-node.is-dot.is-live::after{background:#16a34a;box-shadow:0 0 0 3px #fff,0 0 0 5px rgba(22,163,74,.16)}" +
        ".wb-cd-proc-node svg{width:12px;height:12px;display:block}" +
        ".wb-cd-proc-body{flex:1;min-width:0;padding-top:1px}" +
        ".wb-cd-proc-t{margin:0;font-size:14px;line-height:1.75;color:#0f172a;overflow-wrap:break-word}" +
        ".wb-cd-proc-t + .wb-cd-proc-t,.wb-cd-proc-t + .wb-cd-proc-path,.wb-cd-proc-path + .wb-cd-proc-path{margin-top:6px}" +
        ".wb-cd-proc-path{margin:0;font:12px/1.55 ui-monospace,Menlo,Consolas,monospace;color:#334155;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:4px 8px;overflow-wrap:anywhere}" +
        ".wb-cd-proc-meta{margin:0 0 4px;font-size:12px;font-weight:650;color:#64748b;letter-spacing:.02em}" +
        ".wb-cd-proc-links{list-style:none;margin:6px 0 0;padding:0}" +
        ".wb-cd-proc-links li{margin:0 0 4px;font-size:13px;line-height:1.55;color:#334155}" +
        ".wb-cd-proc-links li:last-child{margin-bottom:0}" +
        ".wb-cd-md h3,.wb-cd-md h4{margin:18px 0 8px;font-size:15px;font-weight:650;color:#111827}" +
        ".wb-cd-md p{margin:0 0 12px;max-width:100%;overflow-wrap:break-word}" +
        ".wb-cd-md table{border-collapse:collapse;width:100%;margin:8px 0 14px;font-size:13px;table-layout:auto;display:block;overflow-x:auto}" +
        ".wb-cd-md th,.wb-cd-md td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:break-word}" +
        ".wb-cd-md th{background:#f8fafc}" +
        ".wb-cd-md code{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:#f1f5f9;padding:1px 4px;border-radius:4px;white-space:pre-wrap;overflow-wrap:break-word}" +
        ".wb-cd-md .wb-cd-codewrap code,.wb-cd-stream .wb-cd-codewrap code{background:none!important;padding:0!important;border-radius:0!important;white-space:pre!important}" +
        ".wb-cd-md ul,.wb-cd-md ol{margin:0 0 16px;padding-left:1.35em}" +
        ".wb-cd-md li{margin:0 0 8px;line-height:1.75}" +
        ".wb-cd-md pre.wb-cd-code{background:#0f172a;color:#e2e8f0;padding:12px 14px;border-radius:0;overflow:auto;font:12.5px/1.55 ui-monospace,Menlo,monospace;margin:0;max-height:min(70vh,640px);white-space:pre}" +
        ".wb-cd-md pre.wb-cd-code code{background:none;color:inherit;padding:0;white-space:pre;overflow-wrap:normal}" +
        ".wb-cd-codewrap + .wb-cd-codewrap{margin-top:8px}" +
        ".wb-cd-kicker{margin:20px 0 8px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#0f766e}" +
        ".wb-cd-doc{margin-top:8px;padding-top:4px}" +
        ".wb-cd-doc h3{margin:20px 0 8px;font-size:14px;font-weight:700}" +
        ".wb-cd-doc h3:first-child{margin-top:4px;font-size:16px}" +
        ".wb-cd-doc p{margin:0 0 14px;line-height:1.85}" +
        ".wb-cd-doc ul,.wb-cd-doc ol{margin:0 0 16px;padding-left:1.4em}" +
        ".wb-cd-doc li{margin:0 0 8px;line-height:1.75}" +
        ".wb-cd-stream{font:13px/1.65 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#0f172a;white-space:normal;width:100%;max-width:100%;min-width:0;box-sizing:border-box;overflow:visible;background:transparent;border:none;padding:0;margin-top:8px;overflow-wrap:break-word}" +
        ".wb-cd-stream h3,.wb-cd-stream h4{margin:12px 0 6px;font-size:14px;color:#111827}" +
        ".wb-cd-stream p{margin:0 0 10px;max-width:100%;overflow-wrap:break-word}" +
        ".wb-cd-stream table{border-collapse:collapse;width:100%;margin:8px 0;font-size:12px;table-layout:auto}" +
        ".wb-cd-stream th,.wb-cd-stream td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:break-word}" +
        ".wb-cd-stream th{background:#f8fafc}" +
        ".wb-cd-stream code{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:#f1f5f9;padding:1px 4px;border-radius:4px;white-space:pre-wrap;overflow-wrap:break-word}" +
        ".wb-cd-stream ul,.wb-cd-stream ol{margin:0 0 8px;padding-left:1.2em}" +
        ".wb-cd-stream pre.wb-cd-code{background:#0f172a;color:#e2e8f0;padding:10px 12px;border-radius:8px;overflow:auto;font:12px/1.5 ui-monospace,Menlo,monospace;margin:8px 0 12px;white-space:pre}" +
        ".wb-cd-stream pre.wb-cd-code code{background:none;color:inherit;padding:0;white-space:pre;overflow-wrap:normal}" +
        ".wb-cd-action{margin:8px 0 0;font-size:12px;color:#334155;overflow-wrap:anywhere}" +
        ".wb-cd-tools{margin-top:6px;font-size:12px;color:#64748b}" +
        ".wb-cd-tools summary{cursor:pointer}" +
        ".wb-cd-think{margin:0 0 10px;border:1px solid #e5e7eb;border-radius:8px;background:#f8fafc;overflow:hidden;width:100%;box-sizing:border-box}" +
        ".wb-cd-think summary{cursor:pointer;list-style:none;padding:8px 12px;font-size:12px;color:#64748b;user-select:none}" +
        ".wb-cd-think summary::-webkit-details-marker{display:none}" +
        ".wb-cd-think.is-live{display:flex;align-items:center;gap:8px;border:none;background:transparent;border-radius:0;margin:0 0 12px;overflow:visible}" +
        ".wb-cd-think-lab{flex:none;font-size:13px;font-weight:650;color:#64748b;line-height:20px;letter-spacing:.02em}" +
        ".wb-cd-think-rail{flex:none;width:2px;height:16px;border-radius:1px;background:#94a3b8}" +
        ".wb-cd-think-ticker{flex:1;min-width:0;height:20px;overflow:hidden;position:relative}" +
        ".wb-cd-think-line.is-solo{height:20px;line-height:20px;padding:0;font-size:13px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:opacity .35s ease}" +
        ".wb-cd-think-line.is-solo.is-fade{opacity:.35}" +
        ".wb-cd-think .wb-cd-think-body{padding:10px 12px 12px;font-size:13px;color:#334155;white-space:pre-wrap;overflow-wrap:anywhere;word-break:normal;line-height:1.7;border-top:1px dashed #e5e7eb;max-height:min(40vh,320px);overflow:auto}" +
        ".wb-cd-alive{font-size:12px;color:#0f766e;margin:0 0 8px}" +
        ".wb-cd-act{margin:0 0 12px;padding:10px 12px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;max-height:min(36vh,280px);overflow:auto}" +
        ".wb-cd-act-h{font-size:11px;font-weight:650;color:#64748b;margin:0 0 8px;letter-spacing:.04em}" +
        ".wb-cd-act li{display:flex;align-items:flex-start;gap:8px;margin:0 0 6px;font-size:12px;line-height:1.55;color:#334155;font-family:ui-monospace,Menlo,monospace;word-break:break-all}" +
        ".wb-cd-act li.is-live{color:#0369a1;font-weight:600}" +
        ".wb-cd-act li.is-live::before{background:#16a34a;box-shadow:0 0 0 2px rgba(22,163,74,.18)}" +
        ".wb-cd-stack{display:flex;flex-direction:column;gap:8px;width:100%;min-width:0}" +
        ".wb-cd-intro{margin:0 0 4px;padding:10px 12px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;font-size:13px;line-height:1.65;color:#0c4a6e}" +
        ".wb-cd-guide{margin:0;padding:10px 14px 10px 1.7em;border:1px solid #e5e7eb;border-radius:12px;background:#fff;font-size:13px;line-height:1.75;color:#334155}" +
        ".wb-cd-guide li{margin:0 0 8px}" +
        ".wb-cd-guide li:last-child{margin:0}" +
        ".wb-cd-guide li.is-on{font-weight:650;color:#0f766e}" +
        ".wb-cd-guide li.is-done{color:#64748b}" +
        ".wb-cd-checks{display:flex;flex-wrap:wrap;gap:8px 12px;margin:0 0 12px;padding:0;list-style:none}" +
        ".wb-cd-checks li{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#94a3b8}" +
        ".wb-cd-checks li.is-on{color:#0f766e;font-weight:650}" +
        ".wb-cd-checks li.is-done{color:#047857}" +
        ".wb-cd-checks .mark{width:18px;height:18px;flex:none;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;background:#e5e7eb;color:#6b7280}" +
        ".wb-cd-checks li.is-on .mark{background:#cffafe;color:#0e7490}" +
        ".wb-cd-checks li.is-done .mark{background:#d1fae5;color:#047857}" +
        ".wb-cd-pipe{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 14px;width:100%;min-width:0}" +
        ".wb-cd-pipecard{border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc;overflow:hidden;min-width:0}" +
        ".wb-cd-pipecard.is-running{border-color:#7dd3fc;background:#fff}" +
        ".wb-cd-pipecard.is-done{background:#f8fafc}" +
        ".wb-cd-pipecard.is-error{border-color:#fecaca;background:#fef2f2}" +
        ".wb-cd-pipecard-h{display:flex;align-items:center;gap:6px;padding:10px 10px;font-size:12px;font-weight:600;color:#111827;min-width:0}" +
        ".wb-cd-pipecard-h .ttl{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        ".wb-cd-pipecard-h .hint{margin-left:auto;font-weight:500;font-size:10px;color:#64748b;flex:none}" +
        ".wb-cd-pipecard.is-done .hint{color:#047857}" +
        ".wb-cd-pipecard.is-running .hint{color:#0369a1;display:inline-flex;align-items:center}" +
        ".wb-cd-pipecard .wb-cd-ico{background:#e5e7eb;color:#6b7280}" +
        ".wb-cd-pipecard.is-done .wb-cd-ico{background:#d1fae5;color:#047857}" +
        ".wb-cd-pipecard.is-running .wb-cd-ico{background:#dcfce7;color:#15803d}" +
        ".wb-cd-stepcard{border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc;overflow:hidden}" +
        ".wb-cd-stepcard-h{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:12px;font-weight:600;color:#111827}" +
        ".wb-cd-stepcard-h .hint{margin-left:auto;font-weight:500;color:#64748b;font-size:11px}" +
        ".wb-cd-stepcard-b{margin:0;padding:0 12px 10px;font:12px/1.5 inherit;color:#475569;white-space:pre-wrap;max-height:88px;overflow:auto}" +
        ".wb-cd-job{border-color:#c7d2fe}" +
        ".wb-cd-stepcard .wb-cd-ico{background:#d1fae5;color:#047857}" +
        ".wb-cr-sum{font-size:12px;color:#4b5563;margin:0 0 8px}" +
        ".wb-cr-kv{display:grid;grid-template-columns:4.5em 1fr;gap:4px 10px;margin:0 0 10px;font-size:12px}" +
        ".wb-cr-kv dt{margin:0;color:#94a3b8;font-weight:600}" +
        ".wb-cr-kv dd{margin:0;color:#334155;word-break:break-all}" +
        ".wb-cr-kv a{color:#0f766e;text-decoration:none}" +
        ".wb-cr-kv a:hover{text-decoration:underline}" +
        ".wb-cr-units{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px;max-height:140px;overflow:auto}" +
        ".wb-cr-unit{display:inline-flex;align-items:center;gap:4px;border:1px solid #e2e8f0;background:#f8fafc;border-radius:999px;padding:3px 9px;font-size:11px;color:#334155}" +
        ".wb-cr-unit .k{color:#94a3b8;font-size:10px}" +
        ".wb-cr-note{font-size:11px;color:#64748b;margin:0 0 8px;line-height:1.45}" +
        ".wb-cr-done-banner{display:flex;align-items:flex-start;gap:10px;border-radius:10px;padding:10px 12px;margin:0 0 12px;font-size:13px;line-height:1.45}" +
        ".wb-cr-done-banner.ok{color:#065f46;background:#ecfdf5;border:1px solid #a7f3d0}" +
        ".wb-cr-done-banner.warn{color:#92400e;background:#fffbeb;border:1px solid #fcd34d}" +
        ".wb-cr-done-icon{font-size:16px;line-height:1;font-weight:700;flex-shrink:0}" +
        ".wb-cr-msg{border:1px solid #e5e7eb;border-radius:8px;padding:8px 10px;font-size:12px;color:#334155;background:#f8fafc;white-space:pre-wrap;margin:0 0 10px}";
      document.head.appendChild(s);
    }

    function readMeta(block) {
      if (!block || !("kind" in block)) return null;
      var meta = block.meta;
      if (!meta || typeof meta !== "object") return null;
      var wb = meta.wb;
      if (!wb || typeof wb !== "object") return null;
      return wb;
    }

    /** 展开 ~；去掉尾部 /（根路径除外）。 */
    function expandHomePath(p, home) {
      var s = String(p || "").trim();
      if (!s) return "";
      var hm = String(home || "").trim().replace(/\/+$/, "");
      if (s === "~" && hm) return hm;
      if (s.indexOf("~/") === 0 && hm) s = hm + s.slice(1);
      if (s.length > 1) s = s.replace(/\/+$/, "");
      return s;
    }

    function pathsEqual(a, b, home) {
      var x = expandHomePath(a, home);
      var y = expandHomePath(b, home);
      if (!x || !y) return false;
      return x === y;
    }

    /**
     * DSH 当前工作区绝对路径（侧栏已选目录 = session cwd）。
     * tool.call.toolview 的 props.cwd；必要时再读 useSessions。
     */
    function resolveDshCwd(props) {
      if (!props) return "";
      var direct = String(props.cwd || "").trim();
      if (direct) return expandHomePath(direct, props.home);
      try {
        if (typeof props.useSessions === "function" && props.sessionId) {
          var cwd = props.useSessions(function (s) {
            var row = s && s.byId && s.byId[props.sessionId];
            return row && row.cwd;
          });
          if (cwd) return expandHomePath(cwd, props.home);
        }
      } catch (e) {}
      return "";
    }

    /** 初始工程路径：优先 DSH 已选工作区，其次工具卡/引擎带回的 workspace。 */
    function initialWorkspace(props, ui) {
      var dsh = resolveDshCwd(props);
      var fromUi = String((ui && ui.workspace) || "").trim();
      return dsh || fromUi || "";
    }

    function textFromContentBlocks(content) {
      if (!Array.isArray(content)) return "";
      return content
        .map(function (c) {
          if (!c) return "";
          if (c.type === "text" || c.kind === "text") return String(c.text || "");
          return "";
        })
        .filter(Boolean)
        .join("\n")
        .trim();
    }

    /** 从 tool call argsRaw 取出 message / requirement。 */
    function toolArgsMessage(block) {
      if (!block) return "";
      var raw = "";
      if (typeof block.argsRaw === "string") raw = block.argsRaw;
      else if (block.call && typeof block.call.argsRaw === "string") raw = block.call.argsRaw;
      if (!raw) return "";
      try {
        var o = JSON.parse(raw);
        return String((o && (o.message || o.requirement)) || "").trim();
      } catch (e) {
        return "";
      }
    }

    /** 会话里最近一条用户原话（Agent 未传 message 时兜底预填）。 */
    function lastUserUtterance(props) {
      try {
        if (!props || typeof props.useSession !== "function") return "";
        var text = props.useSession(function (s) {
          var list =
            (s && Array.isArray(s.nodes) && s.nodes) ||
            (s && s.chat && s.chat.legacy && Array.isArray(s.chat.legacy.nodes) && s.chat.legacy.nodes) ||
            null;
          if (!list) return "";
          for (var i = list.length - 1; i >= 0; i--) {
            var n = list[i];
            if (n && n.kind === "user") return textFromContentBlocks(n.content);
          }
          return "";
        });
        return String(text || "").trim();
      } catch (e) {
        return "";
      }
    }

    /** 原始写码诉求：ui → 工具参数 → 用户刚发的那句话。 */
    function initialRequirement(props, ui) {
      var fromUi = String((ui && (ui.requirement || ui.original_goal)) || "").trim();
      if (fromUi) return fromUi;
      var fromArgs = toolArgsMessage(props && props.block);
      if (fromArgs) return fromArgs;
      return lastUserUtterance(props) || "";
    }

    function WorkspaceMismatchHint(hintProps) {
      var dshCwd = hintProps.dshCwd;
      var workspace = hintProps.workspace;
      var home = hintProps.home;
      var onUseDsh = hintProps.onUseDsh;
      if (!dshCwd) {
        return h(
          "p",
          { className: "wb-cr-dsh" },
          "未检测到侧栏工作区路径；请先在左侧选择工作区，或手动填写/浏览目录。",
        );
      }
      var mismatch =
        !!String(workspace || "").trim() && !pathsEqual(workspace, dshCwd, home);
      return h(
        "div",
        null,
        h(
          "p",
          { className: "wb-cr-dsh" },
          "当前工作区：",
          h("code", null, dshCwd),
          mismatch ? null : "（已默认填入，可改）",
        ),
        mismatch
          ? h(
              "div",
              { className: "wb-cr-warn" },
              "填写目录与侧栏工作区不一致。将按上方输入路径执行，请确认是否搞错工程。",
              onUseDsh
                ? h(
                    "div",
                    { style: { marginTop: 8 } },
                    h(
                      "button",
                      {
                        type: "button",
                        className: "wb-cr-btn",
                        onClick: onUseDsh,
                      },
                      "改用当前工作区",
                    ),
                  )
                : null,
            )
          : null,
      );
    }

    var CR_UI_REV = "2026-09-10o-cr-session";
    var CR_PERSIST_VER = 1;
    var CR_PERSIST_MAX_REPORT = 100000;

    function crBlockCallId(block, callIdProp) {
      if (callIdProp != null && String(callIdProp).trim()) return String(callIdProp).trim();
      if (!block) return "";
      var nested = block.call && typeof block.call === "object" ? block.call : null;
      return String(
        block.callId ||
          block.toolCallId ||
          (nested && (nested.callId || nested.toolCallId || nested.id)) ||
          block.id ||
          "",
      ).trim();
    }

    function crBlockSessionId(block, sessionId) {
      return String(
        sessionId ||
          (block &&
            (block.threadId ||
              block.thread_id ||
              block.sessionId ||
              block.session_id ||
              block.conversationId ||
              "")) ||
          "",
      ).trim();
    }

    function crPersistKey(block, sessionId, callIdProp) {
      var callId = crBlockCallId(block, callIdProp);
      var sid = crBlockSessionId(block, sessionId);
      if (callId && sid) return "wb-cr-card:" + sid + ":" + callId;
      if (callId) return "wb-cr-card:call:" + callId;
      if (sid) return "wb-cr-card:session:" + sid + ":lone";
      return "wb-cr-card:anon";
    }

    function crPersistKeyAliases(block, sessionId, callIdProp) {
      var callId = crBlockCallId(block, callIdProp);
      var sid = crBlockSessionId(block, sessionId);
      var keys = [crPersistKey(block, sessionId, callIdProp)];
      if (callId) {
        keys.push("wb-cr-card:call:" + callId, "wb-cr-card:block:" + callId);
        if (sid) keys.push("wb-cr-card:" + sid + ":" + callId);
      } else if (sid) {
        keys.push("wb-cr-card:" + sid, "wb-cr-card:session:" + sid + ":lone");
      } else {
        keys.push("wb-cr-card:anon");
      }
      var uniq = [];
      var seen = {};
      keys.forEach(function (k) {
        if (!k || seen[k]) return;
        seen[k] = true;
        uniq.push(k);
      });
      return uniq;
    }

    function crPersistBelongsToCall(saved, callId) {
      if (!saved || typeof saved !== "object") return false;
      var cid = String(callId || "").trim();
      if (!cid) return false;
      return String(saved.callId || "").trim() === cid;
    }

    /** 本 callId 已有 files/running/done 则恢复；新 begin 停选目录。 */
    function crPickMustStayPick(wb, ui, saved, callId) {
      var cid = String(callId || "").trim();
      if (saved && cid && crPersistBelongsToCall(saved, callId)) {
        var phase = String(saved.phase || "");
        if (phase === "done" || phase === "running" || phase === "files") return false;
      }
      var isPick =
        (ui && String(ui.kind || "") === "pick") || (wb && wb.t === "cr-pick");
      if (!isPick && wb && wb.t && String(wb.t).indexOf("cr-") === 0 && wb.t !== "cr-pick") {
        return false;
      }
      if (!isPick && wb && wb.t) return false;
      if (!saved) return true;
      if (!cid) return true;
      return !crPersistBelongsToCall(saved, callId);
    }

    function crPersistClip(text, maxLen) {
      var s = String(text || "");
      if (!s) return "";
      var n = maxLen || CR_PERSIST_MAX_REPORT;
      return s.length > n ? s.slice(-n) : s;
    }

    function crPersistNormalize(o) {
      if (!o || typeof o !== "object") return null;
      if (Number(o.v || 0) < 1) return null;
      return o;
    }

    function crPersistLoad(key) {
      try {
        var raw = localStorage.getItem(key);
        if (!raw) return null;
        return crPersistNormalize(JSON.parse(raw));
      } catch (e) {
        return null;
      }
    }

    function crPersistLoadForCard(block, sessionId, callIdProp) {
      try {
        var callId = crBlockCallId(block, callIdProp);
        var key = crPersistKey(block, sessionId, callIdProp);
        var aliases = crPersistKeyAliases(block, sessionId, callIdProp);
        for (var i = 0; i < aliases.length; i++) {
          var hit = crPersistLoad(aliases[i]);
          if (
            hit &&
            crPersistBelongsToCall(hit, callId) &&
            (hit.phase === "done" || hit.phase === "running" || hit.phase === "files")
          ) {
            return { key: key, saved: hit };
          }
        }
        return { key: key, saved: null };
      } catch (eLoad) {
        return { key: crPersistKey(block, sessionId, callIdProp), saved: null };
      }
    }

    function crPersistSave(key, data) {
      try {
        var prev = null;
        try {
          prev = JSON.parse(localStorage.getItem(key) || "null");
        } catch (ePrev) {}
        if (
          prev &&
          Number(prev.v || 0) >= 1 &&
          prev.phase === "done" &&
          data &&
          data.phase === "dir" &&
          !data.forceReset
        ) {
          return;
        }
        var payload = Object.assign({ v: CR_PERSIST_VER, at: Date.now() }, data || {});
        if (prev && Number(prev.v || 0) >= 1 && (payload.phase === "done" || payload.phase === "running")) {
          if (!payload.report && prev.report) payload.report = prev.report;
          if (!payload.log && prev.log) payload.log = prev.log;
        }
        payload.report = crPersistClip(payload.report, CR_PERSIST_MAX_REPORT);
        payload.log = crPersistClip(payload.log, 40000);
        localStorage.setItem(key, JSON.stringify(payload));
      } catch (e0) {}
    }

    function crPersistSaveCard(block, sessionId, callIdProp, data) {
      var callId = crBlockCallId(block, callIdProp) || (data && data.callId) || "";
      var aliases = crPersistKeyAliases(block, sessionId, callIdProp);
      var payload = Object.assign({}, data || {}, {
        callId: callId,
        sessionId: crBlockSessionId(block, sessionId) || (data && data.sessionId) || "",
      });
      aliases.forEach(function (k) {
        crPersistSave(k, payload);
      });
      if (callId) {
        var sid = crBlockSessionId(block, sessionId);
        ["wb-cr-card:anon"]
          .concat(sid ? ["wb-cr-card:" + sid, "wb-cr-card:session:" + sid + ":lone"] : [])
          .forEach(function (sharedKey) {
            try {
              var old = crPersistLoad(sharedKey);
              if (old && (old.phase === "done" || old.phase === "running")) {
                localStorage.removeItem(sharedKey);
              }
            } catch (eClr) {}
          });
      }
      return aliases[0];
    }

    function crPersistClearCard(block, sessionId, callIdProp) {
      crPersistKeyAliases(block, sessionId, callIdProp).forEach(function (k) {
        try {
          localStorage.removeItem(k);
        } catch (e1) {}
      });
    }

    function CodeReviewBeginCard(props) {
      ensureCss();
      var block = props.block;
      var toolCallId = String(props.callId || crBlockCallId(block, "") || "").trim();
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var dshCwd = resolveDshCwd(props);
      var persistBoot = useMemo(
        function () {
          return crPersistLoadForCard(block, props.sessionId, toolCallId);
        },
        [block, props.sessionId, toolCallId],
      );
      var bootSavedRaw =
        persistBoot.saved && crPersistBelongsToCall(persistBoot.saved, toolCallId)
          ? persistBoot.saved
          : null;
      var bootSaved =
        bootSavedRaw && !crPickMustStayPick(wb, ui, bootSavedRaw, toolCallId) ? bootSavedRaw : null;

      var _phase = useState(function () {
        return (bootSaved && bootSaved.phase) || "dir";
      }); // dir | files | running | done
      var phase = _phase[0];
      var setPhase = _phase[1];
      var _ws = useState(function () {
        return (bootSaved && bootSaved.workspace) || initialWorkspace(props, ui);
      });
      var workspace = _ws[0];
      var setWorkspace = _ws[1];
      var _scope = useState(function () {
        return (bootSaved && bootSaved.scope) || String(ui.scope || "");
      });
      var scope = _scope[0];
      var setScope = _scope[1];
      var _focus = useState(function () {
        return (bootSaved && bootSaved.focus) || String(ui.focus || "");
      });
      var focus = _focus[0];
      var setFocus = _focus[1];
      var _err = useState(function () {
        return (bootSaved && bootSaved.err) || "";
      });
      var err = _err[0];
      var setErr = _err[1];
      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _files = useState(function () {
        return (bootSaved && bootSaved.files) || [];
      });
      var files = _files[0];
      var setFiles = _files[1];
      var _sample = useState(function () {
        return (bootSaved && bootSaved.sample) || [];
      });
      var sample = _sample[0];
      var setSample = _sample[1];
      var _selected = useState(function () {
        return (bootSaved && bootSaved.selected) || {};
      });
      var selected = _selected[0];
      var setSelected = _selected[1];
      var _count = useState(function () {
        return (bootSaved && bootSaved.count) || 0;
      });
      var count = _count[0];
      var setCount = _count[1];
      var _log = useState(function () {
        return (bootSaved && bootSaved.log) || "";
      });
      var log = _log[0];
      var setLog = _log[1];
      var _report = useState(function () {
        return (bootSaved && bootSaved.report) || "";
      });
      var report = _report[0];
      var setReport = _report[1];
      var _pathTicket = useState(function () {
        return (bootSaved && bootSaved.pathTicket) || "";
      });
      var pathTicket = _pathTicket[0];
      var setPathTicket = _pathTicket[1];

      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];

      function crSnapshotPersist(extra) {
        if (phase === "dir" && !(extra && extra.forceReset)) return;
        crPersistSaveCard(
          block,
          props.sessionId,
          toolCallId,
          Object.assign(
            {
              phase: phase,
              callId: toolCallId,
              sessionId: crBlockSessionId(block, props.sessionId),
              workspace: workspace,
              scope: scope,
              focus: focus,
              files: files,
              sample: sample,
              selected: selected,
              count: count,
              log: log,
              report: report,
              pathTicket: pathTicket,
              err: err,
            },
            extra || {},
          ),
        );
      }

      function crResetCard() {
        crPersistClearCard(block, props.sessionId, toolCallId);
        setPhase("dir");
        setErr("");
        setLog("");
        setReport("");
        setFiles([]);
        setSelected({});
        setPathTicket("");
      }

      useEffect(
        function () {
          if (
            phase === "files" ||
            phase === "running" ||
            phase === "done"
          ) {
            crSnapshotPersist();
          }
        },
        [phase, workspace, scope, focus, files, selected, count, log, report, pathTicket, err],
      );

      useEffect(
        function () {
          if (dshCwd && !String(workspace || "").trim()) setWorkspace(dshCwd);
        },
        [dshCwd],
      );

      if (!wb || wb.t !== "cr-pick") {
        var out =
          block && "kind" in block
            ? (block.content || [])
                .map(function (c) {
                  return c && c.type === "text" ? c.text : "";
                })
                .filter(Boolean)
                .join("\n")
            : "审码进行中…";
        return h(
          "div",
          { className: "wb-cr" },
          h("div", { className: "wb-cr-head" }, h("span", { className: "wb-cr-badge" }, "代码审核"), h("span", { className: "wb-cr-hint" }, "结果")),
          h("div", { className: "wb-cr-body" }, h("pre", { className: "wb-cr-progress", style: { margin: 0 } }, out || "（无详情）")),
        );
      }

      function browse() {
        setBusy(true);
        setErr("请在弹出的系统对话框中选择目录（若看不到，请看 Dock / 其它窗口后面）");
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = setTimeout(function () {
          try {
            if (ctrl) ctrl.abort();
          } catch (e0) {}
        }, 120000);
        pickLocalFolder("选择要审核的工程目录", ctrl ? ctrl.signal : undefined)
          .then(function (d) {
            if (d && d.ok && d.path) {
              setWorkspace(d.path);
              setErr("");
            } else if (d && d.error && d.error !== "已取消选择") {
              setErr(d.error || "选文件夹失败");
            } else {
              setErr("");
            }
          })
          .catch(function (e) {
            setErr(
              e && e.name === "AbortError"
                ? "选择超时：请点常用路径或手动粘贴目录"
                : "浏览失败：" + (e && e.message ? e.message : e),
            );
          })
          .finally(function () {
            clearTimeout(timer);
            setBusy(false);
          });
      }

      function goList() {
        var local_path = String(workspace || "").trim();
        if (!local_path) {
          setErr("请填写或浏览选择本机工程目录");
          return;
        }
        setBusy(true);
        setErr("正在列出可审文件…");
        fetch(engineBase() + "/api/code-review/list", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ local_path: local_path, scope: String(scope || "").trim() }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (!d || !d.ok) {
              setErr((d && (d.detail || d.reply)) || "列文件失败");
              setBusy(false);
              return;
            }
            var list = Array.isArray(d.files) ? d.files : [];
            var samp = Array.isArray(d.sample_selected) ? d.sample_selected : [];
            var paths = [];
            var seen = {};
            var sel = {};
            function add(p, check) {
              var rel = typeof p === "string" ? p : (p && p.path) || "";
              if (!rel || seen[rel]) return;
              seen[rel] = true;
              paths.push(rel);
              if (check) sel[rel] = true;
            }
            samp.forEach(function (p) {
              add(p, true);
            });
            list.forEach(function (p) {
              add(p, false);
            });
            setFiles(paths.slice(0, 80));
            setSample(
              samp
                .map(function (p) {
                  return typeof p === "string" ? p : (p && p.path) || "";
                })
                .filter(Boolean),
            );
            setSelected(sel);
            setCount(d.count || paths.length);
            if (d.local_path) setWorkspace(String(d.local_path));
            setPathTicket(String(d.path_ticket || ""));
            setPhase("files");
            setErr("");
            setBusy(false);
          })
          .catch(function (e) {
            setErr("列文件失败：" + (e && e.message ? e.message : e));
            setBusy(false);
          });
      }

      function toggle(rel) {
        setSelected(function (prev) {
          var next = Object.assign({}, prev);
          if (next[rel]) delete next[rel];
          else next[rel] = true;
          return next;
        });
      }

      function selectedList() {
        return Object.keys(selected).filter(function (k) {
          return selected[k];
        });
      }

      function runReview(fileList) {
        var local_path = String(workspace || "").trim();
        var ticket = String(pathTicket || "").trim();
        if (!ticket) {
          setErr("缺少 path_ticket：请重新列出文件后再开始审核");
          return;
        }
        setPhase("running");
        setBusy(true);
        setErr("");
        setLog("正在审核…\n");
        setReport("");
        // token.text 是引擎累计全文（非增量）；错误拼接会平方膨胀卡死页面
        var reportAcc = "";
        var logAcc = "正在审核…\n";
        var flushTimer = null;
        var finished = false;
        function flushUi() {
          flushTimer = null;
          setLog(logAcc);
          setReport(reportAcc);
        }
        function scheduleFlush() {
          if (flushTimer != null) return;
          flushTimer = setTimeout(flushUi, 150);
        }
        fetch(engineBase() + "/api/code-review/run/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({
            local_path: local_path,
            scope: String(scope || "").trim(),
            focus: String(focus || "").trim(),
            files: fileList && fileList.length ? fileList : null,
            path_ticket: ticket,
          }),
        })
          .then(function (r) {
            if (!r.ok) {
              return r
                .json()
                .catch(function () {
                  return {};
                })
                .then(function (j) {
                  finished = true;
                  setPhase("done");
                  setBusy(false);
                  setErr((j && (j.detail || j.reply)) || "HTTP " + r.status);
                });
            }
            var reader = r.body.getReader();
            var decoder = new TextDecoder();
            var pending = "";
            function onEvent(ev) {
              if (!ev || typeof ev !== "object") return;
              if (ev.type === "step" || ev.type === "status") {
                var line =
                  ev.title || ev.detail || ev.text || ev.id || "";
                if (line) {
                  logAcc += line + "\n";
                  scheduleFlush();
                }
              } else if (ev.type === "token") {
                // 优先用累计全文覆盖；仅有 delta 时才追加
                if (typeof ev.text === "string") reportAcc = ev.text;
                else if (typeof ev.delta === "string") reportAcc += ev.delta;
                scheduleFlush();
              } else if (ev.type === "done" || ev.type === "error" || ev.ok === true || ev.ok === false) {
                finished = true;
                if (flushTimer != null) {
                  clearTimeout(flushTimer);
                  flushTimer = null;
                }
                if (ev.reply) reportAcc = ev.reply;
                flushUi();
                setPhase("done");
                setBusy(false);
                if (ev.ok === false || ev.type === "error") {
                  setErr(ev.detail || ev.message || ev.reply || "审核失败");
                } else {
                  setErr("");
                }
              }
            }
            function pump() {
              return reader.read().then(function (res) {
                if (res.done) {
                  if (flushTimer != null) {
                    clearTimeout(flushTimer);
                    flushTimer = null;
                  }
                  flushUi();
                  if (!finished) {
                    setBusy(false);
                    setPhase("done");
                    if (!reportAcc) setErr("流式结束但未收到完成事件");
                  }
                  return;
                }
                pending += decoder.decode(res.value, { stream: true });
                var chunks = pending.split("\n\n");
                pending = chunks.pop() || "";
                chunks.forEach(function (block) {
                  block.split("\n").forEach(function (line) {
                    if (line.indexOf("data:") !== 0) return;
                    var raw = line.slice(5).trim();
                    if (!raw) return;
                    try {
                      onEvent(JSON.parse(raw));
                    } catch (e1) {}
                  });
                });
                return pump();
              });
            }
            return pump();
          })
          .catch(function (e) {
            finished = true;
            setPhase("done");
            setBusy(false);
            setErr("请求失败：" + (e && e.message ? e.message : e));
          });
      }

      if (phase === "running" || phase === "done") {
        // 进行中只展示尾部，避免超长报告反复重排卡死
        var reportView = report;
        if (phase === "running" && report && report.length > 3500) {
          reportView =
            "…（报告生成中，已 " +
            report.length +
            " 字，完成后显示全文）\n\n" +
            report.slice(-2800);
        }
        return h(
          "div",
          { className: "wb-cr" },
          h(
            "div",
            { className: "wb-cr-head" },
            h("span", { className: "wb-cr-badge" }, "代码审核"),
            h("span", { className: "wb-cr-hint" }, (phase === "running" ? "进行中（勿重复点击）" : "完成") + " · " + CR_UI_REV),
          ),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, "路径：" + workspace),
            log ? h("pre", { className: "wb-cr-progress" }, log) : null,
            reportView
              ? h("pre", { className: "wb-cr-progress", style: { maxHeight: phase === "done" ? "420px" : "220px" } }, reportView)
              : phase === "running"
                ? h("p", { className: "wb-cr-sum" }, "正在审查源码，请稍候…")
                : null,
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            phase === "done"
              ? h(
                  "div",
                  { className: "wb-cr-actions" },
                  h(
                    "button",
                    {
                      type: "button",
                      className: "wb-cr-btn",
                      onClick: crResetCard,
                    },
                    "重新选择",
                  ),
                )
              : null,
          ),
        );
      }

      if (phase === "files") {
        var sampleSet = {};
        sample.forEach(function (p) {
          sampleSet[p] = true;
        });
        return h(
          "div",
          { className: "wb-cr" },
          h(
            "div",
            { className: "wb-cr-head" },
            h("span", { className: "wb-cr-badge" }, "代码审核"),
            h("span", { className: "wb-cr-hint" }, "勾选文件"),
          ),
          h(
            "div",
            { className: "wb-cr-body" },
            h(
              "p",
              { className: "wb-cr-sum" },
              workspace + " · 共 " + count + " 个可审，展示 " + files.length,
            ),
            h(
              "div",
              { className: "wb-cr-actions", style: { marginTop: 0 } },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    var next = {};
                    sample.forEach(function (p) {
                      next[p] = true;
                    });
                    setSelected(next);
                  },
                },
                "勾选默认抽样",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    var next = {};
                    files.forEach(function (p) {
                      next[p] = true;
                    });
                    setSelected(next);
                  },
                },
                "全选当前列表",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    setSelected({});
                  },
                },
                "清空",
              ),
            ),
            h(
              "div",
              { className: "wb-cr-files" },
              files.length
                ? files.map(function (rel) {
                    return h(
                      "label",
                      { key: rel, className: "wb-cr-file" },
                      h("input", {
                        type: "checkbox",
                        checked: !!selected[rel],
                        onChange: function () {
                          toggle(rel);
                        },
                      }),
                      h("span", null, rel + (sampleSet[rel] ? " · 抽样" : "")),
                    );
                  })
                : h("p", { className: "wb-cr-sum" }, "没有可审文件，可用默认抽样开审。"),
            ),
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  disabled: busy,
                  onClick: function () {
                    setPhase("dir");
                    setErr("");
                  },
                },
                "返回改目录",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn primary",
                  disabled: busy,
                  onClick: function () {
                    var sel = selectedList();
                    if (!sel.length) {
                      setErr("请至少勾选一个文件，或点「不选文件·默认抽样」");
                      return;
                    }
                    runReview(sel);
                  },
                },
                "开始审核所选",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn primary",
                  disabled: busy,
                  onClick: function () {
                    runReview(null);
                  },
                },
                "不选文件·默认抽样",
              ),
            ),
          ),
        );
      }

      // phase === dir
      return h(
        "div",
        { className: "wb-cr" },
        h(
          "div",
          { className: "wb-cr-head" },
          h("span", { className: "wb-cr-badge" }, "代码审核"),
          h("span", { className: "wb-cr-hint" }, "选择目录 · 下一步勾选文件 · " + CR_UI_REV),
        ),
        h(
          "div",
          { className: "wb-cr-body" },
          h("p", { className: "wb-cr-sum" }, "在主聊天工具卡里选目录与文件（不是答题壳、也不是浮层面板）。"),
          h(WorkspaceMismatchHint, {
            dshCwd: dshCwd,
            workspace: workspace,
            home: props.home,
            onUseDsh: function () {
              setWorkspace(dshCwd);
            },
          }),
          h("label", { className: "wb-cr-label" }, "本机工程目录"),
          h(
            "div",
            { className: "wb-cr-row" },
            h("input", {
              className: "wb-cr-input",
              value: workspace,
              placeholder: "/Users/你/项目",
              onChange: function (e) {
                setWorkspace(e.target.value);
              },
            }),
            h(
              "button",
              { type: "button", className: "wb-cr-btn", disabled: busy, onClick: browse },
              busy ? "选择中…" : "浏览…",
            ),
          ),
          suggestions.length
            ? h(
                "div",
                { className: "wb-cr-chips" },
                suggestions.map(function (s, i) {
                  var p = typeof s === "string" ? s : (s && s.path) || "";
                  var lab = typeof s === "object" && s.label ? s.label + " · " : "";
                  if (!p) return null;
                  return h(
                    "button",
                    {
                      key: i + p,
                      type: "button",
                      className: "wb-cr-chip",
                      title: p,
                      onClick: function () {
                        setWorkspace(p);
                      },
                    },
                    lab + p,
                  );
                }),
              )
            : null,
          h("label", { className: "wb-cr-label" }, "范围（可选，相对子路径）"),
          h("input", {
            className: "wb-cr-input",
            style: { width: "100%", marginBottom: 10, boxSizing: "border-box" },
            value: scope,
            placeholder: "如 frontend/src",
            onChange: function (e) {
              setScope(e.target.value);
            },
          }),
          h("label", { className: "wb-cr-label" }, "审查重点（可选）"),
          h("input", {
            className: "wb-cr-input",
            style: { width: "100%", marginBottom: 10, boxSizing: "border-box" },
            value: focus,
            placeholder: "如 SQL 注入、权限校验",
            onChange: function (e) {
              setFocus(e.target.value);
            },
          }),
          err ? h("p", { className: "wb-cr-err" }, err) : null,
          h(
            "div",
            { className: "wb-cr-actions" },
            h(
              "button",
              {
                type: "button",
                className: "wb-cr-btn primary",
                disabled: busy,
                onClick: goList,
              },
              busy ? "列出文件…" : "下一步：选文件",
            ),
          ),
        ),
      );
    }

    function ccTailName(path) {
      var s = String(path || "").replace(/\\/g, "/").replace(/\/+$/, "");
      var slash = s.lastIndexOf("/");
      return slash >= 0 ? s.slice(slash + 1) : s || "—";
    }

    function ccRedactRemoteUrl(url) {
      var u = String(url || "").trim();
      if (!u) return "";
      try {
        if (/^https?:\/\//i.test(u)) {
          var parsed = new URL(u);
          if (parsed.username || parsed.password) {
            parsed.username = "";
            parsed.password = "";
            return parsed.toString();
          }
        }
      } catch (_e) {}
      return u.replace(/^(https?:\/\/)([^/@\s]+)@/i, "$1");
    }

    function ccSanitizeCommitDetail(detail) {
      if (!detail || typeof detail !== "object") return detail;
      var out = Object.assign({}, detail);
      if (out.push && typeof out.push === "object") {
        out.push = Object.assign({}, out.push, {
          remote_url: ccRedactRemoteUrl(out.push.remote_url || ""),
        });
      }
      return out;
    }

    function ccCommitRemoteLabel(didPush, pushInfo) {
      if (!didPush) return "仅本地提交（未 push）";
      if (pushInfo && pushInfo.ok) {
        var remote = String(pushInfo.remote || "origin");
        var url = ccRedactRemoteUrl(pushInfo.remote_url || "");
        return url ? "已推送到 " + remote + " · " + url : "已推送到 " + remote;
      }
      return "推送失败";
    }

    var CC_PERSIST_VER = 1;
    var CC_UI_REV = "2026-09-10o-cc-contract";

    function ccBlockCallId(block, callIdProp) {
      if (callIdProp != null && String(callIdProp).trim()) return String(callIdProp).trim();
      if (!block) return "";
      var nested = block.call && typeof block.call === "object" ? block.call : null;
      return String(
        block.callId ||
          block.toolCallId ||
          (nested && (nested.callId || nested.toolCallId || nested.id)) ||
          block.id ||
          "",
      ).trim();
    }

    function ccBlockSessionId(block, sessionId) {
      return String(
        sessionId ||
          (block &&
            (block.threadId ||
              block.thread_id ||
              block.sessionId ||
              block.session_id ||
              block.conversationId ||
              "")) ||
          "",
      ).trim();
    }

    function ccPersistKey(block, sessionId, callIdProp) {
      var callId = ccBlockCallId(block, callIdProp);
      var sid = ccBlockSessionId(block, sessionId);
      if (callId && sid) return "wb-cc-card:" + sid + ":" + callId;
      if (callId) return "wb-cc-card:call:" + callId;
      if (sid) return "wb-cc-card:session:" + sid + ":lone";
      return "wb-cc-card:anon";
    }

    function ccPersistKeyAliases(block, sessionId, callIdProp) {
      var callId = ccBlockCallId(block, callIdProp);
      var sid = ccBlockSessionId(block, sessionId);
      var keys = [ccPersistKey(block, sessionId, callIdProp)];
      if (callId) {
        keys.push("wb-cc-card:call:" + callId, "wb-cc-card:block:" + callId);
        if (sid) keys.push("wb-cc-card:" + sid + ":" + callId);
      } else if (sid) {
        keys.push("wb-cc-card:" + sid, "wb-cc-card:session:" + sid + ":lone");
      } else {
        keys.push("wb-cc-card:anon");
      }
      var uniq = [];
      var seen = {};
      keys.forEach(function (k) {
        if (!k || seen[k]) return;
        seen[k] = true;
        uniq.push(k);
      });
      return uniq;
    }

    function ccPersistBelongsToCall(saved, callId) {
      if (!saved || typeof saved !== "object") return false;
      var cid = String(callId || "").trim();
      if (!cid) return false;
      var savedCid = String(saved.callId || "").trim();
      if (!savedCid) return false;
      return savedCid === cid;
    }

    /**
     * 工具 meta 永远是 cc-pick，不能据此判定「必须回选目录」。
     * 仅当：无本 callId 绑定进度，且当前确是 pick 卡 → 才停在 HITL。
     */
    function ccPickMustStayPick(wb, ui, saved, callId) {
      var cid = String(callId || "").trim();
      if (saved && cid && ccPersistBelongsToCall(saved, callId)) {
        var phase = String(saved.phase || "");
        if (
          phase === "done" ||
          phase === "confirm" ||
          phase === "blocked" ||
          phase === "files" ||
          phase === "gating" ||
          saved.jobId
        ) {
          return false;
        }
      }
      var isPick =
        (ui && String(ui.kind || "") === "pick") ||
        (wb && wb.t === "cc-pick");
      if (!isPick && wb && wb.t && String(wb.t).indexOf("cc-") === 0 && wb.t !== "cc-pick") {
        return false;
      }
      if (!isPick && wb && wb.t) return false;
      if (!saved) return true;
      if (!cid) return true;
      return !ccPersistBelongsToCall(saved, callId);
    }

    function ccPersistScanByCallId(callId) {
      var cid = String(callId || "").trim();
      if (!cid) return null;
      var best = null;
      try {
        for (var i = 0; i < localStorage.length; i++) {
          var k = localStorage.key(i);
          if (!k || k.indexOf("wb-cc-card:") !== 0) continue;
          var hitKey =
            k === "wb-cc-card:call:" + cid ||
            k === "wb-cc-card:block:" + cid ||
            k.slice(-cid.length - 1) === ":" + cid;
          var o = null;
          try {
            o = ccPersistNormalize(JSON.parse(localStorage.getItem(k) || "null"));
          } catch (e1) {
            continue;
          }
          if (!o) continue;
          if (!hitKey && String(o.callId || "") !== cid) continue;
          if (
            !(
              o.phase === "done" ||
              o.phase === "confirm" ||
              o.phase === "blocked" ||
              o.phase === "files" ||
              o.phase === "gating" ||
              o.jobId
            )
          ) {
            continue;
          }
          if (!best || Number(o.at || 0) > Number(best.at || 0)) best = o;
        }
      } catch (e2) {}
      return best;
    }

    function ccPersistNormalize(o) {
      if (!o || typeof o !== "object") return null;
      if (Number(o.v || 0) < 1) return null;
      return o;
    }

    function ccPersistLoad(key) {
      try {
        var raw = localStorage.getItem(key);
        if (!raw) return null;
        return ccPersistNormalize(JSON.parse(raw));
      } catch (e) {
        return null;
      }
    }

    function ccPersistLoadForCard(block, sessionId, callIdProp) {
      try {
        var callId = ccBlockCallId(block, callIdProp);
        var key = ccPersistKey(block, sessionId, callIdProp);
        var aliases = ccPersistKeyAliases(block, sessionId, callIdProp);
        for (var i = 0; i < aliases.length; i++) {
          var hit = ccPersistLoad(aliases[i]);
          if (
            hit &&
            ccPersistBelongsToCall(hit, callId) &&
            (hit.phase === "done" ||
              hit.phase === "confirm" ||
              hit.phase === "blocked" ||
              hit.phase === "files" ||
              hit.phase === "gating" ||
              hit.jobId)
          ) {
            return { key: key, saved: hit, migrateFrom: aliases[i] !== key ? aliases[i] : "" };
          }
        }
        var scanned = ccPersistScanByCallId(callId);
        if (scanned && ccPersistBelongsToCall(scanned, callId)) {
          return { key: key, saved: scanned, migrateFrom: "" };
        }
        return { key: key, saved: null };
      } catch (eLoad) {
        return { key: ccPersistKey(block, sessionId, callIdProp), saved: null };
      }
    }

    function ccPersistSave(key, data) {
      try {
        var prev = null;
        try {
          prev = JSON.parse(localStorage.getItem(key) || "null");
        } catch (ePrev) {}
        if (
          prev &&
          Number(prev.v || 0) >= 1 &&
          prev.phase === "done" &&
          data &&
          data.phase === "dir" &&
          !data.forceReset
        ) {
          return;
        }
        var payload = Object.assign({ v: CC_PERSIST_VER, at: Date.now() }, data || {});
        if (prev && Number(prev.v || 0) >= 1 && (payload.phase === "done" || prev.phase === "done")) {
          if (!payload.commitDetail && prev.commitDetail) payload.commitDetail = prev.commitDetail;
          if (!payload.result && prev.result) payload.result = prev.result;
          if (!payload.jobId && prev.jobId) payload.jobId = prev.jobId;
        }
        if (payload.commitDetail) {
          payload.commitDetail = ccSanitizeCommitDetail(payload.commitDetail);
        }
        if (payload.lastPush && typeof payload.lastPush === "object") {
          payload.lastPush = Object.assign({}, payload.lastPush, {
            remote_url: ccRedactRemoteUrl(payload.lastPush.remote_url || ""),
          });
        }
        localStorage.setItem(key, JSON.stringify(payload));
        if (payload.jobId && payload.phase === "done") {
          try {
            localStorage.setItem(
              "wb-cc-job:" + String(payload.jobId),
              JSON.stringify({
                v: CC_PERSIST_VER,
                at: Date.now(),
                jobId: payload.jobId,
                callId: payload.callId || "",
                commitDetail: payload.commitDetail || null,
                result: payload.result || "",
                lastPush: payload.lastPush,
              }),
            );
          } catch (eJob) {}
        }
      } catch (e0) {}
    }

    function ccPersistSaveCard(block, sessionId, callIdProp, data) {
      var callId = ccBlockCallId(block, callIdProp) || (data && data.callId) || "";
      var aliases = ccPersistKeyAliases(block, sessionId, callIdProp);
      var payload = Object.assign({}, data || {}, {
        callId: callId,
        sessionId: ccBlockSessionId(block, sessionId) || (data && data.sessionId) || "",
      });
      aliases.forEach(function (k) {
        ccPersistSave(k, payload);
      });
      if (callId) {
        var sid = ccBlockSessionId(block, sessionId);
        ["wb-cc-card:anon"]
          .concat(sid ? ["wb-cc-card:" + sid, "wb-cc-card:session:" + sid + ":lone"] : [])
          .forEach(function (sharedKey) {
            try {
              var old = ccPersistLoad(sharedKey);
              if (old && (old.phase === "done" || old.jobId)) {
                localStorage.removeItem(sharedKey);
              }
            } catch (eClr) {}
          });
      }
      return aliases[0];
    }

    function ccPersistClearCard(block, sessionId, callIdProp) {
      ccPersistKeyAliases(block, sessionId, callIdProp).forEach(function (k) {
        try {
          localStorage.removeItem(k);
        } catch (e1) {}
      });
    }

    function ccDetailFromEngineJob(job) {
      if (!job || typeof job !== "object") return null;
      var cr = job.commit_result || {};
      var pushInfo = cr.push || {};
      var st = String(job.status || "");
      var ok = st === "done" && !!cr.commit;
      var pushRetry =
        st === "done" &&
        !!cr.commit &&
        job.push !== false &&
        pushInfo &&
        !pushInfo.ok;
      return {
        ok: ok && !pushRetry,
        job_id: job.id,
        workspace: job.workspace,
        message: job.message || cr.message || "",
        files: job.files || cr.files || [],
        commit_result: cr,
        push_retry_needed: pushRetry,
        status: st,
      };
    }

    function CodeCommitBeginCard(props) {
      ensureCss();
      var block = props.block;
      var toolCallId = String(props.callId || ccBlockCallId(block, "") || "").trim();
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var dshCwd = resolveDshCwd(props);
      var persistBoot = useMemo(
        function () {
          return ccPersistLoadForCard(block, props.sessionId, toolCallId);
        },
        [block, props.sessionId, toolCallId],
      );
      var persistKey = persistBoot.key;
      var bootSavedRaw =
        persistBoot.saved && ccPersistBelongsToCall(persistBoot.saved, toolCallId)
          ? persistBoot.saved
          : null;
      var bootSaved = null;
      if (bootSavedRaw && !ccPickMustStayPick(wb, ui, bootSavedRaw, toolCallId)) {
        bootSaved = bootSavedRaw;
      }

      var _phase = useState(function () {
        return (bootSaved && bootSaved.phase) || "dir";
      }); // dir | files | gating | blocked | confirm | done
      var phase = _phase[0];
      var setPhase = _phase[1];
      var _ws = useState(function () {
        return (bootSaved && bootSaved.workspace) || initialWorkspace(props, ui);
      });
      var workspace = _ws[0];
      var setWorkspace = _ws[1];
      var _branch = useState(function () {
        return (bootSaved && bootSaved.branch) || String(ui.work_branch || "");
      });
      var branch = _branch[0];
      var setBranch = _branch[1];
      var _branchHint = useState(function () {
        return (bootSaved && bootSaved.branchHint) || String(ui.branch_hint || "");
      });
      var branchHint = _branchHint[0];
      var setBranchHint = _branchHint[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _files = useState(function () {
        return (bootSaved && bootSaved.files) || [];
      });
      var files = _files[0];
      var setFiles = _files[1];
      var _selected = useState(function () {
        return (bootSaved && bootSaved.selected) || {};
      });
      var selected = _selected[0];
      var setSelected = _selected[1];
      var _draft = useState(function () {
        return (bootSaved && bootSaved.draft) || "";
      });
      var draft = _draft[0];
      var setDraft = _draft[1];
      var _push = useState(function () {
        return bootSaved && bootSaved.push != null ? !!bootSaved.push : ui.default_push !== false;
      });
      var push = _push[0];
      var setPush = _push[1];
      var _jobId = useState(function () {
        return (bootSaved && bootSaved.jobId) || "";
      });
      var jobId = _jobId[0];
      var setJobId = _jobId[1];
      var _findings = useState(function () {
        return (bootSaved && bootSaved.findings) || [];
      });
      var findings = _findings[0];
      var setFindings = _findings[1];
      var _summary = useState(function () {
        return (bootSaved && bootSaved.summary) || "";
      });
      var summary = _summary[0];
      var setSummary = _summary[1];
      var _result = useState(function () {
        return (bootSaved && bootSaved.result) || "";
      });
      var result = _result[0];
      var setResult = _result[1];
      var _commitDetail = useState(function () {
        return (bootSaved && bootSaved.commitDetail) || null;
      });
      var commitDetail = _commitDetail[0];
      var setCommitDetail = _commitDetail[1];
      var _lastPush = useState(function () {
        return bootSaved && bootSaved.lastPush != null ? !!bootSaved.lastPush : true;
      });
      var lastPush = _lastPush[0];
      var setLastPush = _lastPush[1];
      var restoreOnceRef = useRef(false);

      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];

      function ccSnapshotPersist(extra) {
        if (phase === "dir" && !(extra && extra.forceReset)) return;
        var cidSave = ccResolveCallId();
        ccPersistSaveCard(
          block,
          props.sessionId,
          cidSave,
          Object.assign(
            {
              phase: phase,
              callId: cidSave,
              sessionId: ccBlockSessionId(block, props.sessionId),
              workspace: workspace,
              branch: branch,
              branchHint: branchHint,
              files: files,
              selected: selected,
              draft: draft,
              push: push,
              jobId: jobId,
              findings: findings,
              summary: summary,
              result: result,
              commitDetail: commitDetail,
              lastPush: lastPush,
            },
            extra || {},
          ),
        );
      }

      function ccResetCard() {
        ccPersistClearCard(block, props.sessionId, toolCallId);
        try {
          var jidClr = String(jobId || (commitDetail && commitDetail.job_id) || "").trim();
          if (jidClr) localStorage.removeItem("wb-cc-job:" + jidClr);
        } catch (eClr) {}
        setPhase("dir");
        setErr("");
        setResult("");
        setSummary("");
        setFindings([]);
        setCommitDetail(null);
        setJobId("");
        setFiles([]);
        setSelected({});
      }

      function ccResolveCallId() {
        return String(props.callId || ccBlockCallId(block, toolCallId) || toolCallId || "").trim();
      }

      useEffect(
        function () {
          if (
            phase === "files" ||
            phase === "confirm" ||
            phase === "blocked" ||
            phase === "done" ||
            phase === "gating"
          ) {
            ccSnapshotPersist();
          }
        },
        [
          phase,
          workspace,
          branch,
          files,
          selected,
          draft,
          push,
          jobId,
          findings,
          summary,
          result,
          commitDetail,
          lastPush,
        ],
      );

      useEffect(
        function () {
          if (restoreOnceRef.current) return;
          restoreOnceRef.current = true;
          var cid = ccResolveCallId();
          if (!cid) return;
          if (ccPickMustStayPick(wb, ui, bootSavedRaw, cid)) {
            var sidClr = ccBlockSessionId(block, props.sessionId);
            ["wb-cc-card:anon"]
              .concat(
                sidClr ? ["wb-cc-card:" + sidClr, "wb-cc-card:session:" + sidClr + ":lone"] : [],
              )
              .forEach(function (sharedKey) {
                try {
                  localStorage.removeItem(sharedKey);
                } catch (eRm) {}
              });
            return;
          }
          var saved = bootSaved;
          if (!saved || saved.phase !== "done" || !saved.jobId) return;
          if (saved.commitDetail) return;
          try {
            var snapRaw = localStorage.getItem("wb-cc-job:" + String(saved.jobId));
            if (snapRaw) {
              var snap = JSON.parse(snapRaw);
              if (snap && snap.commitDetail) {
                setCommitDetail(snap.commitDetail);
                if (snap.result) setResult(String(snap.result));
                if (snap.lastPush != null) setLastPush(!!snap.lastPush);
                return;
              }
            }
          } catch (eSnap) {}
          fetch(engineBase() + "/api/code-commit/jobs/" + encodeURIComponent(String(saved.jobId)))
            .then(function (r) {
              return r.json();
            })
            .then(function (jd) {
              if (!jd || !jd.ok || !jd.job) return;
              var rebuilt = ccDetailFromEngineJob(jd.job);
              if (!rebuilt) return;
              setCommitDetail(rebuilt);
              ccPersistSaveCard(block, props.sessionId, toolCallId, Object.assign({}, saved, {
                commitDetail: rebuilt,
                phase: "done",
              }));
            })
            .catch(function () {});
        },
        [persistKey, toolCallId],
      );

      // 目录预填（DSH 工作区 / 上次路径）时自动识别当前分支；须在任何 early return 之前挂 effect。
      useEffect(
        function () {
          if (phase === "done") return;
          var ws = String(workspace || "").trim();
          if (dshCwd && !ws) {
            setWorkspace(dshCwd);
            ws = dshCwd;
          }
          if (!ws) return;
          setBranchHint("正在识别分支…");
          fetch(engineBase() + "/api/code-commit/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ workspace: ws }),
          })
            .then(function (r) {
              return r.json();
            })
            .then(function (d) {
              if (!d || !d.ok) {
                setBranch("");
                setBranchHint((d && (d.detail || d.reply)) || "路径不可用");
                return;
              }
              setBranch(String(d.work_branch || ""));
              setBranchHint(String(d.branch_hint || (d.need_user_branch ? "请填写要提交的分支" : "") || ""));
            })
            .catch(function () {
              setBranchHint("分支识别失败，请手动填写");
            });
        },
        [dshCwd],
      );

      if (!wb || (wb.t !== "cc-pick" && String(wb.t || "").indexOf("cc-") !== 0)) {
        // 非 pick 元数据：仍尝试用 ui.kind===pick；否则展示正文
        if (!(ui && ui.kind === "pick")) {
          var out =
            block && "kind" in block
              ? (block.content || [])
                  .map(function (c) {
                    return c && c.type === "text" ? c.text : "";
                  })
                  .filter(Boolean)
                  .join("\n")
              : "提交进行中…";
          return h(
            "div",
            { className: "wb-cr" },
            h(
              "div",
              { className: "wb-cr-head" },
              h("span", { className: "wb-cr-badge" }, "提交代码"),
              h("span", { className: "wb-cr-hint" }, "结果"),
            ),
            h("div", { className: "wb-cr-body" }, h("pre", { className: "wb-cr-progress", style: { margin: 0 } }, out || "（无详情）")),
          );
        }
      }

      function refreshBranch(path) {
        var workspacePath = String(path || workspace || "").trim();
        if (!workspacePath) {
          setBranch("");
          setBranchHint("请先选择工程目录");
          return;
        }
        setBranchHint("正在识别分支…");
        fetch(engineBase() + "/api/code-commit/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace: workspacePath }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (!d || !d.ok) {
              setBranch("");
              setBranchHint((d && (d.detail || d.reply)) || "路径不可用");
              return;
            }
            setBranch(String(d.work_branch || ""));
            setBranchHint(String(d.branch_hint || (d.need_user_branch ? "请填写要提交的分支" : "") || ""));
          })
          .catch(function () {
            setBranchHint("分支识别失败，请手动填写");
          });
      }

      function browse() {
        setBusy(true);
        setErr("请在弹出的系统对话框中选择目录（若看不到，请看 Dock / 其它窗口后面）");
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = setTimeout(function () {
          try {
            if (ctrl) ctrl.abort();
          } catch (e0) {}
        }, 120000);
        pickLocalFolder("选择要提交的 Git 工程目录", ctrl ? ctrl.signal : undefined)
          .then(function (d) {
            if (d && d.ok && d.path) {
              setWorkspace(d.path);
              setErr("");
              refreshBranch(d.path);
            } else if (d && d.error && d.error !== "已取消选择") {
              setErr(d.error || "选文件夹失败");
            } else {
              setErr("");
            }
          })
          .catch(function (e) {
            setErr(
              e && e.name === "AbortError"
                ? "选择超时：请点常用路径或手动粘贴目录"
                : "浏览失败：" + (e && e.message ? e.message : e),
            );
          })
          .finally(function () {
            clearTimeout(timer);
            setBusy(false);
          });
      }

      function runPrepare(local_path, work_branch) {
        setBusy(true);
        setErr("正在列出待提交文件…");
        fetch(engineBase() + "/api/code-commit/prepare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace: local_path, work_branch: work_branch }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (!d || !d.ok) {
              setErr((d && (d.detail || d.reply)) || "列文件失败");
              setBusy(false);
              return;
            }
            var list = Array.isArray(d.pending_files)
              ? d.pending_files
              : Array.isArray(d.files)
                ? d.files
                : [];
            var paths = list
              .map(function (p) {
                return typeof p === "string" ? p : (p && p.path) || "";
              })
              .filter(Boolean);
            if (!paths.length) {
              setErr((d && d.reply) || "没有待提交的业务文件（工作区可能干净）");
              setBusy(false);
              return;
            }
            var sel = {};
            paths.forEach(function (p) {
              sel[p] = true;
            });
            setFiles(paths.slice(0, 120));
            setSelected(sel);
            setDraft(String(d.draft_message || ""));
            if (d.work_branch) setBranch(String(d.work_branch));
            setPhase("files");
            setErr("");
            setBusy(false);
          })
          .catch(function (e) {
            setErr("列文件失败：" + (e && e.message ? e.message : e));
            setBusy(false);
          });
      }

      function goPrepare() {
        var local_path = String(workspace || "").trim();
        var work_branch = String(branch || "").trim();
        if (!local_path) {
          setErr("请填写或浏览选择本机 Git 工程目录");
          return;
        }
        if (work_branch) {
          runPrepare(local_path, work_branch);
          return;
        }
        // 分支空时先按工程当前分支识别，再进入选文件（避免目录已填却卡在手填）
        setBusy(true);
        setErr("正在识别分支…");
        fetch(engineBase() + "/api/code-commit/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace: local_path }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (!d || !d.ok) {
              setErr((d && (d.detail || d.reply)) || "路径不可用");
              setBusy(false);
              return;
            }
            var wb = String(d.work_branch || "").trim();
            setBranch(wb);
            setBranchHint(String(d.branch_hint || (d.need_user_branch ? "请填写要提交的分支" : "") || ""));
            if (!wb) {
              setErr(d.branch_hint || "请填写要提交的分支");
              setBusy(false);
              return;
            }
            runPrepare(local_path, wb);
          })
          .catch(function (e) {
            setErr("分支识别失败：" + (e && e.message ? e.message : e));
            setBusy(false);
          });
      }

      function selectedList() {
        return Object.keys(selected).filter(function (k) {
          return selected[k];
        });
      }

      function toggle(rel) {
        setSelected(function (prev) {
          var next = Object.assign({}, prev);
          if (next[rel]) delete next[rel];
          else next[rel] = true;
          return next;
        });
      }

      function runGate(fileList) {
        var local_path = String(workspace || "").trim();
        var work_branch = String(branch || "").trim();
        setPhase("gating");
        setBusy(true);
        setErr("");
        setSummary("门禁审核中…");
        setFindings([]);
        fetch(engineBase() + "/api/code-commit/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workspace: local_path,
            work_branch: work_branch,
            files: fileList && fileList.length ? fileList : null,
          }),
        })
          .then(function (r) {
            return r.json().then(function (d) {
              return { status: r.status, d: d };
            });
          })
          .then(function (pack) {
            var d = pack.d || {};
            if (!d.ok && !d.job_id) {
              setPhase("dir");
              setBusy(false);
              setErr(d.detail || d.reply || "门禁失败");
              if (d.need_user_branch) setBranchHint(d.branch_hint || d.detail || "请填写分支");
              return;
            }
            setJobId(String(d.job_id || ""));
            setFindings(Array.isArray(d.findings) ? d.findings : []);
            if (d.work_branch) setBranch(String(d.work_branch));
            if (!d.can_commit) {
              setPhase("blocked");
              setBusy(false);
              setSummary(
                d.summary ||
                  d.reply ||
                  "门禁未通过，禁止提交（阻断 " + (d.blocking_count || 0) + "）",
              );
              return;
            }
            var cui = d.code_commit_ui || {};
            setDraft(String(cui.message || d.draft_message || draft || ""));
            setPush(cui.push !== false && d.default_push !== false);
            setPhase("confirm");
            setBusy(false);
            setSummary(d.summary || "门禁通过，请确认提交说明后推送");
            setErr("");
          })
          .catch(function (e) {
            setPhase("dir");
            setBusy(false);
            setErr("门禁请求失败：" + (e && e.message ? e.message : e));
          });
      }

      function doConfirm(doPush) {
        var jid = String(jobId || "").trim();
        var message = String(draft || "").trim();
        if (!jid) {
          setErr("缺少 job_id");
          return;
        }
        if (!message) {
          setErr("请填写中文提交说明");
          return;
        }
        setBusy(true);
        setErr("");
        issueHitl("code-commit.confirm", { job_id: jid })
          .then(function (nonce) {
            return fetch(engineBase() + "/api/code-commit/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                job_id: jid,
                message: message,
                push: !!doPush,
                decision: "approve",
                nonce: nonce,
              }),
            });
          })
          .then(function (r) {
            return r.json().then(function (d) {
              return { status: r.status, d: d };
            });
          })
          .then(function (pack) {
            var d = pack.d || {};
            setBusy(false);
            setLastPush(!!doPush);
            setCommitDetail(d);
            setPhase("done");
            var resultText = "";
            if (d.ok) {
              resultText = d.reply || "提交成功" + (doPush ? "并已推送" : "（仅本地）");
              setResult(resultText);
              setErr("");
            } else if (d.push_retry_needed) {
              resultText = d.reply || "本地已 commit，推送失败，可稍后重试推送";
              setResult(resultText);
              setErr(d.detail || d.reply || "push 失败");
            } else {
              setResult("");
              setErr(d.detail || d.reply || "确认失败");
            }
            ccPersistSaveCard(block, props.sessionId, ccResolveCallId(), {
              phase: "done",
              callId: ccResolveCallId(),
              sessionId: ccBlockSessionId(block, props.sessionId),
              workspace: workspace,
              branch: branch,
              branchHint: branchHint,
              files: files,
              selected: selected,
              draft: draft,
              push: push,
              jobId: jid,
              findings: findings,
              summary: summary,
              result: resultText,
              commitDetail: d,
              lastPush: !!doPush,
            });
          })
          .catch(function (e) {
            setBusy(false);
            setPhase("done");
            setErr("确认请求失败：" + (e && e.message ? e.message : e));
          });
      }

      function head(hint) {
        return h(
          "div",
          { className: "wb-cr-head" },
          h("span", { className: "wb-cr-badge" }, "提交代码"),
          h("span", { className: "wb-cr-hint" }, hint),
        );
      }

      if (phase === "gating") {
        return h(
          "div",
          { className: "wb-cr" },
          head("门禁中"),
          h("div", { className: "wb-cr-body" }, h("p", { className: "wb-cr-sum" }, summary || "门禁审核中，请稍候…")),
        );
      }

      function doPushRetry() {
        var jid = String((commitDetail && commitDetail.job_id) || jobId || "").trim();
        if (!jid) {
          setErr("缺少 job_id，无法重试推送");
          return;
        }
        setBusy(true);
        setErr("");
        fetch(engineBase() + "/api/code-commit/push-retry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jid }),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            setBusy(false);
            setCommitDetail(d);
            var resultText = "";
            if (d && d.ok) {
              resultText = d.reply || "推送成功";
              setResult(resultText);
              setErr("");
              setLastPush(true);
            } else {
              resultText = (d && d.reply) || "推送仍失败";
              setResult(resultText);
              setErr((d && (d.detail || d.hint || d.reply)) || "推送失败");
            }
            ccPersistSaveCard(block, props.sessionId, toolCallId, {
              phase: "done",
              callId: toolCallId,
              jobId: jid,
              commitDetail: d,
              result: resultText,
              lastPush: !!(d && d.ok),
              workspace: workspace,
              branch: branch,
              files: files,
              selected: selected,
              draft: draft,
            });
          })
          .catch(function (e) {
            setBusy(false);
            setErr("重试推送失败：" + (e && e.message ? e.message : e));
          });
      }

      if (phase === "done") {
        var detail = commitDetail || {};
        var cr = detail.commit_result || {};
        var pushInfo = cr.push || {};
        var didPush = lastPush;
        var pushRetry = !!(detail.push_retry_needed || (cr.commit && pushInfo && !pushInfo.ok && didPush));
        var okCommit = !!(detail.ok || cr.ok || cr.commit);
        var fileList = Array.isArray(detail.files) && detail.files.length
          ? detail.files
          : Array.isArray(cr.files) && cr.files.length
            ? cr.files
            : selectedList();
        var msgText = String(detail.message || cr.message || draft || "").trim();
        var wsPath = String(detail.workspace || workspace || "").trim();
        var branchName = String(cr.branch || branch || "").trim();
        var commitSha = String(cr.commit || "").trim();
        var title = pushRetry
          ? "本地已提交，推送未完成"
          : didPush && pushInfo && pushInfo.ok
            ? "已提交并推送到远程"
            : okCommit
              ? didPush
                ? "已提交"
                : "已本地提交（未推送）"
              : "提交结束";
        var bannerClass = pushRetry ? "wb-cr-done-banner warn" : okCommit ? "wb-cr-done-banner ok" : "wb-cr-done-banner warn";
        var remoteLine = ccCommitRemoteLabel(didPush, pushInfo);
        var skippedNote = cr.skipped ? String(cr.message || "本批无新变更或已跳过 commit") : "";
        var kvKids = [
          h("dt", null, "项目"),
          h("dd", { title: wsPath }, ccTailName(wsPath)),
        ];
        if (wsPath) {
          kvKids.push(h("dt", null, "路径"), h("dd", { title: wsPath }, wsPath));
        }
        kvKids.push(
          h("dt", null, "分支"),
          h("dd", null, branchName || "—"),
          h("dt", null, "Commit"),
          h("dd", null, commitSha || "—"),
          h("dt", null, "推送"),
          h("dd", null, remoteLine),
        );
        if (pushInfo && pushInfo.remote_url && didPush && pushInfo.ok) {
          kvKids.push(h("dt", null, "远程"), h("dd", null, String(pushInfo.remote_url)));
        }
        if (jobId || detail.job_id) {
          kvKids.push(h("dt", null, "任务"), h("dd", null, String(detail.job_id || jobId)));
        }
        if (msgText) {
          kvKids.push(h("dt", null, "说明"), h("dd", null, msgText));
        }
        kvKids.push(
          h("dt", null, "文件"),
          h("dd", null, fileList.length ? fileList.length + " 个" : "—"),
        );
        return h(
          "div",
          { className: "wb-cr" },
          head(
            (pushRetry ? "推送待重试" : okCommit ? "完成" : "结束") +
              " · " +
              CC_UI_REV,
          ),
          h(
            "div",
            { className: "wb-cr-body" },
            h(
              "div",
              { className: bannerClass },
              h("span", { className: "wb-cr-done-icon" }, pushRetry ? "!" : okCommit ? "✓" : "·"),
              h(
                "div",
                null,
                h("strong", null, title),
                result && result !== title ? h("p", { className: "wb-cr-note", style: { margin: "4px 0 0" } }, result) : null,
              ),
            ),
            h("dl", { className: "wb-cr-kv" }, kvKids),
            fileList.length
              ? h(
                  "div",
                  { className: "wb-cr-files" },
                  h("div", { className: "wb-cr-label" }, "本批提交文件"),
                  fileList.slice(0, 40).map(function (f, i) {
                    return h("div", { key: i, className: "wb-cr-file" }, h("span", null, String(f)));
                  }),
                  fileList.length > 40
                    ? h("p", { className: "wb-cr-note" }, "…另有 " + (fileList.length - 40) + " 个文件")
                    : null,
                )
              : null,
            skippedNote ? h("p", { className: "wb-cr-warn" }, skippedNote) : null,
            pushRetry && (pushInfo.error || pushInfo.raw_error)
              ? h(
                  "p",
                  { className: "wb-cr-err" },
                  String(pushInfo.error || pushInfo.raw_error || "").slice(0, 320),
                )
              : null,
            err && !pushRetry ? h("p", { className: "wb-cr-err" }, err) : null,
            pushRetry && err ? h("p", { className: "wb-cr-warn" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              pushRetry
                ? h(
                    "button",
                    {
                      type: "button",
                      className: "wb-cr-btn primary",
                      disabled: busy,
                      onClick: doPushRetry,
                    },
                    busy ? "推送中…" : "重试推送",
                  )
                : null,
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: ccResetCard,
                },
                "重新选择",
              ),
            ),
          ),
        );
      }

      if (phase === "blocked") {
        return h(
          "div",
          { className: "wb-cr" },
          head("门禁阻断"),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, summary),
            h(
              "div",
              { className: "wb-cr-files" },
              findings.length
                ? findings.slice(0, 20).map(function (f, i) {
                    return h(
                      "div",
                      { key: i, style: { margin: "6px 0" } },
                      h("b", null, "[" + (f.severity || "?") + "] "),
                      (f.path || f.file || "") + " — " + (f.message || f.title || ""),
                    );
                  })
                : h("p", { className: "wb-cr-sum" }, "无 findings 详情"),
            ),
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    setPhase("files");
                  },
                },
                "返回改文件",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    setPhase("dir");
                  },
                },
                "改目录",
              ),
            ),
          ),
        );
      }

      if (phase === "confirm") {
        return h(
          "div",
          { className: "wb-cr" },
          head("确认提交并推送"),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, summary || ("job：" + jobId)),
            h("p", { className: "wb-cr-sum" }, "分支：" + branch + " · 目录：" + workspace),
            h("label", { className: "wb-cr-label" }, "中文提交说明"),
            h("textarea", {
              className: "wb-cr-input",
              style: { width: "100%", minHeight: 72, boxSizing: "border-box", fontFamily: "inherit" },
              value: draft,
              onChange: function (e) {
                setDraft(e.target.value);
              },
            }),
            h(
              "label",
              { className: "wb-cr-file", style: { marginTop: 8 } },
              h("input", {
                type: "checkbox",
                checked: !!push,
                onChange: function () {
                  setPush(!push);
                },
              }),
              h("span", null, "同时推送到远程（push）"),
            ),
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn primary",
                  disabled: busy,
                  onClick: function () {
                    doConfirm(!!push);
                  },
                },
                busy ? "提交中…" : push ? "确认提交并推送" : "确认仅本地提交",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  disabled: busy,
                  onClick: function () {
                    doConfirm(false);
                  },
                },
                "仅本地提交",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  disabled: busy,
                  onClick: function () {
                    setPhase("done");
                    setResult("已取消，未执行 git commit。");
                  },
                },
                "取消",
              ),
            ),
          ),
        );
      }

      if (phase === "files") {
        return h(
          "div",
          { className: "wb-cr" },
          head("勾选待提交文件"),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, workspace + " · " + branch + " · " + files.length + " 个待提交"),
            h(
              "div",
              { className: "wb-cr-actions", style: { marginTop: 0 } },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    var next = {};
                    files.forEach(function (p) {
                      next[p] = true;
                    });
                    setSelected(next);
                  },
                },
                "全选",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    setSelected({});
                  },
                },
                "清空",
              ),
            ),
            h(
              "div",
              { className: "wb-cr-files" },
              files.map(function (rel) {
                return h(
                  "label",
                  { key: rel, className: "wb-cr-file" },
                  h("input", {
                    type: "checkbox",
                    checked: !!selected[rel],
                    onChange: function () {
                      toggle(rel);
                    },
                  }),
                  h("span", null, rel),
                );
              }),
            ),
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  disabled: busy,
                  onClick: function () {
                    setPhase("dir");
                    setErr("");
                  },
                },
                "返回改目录",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn primary",
                  disabled: busy,
                  onClick: function () {
                    var sel = selectedList();
                    if (!sel.length) {
                      setErr("请至少勾选一个文件");
                      return;
                    }
                    runGate(sel);
                  },
                },
                "开始门禁审核",
              ),
            ),
          ),
        );
      }

      // dir
      return h(
        "div",
        { className: "wb-cr" },
        head("选择目录 · 下一步勾选文件 · " + CC_UI_REV),
        h(
          "div",
          { className: "wb-cr-body" },
          h("p", { className: "wb-cr-sum" }, "主聊天工具卡：选目录 → 勾选文件 → 门禁 → 确认后才 commit/push。"),
          h(WorkspaceMismatchHint, {
            dshCwd: dshCwd,
            workspace: workspace,
            home: props.home,
            onUseDsh: function () {
              setWorkspace(dshCwd);
            },
          }),
          h("label", { className: "wb-cr-label" }, "本机 Git 工程目录"),
          h(
            "div",
            { className: "wb-cr-row" },
            h("input", {
              className: "wb-cr-input",
              value: workspace,
              placeholder: "/Users/你/项目",
              onChange: function (e) {
                setWorkspace(e.target.value);
              },
              onBlur: function () {
                refreshBranch();
              },
            }),
            h(
              "button",
              { type: "button", className: "wb-cr-btn", disabled: busy, onClick: browse },
              busy ? "选择中…" : "浏览…",
            ),
          ),
          suggestions.length
            ? h(
                "div",
                { className: "wb-cr-chips" },
                suggestions.map(function (s, i) {
                  var p = typeof s === "string" ? s : (s && s.path) || "";
                  var lab = typeof s === "object" && s.label ? s.label + " · " : "";
                  if (!p) return null;
                  return h(
                    "button",
                    {
                      key: i + p,
                      type: "button",
                      className: "wb-cr-chip",
                      title: p,
                      onClick: function () {
                        setWorkspace(p);
                        refreshBranch(p);
                      },
                    },
                    lab + p,
                  );
                }),
              )
            : null,
          h("label", { className: "wb-cr-label" }, "提交分支"),
          h("input", {
            className: "wb-cr-input",
            style: { width: "100%", marginBottom: 4, boxSizing: "border-box" },
            value: branch,
            placeholder: "如 feature/xxx",
            onChange: function (e) {
              setBranch(e.target.value);
            },
          }),
          h("p", { className: "wb-cr-sum" }, branchHint || "选目录后自动识别当前分支"),
          err ? h("p", { className: "wb-cr-err" }, err) : null,
          h(
            "div",
            { className: "wb-cr-actions" },
            h(
              "button",
              {
                type: "button",
                className: "wb-cr-btn primary",
                disabled: busy,
                onClick: goPrepare,
              },
              busy ? "列出文件…" : "下一步：选文件",
            ),
          ),
        ),
      );
    }


    var CD_PIPELINE = [
      { id: "brief", title: "需求理解" },
      { id: "sandbox-prep", title: "沙箱准备" },
      { id: "dev", title: "写码" },
      { id: "sync", title: "同步到本机工程" },
    ];
    var CD_STEP_MAP = {
      "agent-loop": "dev",
      "cursor-local": "dev",
      "delete-plan": "dev",
      "delete-exec": "dev",
      "sync-del": "sync",
    };
    /** 持久化版本：升主版本时须兼容读取旧版，禁止 prune 直接删光导致刷新回表单。 */
    var CD_PERSIST_VER = 4;
    var CD_PERSIST_MIN_VER = 2;
    var CD_UI_REV = "2026-09-10q-review-fix";
    var CD_PERSIST_MAX_STREAM = 100000;
    var CD_PERSIST_MAX_DELIVERY = 80000;
    var CD_PERSIST_MAX_THINK = 24000;

    function cdPersistClip(text, maxLen) {
      var s = String(text || "");
      if (!s) return "";
      var n = maxLen || CD_PERSIST_MAX_STREAM;
      return s.length > n ? s.slice(-n) : s;
    }

    /** 完成态禁止用空正文覆盖已有过程/终稿（刷新丢字主因）。 */
    function cdPersistMergeBody(prev, payload) {
      if (!payload || typeof payload !== "object") return payload;
      if (!prev || typeof prev !== "object") return payload;
      var phase = String(payload.phase || "");
      if (phase !== "done" && phase !== "running") return payload;
      ["streamText", "deliveryText", "thinkingText", "result"].forEach(function (field) {
        if (!payload[field] && prev[field]) payload[field] = prev[field];
      });
      if ((!payload.steps || !payload.steps.length) && prev.steps && prev.steps.length) {
        payload.steps = prev.steps;
      }
      return payload;
    }

    function cdPersistLoadJobSnapshot(jobId) {
      var jid = String(jobId || "").trim();
      if (!jid) return null;
      try {
        var raw = localStorage.getItem("wb-cd-job:" + jid);
        if (!raw) return null;
        var o = cdPersistNormalize(JSON.parse(raw));
        if (!o || String(o.jobId || "") !== jid) return null;
        return o;
      } catch (eJ) {
        return null;
      }
    }

    /** 卡级持久化缺正文时，从 job 快照补全（刷新恢复）。 */
    function cdPersistEnrichCardSaved(saved) {
      if (!saved || typeof saved !== "object") return saved;
      var jid = String(saved.jobId || "").trim();
      if (!jid) return saved;
      var snap = cdPersistLoadJobSnapshot(jid);
      if (!snap) return saved;
      // 有过程正文时也要补缺终稿/步骤等（避免刷新后「有过程无结论」）
      return Object.assign({}, saved, {
        streamText: saved.streamText || snap.streamText || "",
        deliveryText: saved.deliveryText || snap.deliveryText || "",
        thinkingText: saved.thinkingText || snap.thinkingText || "",
        thinkingMs: saved.thinkingMs != null ? saved.thinkingMs : snap.thinkingMs,
        result: saved.result || snap.result || "",
        steps: saved.steps && saved.steps.length ? saved.steps : snap.steps,
        synced: saved.synced && saved.synced.length ? saved.synced : snap.synced,
        deferred: saved.deferred && saved.deferred.length ? saved.deferred : snap.deferred,
        deleted: saved.deleted && saved.deleted.length ? saved.deleted : snap.deleted,
        runtimeHint: saved.runtimeHint || snap.runtimeHint || "",
        aliveHint: saved.aliveHint || snap.aliveHint || "",
      });
    }
    var CD_ICON_COPY =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    var CD_ICON_DOWNLOAD =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

    function cdFinalizeSteps(stepState, ev, asError) {
      var job = ev && ev.job;
      if (job && (job.events || job.status)) {
        return cdJobStepsFromRecord(job);
      }
      var sealed = cdSealSteps(stepState, asError);
      var syncedList =
        (ev && ev.synced_files) ||
        (job && job.synced_files) ||
        [];
      if (!asError && syncedList && syncedList.length) {
        sealed = sealed.map(function (s) {
          if (s.id === "sync" && (s.state === "skipped" || s.state === "pending")) {
            return Object.assign({}, s, {
              state: "done",
              title: "已同步 " + syncedList.length + " 个文件到本机",
            });
          }
          return s;
        });
      }
      return sealed;
    }

    function cdBlockCallId(block, callIdProp) {
      if (callIdProp != null && String(callIdProp).trim()) return String(callIdProp).trim();
      if (!block) return "";
      var nested = block.call && typeof block.call === "object" ? block.call : null;
      return String(
        block.callId ||
          block.toolCallId ||
          (nested && (nested.callId || nested.toolCallId || nested.id)) ||
          block.id ||
          "",
      ).trim();
    }

    function cdBlockSessionId(block, sessionId) {
      return String(
        sessionId ||
          (block &&
            (block.threadId ||
              block.thread_id ||
              block.sessionId ||
              block.session_id ||
              block.conversationId ||
              "")) ||
          "",
      ).trim();
    }

    /**
     * DSH toolview 的稳定身份在 props.callId（见 ToolCallTree owner），
     * 不要只读 block —— 刷新后 block 形态常变，会导致 key 漂移回表单。
     */
    function cdPersistKey(block, sessionId, callIdProp) {
      var callId = cdBlockCallId(block, callIdProp);
      var sid = cdBlockSessionId(block, sessionId);
      if (callId && sid) return "wb-cd-card:" + sid + ":" + callId;
      if (callId) return "wb-cd-card:call:" + callId;
      if (sid) return "wb-cd-card:session:" + sid + ":lone";
      return "wb-cd-card:anon";
    }

    function cdPersistKeyAliases(block, sessionId, callIdProp) {
      var callId = cdBlockCallId(block, callIdProp);
      var sid = cdBlockSessionId(block, sessionId);
      var keys = [];
      var primary = cdPersistKey(block, sessionId, callIdProp);
      keys.push(primary);
      // 有 callId 时只认 call 专属 key，禁止 session/anon 共享键（否则新 begin 会吞掉上一张卡的完成态）
      if (callId) {
        keys.push("wb-cd-card:call:" + callId);
        keys.push("wb-cd-card:block:" + callId);
        if (sid) keys.push("wb-cd-card:" + sid + ":" + callId);
      } else if (sid) {
        keys.push("wb-cd-card:" + sid);
        keys.push("wb-cd-card:session:" + sid + ":lone");
      } else {
        keys.push("wb-cd-card:anon");
      }
      var uniq = [];
      var seen = {};
      keys.forEach(function (k) {
        if (!k || seen[k]) return;
        seen[k] = true;
        uniq.push(k);
      });
      return uniq;
    }

    /** 持久化记录是否属于当前工具卡（按 callId 硬绑定）。 */
    function cdPersistBelongsToCall(saved, callId) {
      if (!saved || typeof saved !== "object") return false;
      var cid = String(callId || "").trim();
      // callId 缺失时绝不认领任何完成态（否则新 begin 会吞掉 session 里上一张卡）
      if (!cid) return false;
      var savedCid = String(saved.callId || "").trim();
      if (!savedCid) return false;
      return savedCid === cid;
    }

    /**
     * 新开 mes_code_dev_begin（pick）必须停在 HITL。
     * 返回 true = 丢弃进度、强制表单。
     * 契约：本 callId 已落盘 done/running/options/propose（或已绑 jobId）→ 允许恢复；
     * 不以 meta 仍为 cd-pick 为由回表单。
     */
    function cdPickMustStayHitl(wb, ui, saved, callId) {
      var cid = String(callId || "").trim();
      if (saved && cid && cdPersistBelongsToCall(saved, callId)) {
        var phase = String(saved.phase || "");
        if (
          phase === "done" ||
          phase === "running" ||
          phase === "options" ||
          phase === "propose" ||
          saved.jobId
        ) {
          return false;
        }
      }
      var isPick =
        (ui && String(ui.kind || "") === "pick") ||
        (wb && (wb.t === "cd-pick" || wb.t === "cd-none"));
      if (!isPick && wb && wb.t && String(wb.t).indexOf("cd-") === 0 && wb.t !== "cd-pick") {
        return false;
      }
      if (!isPick && wb && wb.t) return false;
      if (!saved) return true;
      if (!cid) return true;
      return !cdPersistBelongsToCall(saved, callId);
    }

    function cdPersistNormalize(o) {
      if (!o || typeof o !== "object") return null;
      var ver = Number(o.v || 0);
      if (!ver || ver < CD_PERSIST_MIN_VER) return null;
      if (o.streamText) {
        o.streamText = cdStripExplorationFromProcess(cdStripBoilerplate(String(o.streamText || "")));
      }
      if (o.thinkingText) o.thinkingText = cdDedupeThinkText(String(o.thinkingText || ""));
      return o;
    }

    function cdPersistLoad(key) {
      try {
        var raw = localStorage.getItem(key);
        if (!raw) return null;
        return cdPersistNormalize(JSON.parse(raw));
      } catch (e) {
        return null;
      }
    }

    /** 扫整仓 localStorage：按 callId 字段或 key 后缀找回（防 key 算法变更丢进度）。 */
    function cdPersistScanByCallId(callId) {
      var cid = String(callId || "").trim();
      if (!cid) return null;
      var best = null;
      try {
        for (var i = 0; i < localStorage.length; i++) {
          var k = localStorage.key(i);
          if (!k || k.indexOf("wb-cd-card:") !== 0) continue;
          var hit = false;
          if (k === "wb-cd-card:call:" + cid || k === "wb-cd-card:block:" + cid || k.slice(-cid.length - 1) === ":" + cid) {
            hit = true;
          }
          var o = null;
          try {
            o = cdPersistNormalize(JSON.parse(localStorage.getItem(k) || "null"));
          } catch (e1) {
            continue;
          }
          if (!o) continue;
          if (!hit && String(o.callId || "") !== cid) continue;
          if (!(o.phase === "done" || o.phase === "running" || o.jobId)) continue;
          if (!best || Number(o.at || 0) > Number(best.at || 0)) best = o;
        }
      } catch (e2) {}
      return best;
    }

    /** 兼容旧 key + 全库扫描，避免升级或刷新后找不到进度。 */
    function cdPersistLoadForCard(block, sessionId, callIdProp) {
      try {
        var callId = cdBlockCallId(block, callIdProp);
        var sid = cdBlockSessionId(block, sessionId);
        var key = cdPersistKey(block, sessionId, callIdProp);
        var aliases = cdPersistKeyAliases(block, sessionId, callIdProp);
        for (var i = 0; i < aliases.length; i++) {
          var hit = cdPersistLoad(aliases[i]);
          if (
            hit &&
            cdPersistBelongsToCall(hit, callId) &&
            (hit.phase === "done" ||
              hit.phase === "running" ||
              hit.jobId ||
              hit.phase === "options" ||
              hit.phase === "propose")
          ) {
            return { key: key, saved: hit, migrateFrom: aliases[i] !== key ? aliases[i] : "" };
          }
        }
        var scanned = cdPersistScanByCallId(callId);
        if (scanned && cdPersistBelongsToCall(scanned, callId)) {
          return { key: key, saved: scanned, migrateFrom: "" };
        }
        // 无 callId 的旧卡才允许读 session/anon；有 callId 时绝不从共享键偷完成态
        if (!callId) {
          var orphans = ["wb-cd-card:anon"];
          if (sid) orphans.push("wb-cd-card:session:" + sid + ":lone", "wb-cd-card:" + sid);
          for (var j = 0; j < orphans.length; j++) {
            var orphan = cdPersistLoad(orphans[j]);
            if (
              orphan &&
              (orphan.phase === "done" || orphan.phase === "running") &&
              orphan.jobId
            ) {
              return { key: key, saved: orphan, migrateFrom: orphans[j] };
            }
          }
        }
        return { key: key, saved: null };
      } catch (eLoad) {
        try {
          console.warn("[dsh-mes-bridge] cdPersistLoadForCard failed", eLoad);
        } catch (eLog) {}
        return {
          key: cdPersistKey(block, sessionId, callIdProp),
          saved: null,
        };
      }
    }

    function cdPersistPrune() {
      try {
        var now = Date.now();
        var maxAge = 7 * 24 * 3600 * 1000;
        var keys = [];
        for (var i = 0; i < localStorage.length; i++) {
          var k = localStorage.key(i);
          if (k && (k.indexOf("wb-cd-card:") === 0 || k.indexOf("wb-cd-job:") === 0)) keys.push(k);
        }
        keys.forEach(function (k) {
          try {
            var o = JSON.parse(localStorage.getItem(k) || "null");
            if (!o || Number(o.v || 0) < CD_PERSIST_MIN_VER) {
              localStorage.removeItem(k);
              return;
            }
            var at = Number(o.at || 0);
            if (at && now - at > maxAge) localStorage.removeItem(k);
            // 完成态保留正文供刷新；仅按 maxAge 整键淘汰，不再 10 分钟删 streamText
          } catch (e2) {
            try {
              localStorage.removeItem(k);
            } catch (e3) {}
          }
        });
      } catch (e4) {}
    }

    function cdPersistSave(key, data) {
      try {
        // 禁止「空表单」覆盖已有 running/done（刷新后短暂 form 态写回是丢进度主因之一）
        try {
          var prev = JSON.parse(localStorage.getItem(key) || "null");
          var nextPhase = data && data.phase;
          if (
            prev &&
            Number(prev.v || 0) >= CD_PERSIST_MIN_VER &&
            (prev.phase === "done" || prev.phase === "running") &&
            nextPhase === "form" &&
            prev.jobId &&
            !(data && data.jobId)
          ) {
            return;
          }
        } catch (eGuard) {}

        var payload = Object.assign({ v: CD_PERSIST_VER, at: Date.now() }, data || {});
        try {
          var prevBody = JSON.parse(localStorage.getItem(key) || "null");
          if (prevBody && Number(prevBody.v || 0) >= CD_PERSIST_MIN_VER) {
            payload = cdPersistMergeBody(prevBody, payload);
          }
        } catch (ePrev) {}
        payload.streamText = cdPersistClip(payload.streamText, CD_PERSIST_MAX_STREAM);
        payload.deliveryText = cdPersistClip(payload.deliveryText, CD_PERSIST_MAX_DELIVERY);
        payload.thinkingText = cdPersistClip(payload.thinkingText, CD_PERSIST_MAX_THINK);
        localStorage.setItem(key, JSON.stringify(payload));
        if (payload.jobId) {
          try {
            localStorage.setItem(
              "wb-cd-job:" + String(payload.jobId),
              JSON.stringify({
                v: CD_PERSIST_VER,
                at: Date.now(),
                cardKey: key,
                phase: payload.phase,
                jobId: payload.jobId,
                callId: payload.callId || "",
                sessionId: payload.sessionId || "",
                workspace: payload.workspace || "",
                streamText: payload.streamText || "",
                deliveryText: payload.deliveryText || "",
                thinkingText: payload.thinkingText || "",
                thinkingMs: payload.thinkingMs,
                result: payload.result || "",
                steps: payload.steps || [],
                synced: payload.synced || [],
                deferred: payload.deferred || [],
                deleted: payload.deleted || [],
                runtimeHint: payload.runtimeHint || "",
                aliveHint: payload.aliveHint || "",
                elapsed: payload.elapsed,
              }),
            );
          } catch (eJob) {}
        }
        cdPersistPrune();
      } catch (e0) {
        // 配额不足：进一步截断正文，禁止用空 body 覆盖已有 done（契约冻结）
        try {
          cdPersistPrune();
          var slim = Object.assign({ v: CD_PERSIST_VER, at: Date.now() }, data || {});
          slim.streamText = cdPersistClip(slim.streamText, 20000);
          slim.deliveryText = cdPersistClip(slim.deliveryText, 12000);
          slim.thinkingText = cdPersistClip(slim.thinkingText, 4000);
          try {
            var prevSlim = JSON.parse(localStorage.getItem(key) || "null");
            if (prevSlim && Number(prevSlim.v || 0) >= CD_PERSIST_MIN_VER) {
              slim = cdPersistMergeBody(prevSlim, slim);
            }
          } catch (eM) {}
          localStorage.setItem(key, JSON.stringify(slim));
        } catch (e1) {}
      }
    }

    /** 同一进度写入所有别名 key，刷新时无论 DSH 给哪种 block 形态都能命中。 */
    function cdPersistSaveCard(block, sessionId, callIdProp, data) {
      var callId = cdBlockCallId(block, callIdProp) || (data && data.callId) || "";
      var aliases = cdPersistKeyAliases(block, sessionId, callIdProp);
      var payload = Object.assign({}, data || {}, {
        callId: callId,
        sessionId: cdBlockSessionId(block, sessionId) || (data && data.sessionId) || "",
      });
      // 只写 call 专属 key；顺带清掉历史上污染过的 session/anon 共享完成态
      aliases.forEach(function (k) {
        cdPersistSave(k, payload);
      });
      if (callId) {
        var sid = cdBlockSessionId(block, sessionId);
        ["wb-cd-card:anon"]
          .concat(sid ? ["wb-cd-card:" + sid, "wb-cd-card:session:" + sid + ":lone"] : [])
          .forEach(function (sharedKey) {
            try {
              var old = cdPersistLoad(sharedKey);
              if (old && (old.phase === "done" || old.phase === "running" || old.jobId)) {
                localStorage.removeItem(sharedKey);
              }
            } catch (eClr) {}
          });
      }
      return aliases[0];
    }

    function cdPersistClear(key) {
      try {
        localStorage.removeItem(key);
      } catch (e1) {}
    }

    function cdJobStepsFromRecord(job) {
      var list = cdInitSteps().map(function (s) {
        return s.id === "brief" ? Object.assign({}, s, { state: "done" }) : s;
      });
      var evs = Array.isArray(job.events) ? job.events : [];
      var stepped = false;
      evs.forEach(function (ev) {
        if (ev && ev.type === "step") {
          stepped = true;
          list = cdApplyStep(list, ev);
        }
      });
      if (!stepped) {
        (job.steps || []).forEach(function (s) {
          if (s && s.id) list = cdApplyStep(list, { id: s.id, state: s.state, title: s.title });
        });
      }
      var st = String(job.status || "");
      if (st === "succeeded") return cdSealSteps(list, false);
      if (st === "failed" || st === "cancelled") return cdSealSteps(list, true);
      return list;
    }

    function cdJobElapsed(job) {
      var created = Number(job.created_at || 0);
      var updated = Number(job.updated_at || 0);
      if (created > 0 && updated >= created) return Math.max(0, updated - created);
      return 0;
    }

    function cdJobAliveHint(job) {
      var st = String(job.status || "");
      if (st === "succeeded") return "任务完成 · " + cdFormatDuration(cdJobElapsed(job));
      if (st === "failed") return "任务结束（失败）";
      if (st === "cancelled") return "任务已取消";
      return String(job.progress || "写码进行中…");
    }

    function cdInitSteps() {
      return CD_PIPELINE.map(function (p) {
        return { id: p.id, title: p.title, state: "pending" };
      });
    }

    function cdPipelineIndex(id) {
      for (var i = 0; i < CD_PIPELINE.length; i++) {
        if (CD_PIPELINE[i].id === id) return i;
      }
      return CD_PIPELINE.length + 99;
    }

    function cdNormalizeStepId(id) {
      return CD_STEP_MAP[id] || id;
    }

    function cdMarkPriorDone(list, id) {
      var pIdx = cdPipelineIndex(id);
      return list.map(function (s) {
        if (cdPipelineIndex(s.id) < pIdx && s.state !== "done" && s.state !== "error") {
          return Object.assign({}, s, { state: "done" });
        }
        return s;
      });
    }

    function cdSealSteps(steps, asError) {
      return (steps || [])
        .filter(function (s) {
          return s.id !== "status" && s.id !== "cursor-heartbeat";
        })
        .map(function (s) {
          if (asError) {
            if (s.state === "running" || s.state === "waiting") {
              return Object.assign({}, s, { state: "error" });
            }
            return s;
          }
          if (s.state === "skipped") return s;
          if (s.state === "pending") {
            return Object.assign({}, s, { state: "skipped" });
          }
          if (s.state !== "error") return Object.assign({}, s, { state: "done" });
          return s;
        });
    }

    function cdApplyStep(steps, event) {
      var rawId = event && event.id;
      if (!rawId || rawId === "status" || rawId === "cursor-heartbeat") return steps;
      var id = cdNormalizeStepId(rawId);
      var title = String(event.title || "").trim();
      var nextState = event.state || "running";
      var list = steps && steps.length ? steps.slice() : cdInitSteps();
      var idx = -1;
      for (var i = 0; i < list.length; i++) {
        if (list[i].id === id) {
          idx = i;
          break;
        }
      }
      if (idx < 0) return list;
      var cur = list[idx];
      var merged = Object.assign({}, cur, { state: nextState });
      if (id === "dev") {
        if (rawId === "cursor-local" && nextState === "done") merged.state = "running";
        else if (rawId === "agent-loop" && nextState === "done") merged.state = "done";
        else if (
          (rawId === "delete-plan" || rawId === "delete-exec") &&
          (nextState === "done" || nextState === "skipped")
        ) {
          merged.state = nextState === "done" ? "done" : "running";
        } else if (nextState === "running") merged.state = "running";
      }
      list[idx] = merged;
      if (
        nextState === "running" ||
        (id === "dev" && rawId === "agent-loop" && nextState === "done") ||
        nextState === "done"
      ) {
        list = cdMarkPriorDone(list, id);
      }
      if (id === "sync" && nextState === "running") {
        list = list.map(function (s) {
          return s.id === "dev" && s.state === "running"
            ? Object.assign({}, s, { state: "done" })
            : s;
        });
      }
      return list;
    }

    function cdPlanSummary(steps) {
      var list = (steps || []).filter(function (s) {
        return s.state !== "pending";
      });
      if (!list.length) return "准备中…";
      var total = list.length;
      var done = list.filter(function (s) {
        return s.state === "done";
      }).length;
      if (
        list.some(function (s) {
          return s.state === "running";
        })
      ) {
        return "正在进行 " + done + "/" + total;
      }
      var err = list.filter(function (s) {
        return s.state === "error";
      }).length;
      if (err) return "完成 " + done + "/" + total + "（" + err + " 步失败）";
      if (done === total) return "已全部完成（" + total + " 步）";
      return "共 " + total + " 步";
    }

    function cdFormatDuration(sec) {
      sec = Math.max(0, Number(sec) || 0);
      var m = Math.floor(sec / 60);
      var s = Math.floor(sec % 60);
      return m > 0 ? m + "分" + s + "秒" : s + "秒";
    }

    function cdEsc(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }
    function cdHl(cls, s) {
      return '<span class="' + cls + '">' + cdEsc(s) + "</span>";
    }
    var CD_JS_TOK =
      /(\/\/[^\n]*|\/\*[\s\S]*?\*\/|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`|\b[A-Za-z_$][\w$]*(?=\s*\()|\b(?:async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|function|if|import|in|instanceof|interface|let|new|return|super|switch|this|throw|try|typeof|var|void|while|with|yield|from|of|null|undefined|true|false|as|type|enum|declare|readonly)\b|\b\d+(?:\.\d+)?\b)/g;
    function cdHighlightJs(src) {
      var s = String(src || "");
      var out = [];
      var last = 0;
      var m;
      CD_JS_TOK.lastIndex = 0;
      while ((m = CD_JS_TOK.exec(s))) {
        if (m.index > last) out.push(cdEsc(s.slice(last, m.index)));
        var tok = m[0];
        var cls = "wb-hl-op";
        if (/^\/\//.test(tok) || /^\/\*/.test(tok)) cls = "wb-hl-cmt";
        else if (/^['"`]/.test(tok)) cls = "wb-hl-str";
        else if (/^\d/.test(tok)) cls = "wb-hl-num";
        else if (/^[A-Za-z_$]/.test(tok)) {
          var ahead = s.slice(m.index + tok.length);
          cls = /^\s*\(/.test(ahead) ? "wb-hl-fn" : "wb-hl-kw";
          if (cls === "wb-hl-kw" && !/^(async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|function|if|import|in|instanceof|interface|let|new|return|super|switch|this|throw|try|typeof|var|void|while|with|yield|from|of|null|undefined|true|false|as|type|enum|declare|readonly)$/.test(tok)) {
            cls = "wb-hl-op";
          }
        }
        out.push(cdHl(cls, tok));
        last = m.index + tok.length;
      }
      if (last < s.length) out.push(cdEsc(s.slice(last)));
      return out.join("") || cdEsc(s);
    }
    function cdHighlightAttrs(s) {
      var src = String(s || "");
      var out = [];
      var i = 0;
      while (i < src.length) {
        var ch = src[i];
        if (/\s/.test(ch)) {
          out.push(ch);
          i++;
          continue;
        }
        var nm = src.slice(i).match(/^[@#:.]?[\w-]+/);
        if (!nm) {
          out.push(cdEsc(ch));
          i++;
          continue;
        }
        out.push(cdHl("wb-hl-attr", nm[0]));
        i += nm[0].length;
        if (src[i] === "=") {
          out.push(cdHl("wb-hl-punct", "="));
          i++;
          var q = src[i];
          if (q === '"' || q === "'") {
            var j = i + 1;
            while (j < src.length && src[j] !== q) j++;
            out.push(cdHl("wb-hl-str", src.slice(i, j + 1)));
            i = j + 1;
          }
        }
      }
      return out.join("");
    }
    function cdHighlightTag(tag) {
      var s = String(tag || "");
      var m = s.match(/^(<\/?)([\w-]+)([\s\S]*?)(\/?>)$/);
      if (!m) return cdHl("wb-hl-tag", s);
      return (
        cdHl("wb-hl-punct", m[1]) +
        cdHl("wb-hl-name", m[2]) +
        cdHighlightAttrs(m[3]) +
        cdHl("wb-hl-punct", m[4])
      );
    }
    function cdHighlightHtml(src) {
      var s = String(src || "");
      var out = [];
      var i = 0;
      while (i < s.length) {
        if (s.slice(i, i + 4) === "<!--") {
          var end = s.indexOf("-->", i);
          if (end < 0) {
            out.push(cdHl("wb-hl-cmt", s.slice(i)));
            break;
          }
          out.push(cdHl("wb-hl-cmt", s.slice(i, end + 3)));
          i = end + 3;
          continue;
        }
        if (s[i] === "<") {
          var gt = s.indexOf(">", i);
          if (gt < 0) {
            out.push(cdHl("wb-hl-tag", s.slice(i)));
            break;
          }
          out.push(cdHighlightTag(s.slice(i, gt + 1)));
          i = gt + 1;
          continue;
        }
        var next = s.indexOf("<", i);
        if (next < 0) next = s.length;
        var text = s.slice(i, next);
        if (text) out.push(cdEsc(text));
        i = next;
      }
      return out.join("") || cdEsc(s);
    }
    function cdHighlightCss(src) {
      return String(src || "").replace(/(\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|#[\da-fA-F]{3,8}\b|\b[\d.]+(?:px|em|rem|%|vh|vw)?\b)/g, function (tok) {
        if (/^\/\*/.test(tok)) return cdHl("wb-hl-cmt", tok);
        if (/^['"]/.test(tok)) return cdHl("wb-hl-str", tok);
        if (/^#/.test(tok) || /px|em|rem|%|vh|vw/.test(tok)) return cdHl("wb-hl-num", tok);
        return cdEsc(tok);
      });
    }
    function cdHighlightJson(src) {
      return String(src || "").replace(
        /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
        function (all, str, colon) {
          if (str && colon) return cdHl("wb-hl-attr", str) + colon;
          if (str) return cdHl("wb-hl-str", str);
          if (/^(true|false|null)$/.test(all)) return cdHl("wb-hl-kw", all);
          if (/^-?\d/.test(all)) return cdHl("wb-hl-num", all);
          return cdEsc(all);
        },
      );
    }
    function cdHighlightPython(src) {
      var s = String(src || "");
      if (!s) return "";
      var out = [];
      var i = 0;
      var n = s.length;
      var pendingFn = false;
      var PY_KW =
        /^(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|with|yield|lambda|pass|break|continue|raise|global|nonlocal|async|await|and|or|not|in|is|True|False|None)$/;
      var PY_BI =
        /^(len|range|print|str|int|float|bool|list|dict|set|tuple|type|isinstance|enumerate|zip|map|filter|sorted|min|max|sum|abs|open|super|staticmethod|classmethod|property|any|all|next|iter|repr|format|input|id|hash|hex|oct|bin|round|pow|divmod|chr|ord|bytes|bytearray|memoryview|object|Exception|ValueError|TypeError|KeyError|IndexError|AttributeError|RuntimeError)$/;
      while (i < n) {
        var tri = s.slice(i, i + 3);
        if (tri === '"""' || tri === "'''") {
          var j = i + 3;
          while (j + 2 < n && s.slice(j, j + 3) !== tri) j++;
          out.push(cdHl("wb-hl-doc", s.slice(i, Math.min(j + 3, n))));
          i = Math.min(j + 3, n);
          pendingFn = false;
          continue;
        }
        if (s[i] === "#") {
          var cj = i;
          while (cj < n && s[cj] !== "\n") cj++;
          out.push(cdHl("wb-hl-cmt", s.slice(i, cj)));
          i = cj;
          pendingFn = false;
          continue;
        }
        if (s[i] === '"' || s[i] === "'") {
          var q = s[i];
          var sj = i + 1;
          while (sj < n && s[sj] !== q) {
            if (s[sj] === "\\") sj++;
            sj++;
          }
          if (sj < n) sj++;
          out.push(cdHl("wb-hl-str", s.slice(i, sj)));
          i = sj;
          pendingFn = false;
          continue;
        }
        if (/[a-zA-Z_]/.test(s[i])) {
          var wm = s.slice(i).match(/^[A-Za-z_]\w*/);
          var w = wm ? wm[0] : s[i];
          var cls = "wb-hl-op";
          if (PY_KW.test(w)) {
            cls = "wb-hl-kw";
            pendingFn = w === "def" || w === "class";
          } else if (pendingFn) {
            cls = "wb-hl-fn";
            pendingFn = false;
          } else if (PY_BI.test(w)) {
            cls = "wb-hl-builtin";
          } else if (/^\s*\(/.test(s.slice(i + w.length))) {
            cls = "wb-hl-fn";
          }
          out.push(cdHl(cls, w));
          i += w.length;
          continue;
        }
        if (/\d/.test(s[i])) {
          var dm = s.slice(i).match(/^\d+(?:\.\d+)?/);
          out.push(cdHl("wb-hl-num", dm ? dm[0] : s[i]));
          i += dm ? dm[0].length : 1;
          pendingFn = false;
          continue;
        }
        out.push(cdEsc(s[i]));
        if (!/\s/.test(s[i])) pendingFn = false;
        i++;
      }
      return out.join("");
    }
    function cdHighlightVue(src) {
      var s = String(src || "");
      if (/<(template|script|style)\b/i.test(s)) {
        return s.replace(/(<(template|script|style)\b[^>]*>)([\s\S]*?)(<\/\2>)/gi, function (_all, open, kind, body, close) {
          var k = String(kind || "").toLowerCase();
          var mid =
            k === "script"
              ? cdHighlightJs(body)
              : k === "style"
                ? cdHighlightCss(body)
                : cdHighlightHtml(body);
          return cdHighlightTag(open) + mid + cdHighlightTag(close);
        });
      }
      return cdHighlightHtml(s);
    }
    function cdHighlightCode(lang, code) {
      var show = String(code || "");
      if (!show) return "";
      var lg = String(lang || "text").toLowerCase();
      if (lg === "vue") return cdHighlightVue(show);
      if (lg === "html" || lg === "xml") return cdHighlightHtml(show);
      if (/^(javascript|js|jsx|typescript|ts|tsx)$/.test(lg)) return cdHighlightJs(show);
      if (/^(python|py)$/.test(lg)) return cdHighlightPython(show);
      if (lg === "json") return cdHighlightJson(show);
      if (/^(css|scss|less)$/.test(lg)) return cdHighlightCss(show);
      return cdEsc(show);
    }
    function cdInline(s) {
      var raw = String(s || "");
      if (cdLineLooksLikeCode(raw) || (raw.indexOf("\n") >= 0 && cdGuessLang(raw) !== "text")) {
        return cdEsc(cdStripLineBackticks(raw));
      }
      var t = cdEsc(raw);
      t = t.replace(/`([^`\n]+)`/g, function (_all, inner) {
        var v = String(inner || "");
        if (v.length > 48 || cdLineLooksLikeCode(v) || /[{};=<>]|import |const |function |from /.test(v)) {
          return v;
        }
        return "<code>" + v + "</code>";
      });
      t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      return t;
    }
    function cdDeliveryStarts(t) {
      var s = String(t || "");
      var starts = [];
      var m;
      var re1 = /一句话结论/g;
      while ((m = re1.exec(s))) starts.push(m.index);
      var re2 = /(^|\n|[。．])([ \t]*#{0,3}[ \t]*)说明方案/g;
      while ((m = re2.exec(s))) {
        starts.push(m.index + (m[1] ? m[1].length : 0) + (m[2] ? m[2].length : 0));
      }
      var re3 = /(^|\n)\s*#{1,3}\s*说明方案/g;
      while ((m = re3.exec(s))) starts.push(m.index + (m[1] ? m[1].length : 0));
      var re4 = /(^|\n)\s*\*\*结论\*\*/g;
      while ((m = re4.exec(s))) starts.push(m.index + (m[1] ? m[1].length : 0));
      starts.sort(function (a, b) { return a - b; });
      var uniq = [];
      starts.forEach(function (at) {
        if (!uniq.length || at !== uniq[uniq.length - 1]) uniq.push(at);
      });
      return uniq;
    }
    function cdStripLineBackticks(line) {
      var s = String(line || "").trim();
      var m = s.match(/^`([^`]+)`$/);
      return m ? m[1] : String(line || "");
    }
    function cdGuessLang(text) {
      var t = String(text || "");
      if (/<(script|template|style)[\s>]|<el-[\w-]+/i.test(t)) return "vue";
      if (/\b(from __future__|mapped_column|sqlalchemy|async def |@router|@app\.)/.test(t)) return "python";
      if (/^\s*(def |class \w+|from \w+ import)/m.test(t)) return "python";
      if (/\b(import |export |const |let |function |=>)/.test(t)) return "javascript";
      if (/^\s*(from |import |class |def )/m.test(t)) return "python";
      return "text";
    }
    function cdLineLooksLikeCode(line) {
      var s = cdStripLineBackticks(line).trim();
      if (!s || /^```/.test(s)) return false;
      if (/^(from\s+\S+|import\s+|def\s+|class\s+|async\s+def|@router|@app|@\w|#\s|if\s+|elif\s+|else:|for\s+|while\s+|return\s+|try:|except|with\s+|pass\b|raise\b)/.test(s)) {
        return true;
      }
      if (/^(const |let |var |function |export |import |class |async )/.test(s)) return true;
      if (/^<script[\s>]/i.test(s) || /^<\/script>/i.test(s) || /^<template[\s>]/i.test(s) || /^<style[\s>]/i.test(s)) {
        return true;
      }
      if (/^\s*(<[\w-]+|<\/[\w-]+|<template|<script|<style|el-[\w-]+)/i.test(s)) return true;
      if (/^[A-Z_][A-Z0-9_]*\s*=/.test(s)) return true;
      if (/^\s*[})];?\s*$/.test(s)) return true;
      if (/[{}();=<>]/.test(s) && (s.match(/[\u4e00-\u9fff]/g) || []).length < 4) return true;
      if (/^\s{2,}\S/.test(String(line || ""))) return true;
      return false;
    }
    function cdLineLooksLikeProse(line) {
      var s = cdStripLineBackticks(line).trim();
      if (!s || cdLineLooksLikeCode(s)) return false;
      if (/[\u4e00-\u9fff]/.test(s) && !/[{};=<>]|import |const |function |from |def |class /.test(s)) return true;
      return false;
    }
    function cdRepairFlattenedCode(text, lang) {
      var s = String(text || "");
      if (!s) return s;
      var lg = String(lang || cdGuessLang(s) || "text").toLowerCase();
      s = s
        .replace(/(import)([A-Za-z_])/g, "$1 $2")
        .replace(/(from)(['"])/g, "$1 $2")
        .replace(/([A-Za-z0-9_\"'`)\]])(from|import|class|def|const|let|var|function|export|async|return)\b/g, "$1\n$2")
        .replace(/(\"{3}|'{3})([A-Za-z_])/g, "$1\n$2")
        .replace(/(#[^\n]*?)([A-Za-z_]\w*\s*[:=])/g, "$1\n$2")
        .replace(/(\})(const|let|var|function|import|export|class)\b/g, "$1\n$2");
      if (lg === "python" || lg === "py") {
        return s
          .replace(/([;)\]}])(from\s+\w+\s+import\s+)/g, "$1\n$2")
          .replace(/([;)\]}])(import\s+\w+)/g, "$1\n$2")
          .replace(/([^\n:])(class\s+\w+)/g, "$1\n\n$2")
          .replace(/([^\n:])(def\s+\w+)/g, "$1\n\n$2")
          .replace(/([^\n])(@\w+)/g, "$1\n$2")
          .replace(/datetimeimport/g, "datetime\nimport")
          .replace(/timedelta(from|import)/g, "timedelta\n$1")
          .replace(/(\w)(Mapped\[)/g, "$1\n    $2");
      }
      if (lg === "vue" || lg === "html" || lg === "xml") {
        return s
          .replace(/>\s*(<[\w-/!])/g, ">\n$1")
          .replace(/(\/>)\s*(<[\w-/!])/g, "$1\n$2");
      }
      if (/^(javascript|js|jsx|typescript|ts|tsx)$/.test(lg)) {
        return s
          .replace(/([;{}])(const |let |var |function |class |export |import )/g, "$1\n$2")
          .replace(/([;{}])(async function )/g, "$1\n$2");
      }
      return s;
    }
    function cdIsExplorationProse(text) {
      var t = String(text || "").trim();
      if (!t) return false;
      if (cdLineLooksLikeCode(t)) return false;
      if (cdDeliveryStarts(t).length) return false;
      if (/frontend\/|backend\/|\.vue|\.js|AppLayout|router\/|已删除|改为|重定向/.test(t)) return false;
      if (t.indexOf("```") >= 0) return false;
      // 引擎流式过程句：绝不当探索文剥掉（曾用 length>72 整段当探索 → 正文被清空）
      if (
        /开始处理删除|阶段\s*\d+\s*\/\s*\d+|本机验尸|已删除|已修补|正在同步|引擎将删除|引擎直接删除|无需再删|删除清单|验尸通过|下线「/.test(
          t,
        )
      ) {
        return false;
      }
      var compact = t.replace(/\s+/g, "");
      // 仅短旁白且命中探索口吻才剥；长文不得因含「发现/准备」整段清空
      if (compact.length > 96) return false;
      return /正在定位|正在搜索|正在分析|正在探索|先定位|开始分析|接下来|准备|沙箱|未发现|怀疑|发现|宿主机|git |已理解需求|将按 A/.test(
        t,
      );
    }
    function cdStripExplorationFromProcess(text) {
      var t = String(text || "").replace(/\r\n/g, "\n").trim();
      if (!t) return "";
      if (t.indexOf("```") >= 0) return t;
      var paras = t.split(/\n{2,}/);
      var kept = [];
      paras.forEach(function (para) {
        var chunk = String(para || "").trim();
        if (!chunk) return;
        if (cdIsExplorationProse(chunk)) return;
        kept.push(chunk);
      });
      return kept.join("\n\n").trim();
    }
    function cdProcessOverlapsThink(processText, thinkText) {
      var p = String(processText || "").replace(/\s+/g, "").trim();
      var th = String(thinkText || "").replace(/\s+/g, "").trim();
      if (!p || !th) return false;
      // 仅当过程正文几乎整段被思考区覆盖时才隐藏，避免误杀流式正文
      if (p.length < 24) return false;
      if (p.length > 96 && th.indexOf(p.slice(0, 96)) >= 0) return true;
      if (p.length <= 160 && th.indexOf(p) >= 0 && p.length / Math.max(th.length, 1) > 0.85) return true;
      return false;
    }
    function cdRouteStreamChannels(text) {
      var t = cdStripBoilerplate(String(text || "")).replace(/\r\n/g, "\n");
      if (!t.trim()) return { process: "", delivery: "" };
      var starts = cdDeliveryStarts(t);
      if (!starts.length) {
        if (/^(说明方(?:案)?|一句话结论?|(\*\*)?结论(\*\*)?)/.test(t.trim())) {
          return { process: "", delivery: t.trim() };
        }
        return { process: cdStripExplorationFromProcess(t.trim()), delivery: "" };
      }
      var d0 = starts[starts.length - 1];
      return {
        process: cdStripExplorationFromProcess(t.slice(0, starts[0]).replace(/[ \t。.;；、，]+$/g, "").trim()),
        delivery: t.slice(d0).trim(),
      };
    }
    function cdSplitDelivery(text) {
      var routed = cdRouteStreamChannels(text);
      return { process: routed.process, delivery: routed.delivery };
    }
    function cdDedupeLines(arr) {
      var out = [];
      (arr || []).forEach(function (s) {
        var t = String(s || "").replace(/\s+/g, " ").trim();
        if (!t) return;
        var dup = out.some(function (x) {
          var y = String(x || "").replace(/\s+/g, " ").trim();
          if (t === y) return true;
          if (t.length > 48 && y.indexOf(t.slice(0, 48)) >= 0) return true;
          if (y.length > 48 && t.indexOf(y.slice(0, 48)) >= 0) return true;
          return false;
        });
        if (!dup) out.push(String(s || "").trim());
      });
      return out;
    }
    function cdNormalizeDelivery(text) {
      var t = String(text || "").replace(/\r\n/g, "\n").trim();
      t = t.replace(/^#{0,3}[ \t]*说明方案[ \t]*/m, "");
      t = t.replace(/一句话结论[ \t]*[：:]?[ \t]*/g, "结论\n");
      t = t.replace(/^#{0,3}[ \t]*(?:一句话结论|说明方案)\b[ \t]*[：:]?[ \t]*/m, "结论\n");
      t = t.replace(/未改动文件/g, "未改动。\n改动文件\n");
      t = t.replace(/行为约定/g, "\n行为约定\n");
      t = t.replace(/\s*-?\s*(已删除|保留|未改动)[：:]/g, "\n$1：");
      t = t.replace(/\s+-\s+(frontend|backend|apps|src|desktop|host)\//g, "\n- $1/");
      t = t.replace(/^[ \t]*\*\*(结论|改动文件|行为约定|验收)\*\*[ \t]*[：:]?[ \t]*/gm, "$1\n");
      t = t.replace(/^[ \t]*\*\*?结论\*\*?[ \t]*[：:]?[ \t]*/gm, "结论\n");
      t = t.replace(/^[ \t]*做了什么[ \t]*[：:]?[ \t]*/gm, "结论\n");
      t = t.replace(/^[ \t]*改动文件表?[ \t]*[：:]?[ \t]*/gm, "改动文件\n");
      t = t.replace(/^[ \t]*行为约定[ \t]*[：:]?[ \t]*/gm, "行为约定\n");
      t = t.replace(/^[ \t]*验收(?:步骤)?[ \t]*[：:]?[ \t]*/gm, "验收\n");
      t = t.replace(/\n{3,}/g, "\n\n");
      return t.trim();
    }
    function cdIsToolEcho(s) {
      var t = String(s || "").trim().replace(/`/g, "");
      if (/^(搜索|查找文件|列出|写入|阅读|查看|语义搜索)$/.test(t)) return true;
      if (!/^(阅读|查看|写入|列出|搜索|查找文件|语义搜索)\s+\S/.test(t)) return false;
      if (/[\/\\]/.test(t) || /\.\w{1,10}\b/.test(t)) return true;
      var rest = t.replace(/^(阅读|查看|写入|列出|搜索|查找文件|语义搜索)\s+/, "");
      return /^(frontend|backend|apps|src|desktop|host|DSH-ZR-WorkBuddy|pythonProject[\w.-]*|[A-Za-z0-9_.-]+)$/i.test(rest);
    }
    function cdScrubAbs(text) {
      return cdStripBoilerplate(
        String(text || "")
          .replace(/\/[^\s\"']*sandboxes\/ldj-[a-f0-9]+\//gi, "")
          .replace(/\/Users\/[^\s\"']+\/sandboxes\/ldj-[a-f0-9]+\//gi, ""),
      );
    }
    function cdScrubProcess(text) {
      var t = cdScrubAbs(text);
      var inFence = false;
      return t
        .split("\n")
        .map(function (line) {
          var raw = String(line || "");
          if (raw.trim().indexOf("```") === 0) {
            inFence = !inFence;
            return line;
          }
          if (inFence) return line;
          if (cdLineLooksLikeCode(raw)) return "";
          if (/^\s*-\s+(阅读|查看|搜索|查找文件|写入|列出|修改|执行|检索)/.test(raw)) {
            return raw;
          }
          var scrubbed = raw
            .replace(/(?:阅读|查看|搜索|查找文件|写入|列出|语义搜索)\s*`[^`]+`/g, "")
            .replace(
              /(?:阅读|查看|搜索|查找文件|写入|列出|语义搜索)\s+(?:frontend|backend|apps|src|desktop|host)\/[\w./@-]+/gi,
              "",
            )
            .replace(
              /(?:阅读|查看|搜索|查找文件|写入|列出|语义搜索)\s+(frontend|backend|apps|src|desktop|host|DSH-ZR-WorkBuddy|pythonProject[\w.-]*|agent-transcripts)\b/gi,
              "",
            )
            .replace(/(?:阅读|查看|写入|列出)\s+[\w./@-]+\.[A-Za-z0-9]+/g, "");
          var keep = [];
          scrubbed.split(/[。．]/).forEach(function (b) {
            var s = b.trim();
            if (!s) return;
            if (cdIsToolEcho(s)) return;
            keep.push(s);
          });
          return keep.join("。");
        })
        .join("\n")
        // 保留空行：过程步骤靠空行分段，滤掉会导致整段糊成一行
        .replace(/\n{3,}/g, "\n\n")
        .replace(/^\n+|\n+$/g, "");
    }
    function cdLooksLikeFileChange(line) {
      var s = String(line || "").trim();
      if (!s || s.length > 400) return false;
      if (/^(frontend|backend|apps|src|desktop|host)\//.test(s)) return true;
      return /^[\w./@-]+\.[A-Za-z0-9]+(?:\s*[—–-]\s+\S)/.test(s);
    }
    function cdIsSepOnly(line) {
      var s = String(line || "").trim();
      return /-{3,}/.test(s) && /^[-–—|: \t]+$/.test(s);
    }
    function cdIsJunkHeader(line) {
      var s = String(line || "").replace(/\t+/g, " ").trim();
      if (cdIsSepOnly(s)) return true;
      return /^(列|说明|文件)(\s+(列|说明|文件))*$/.test(s);
    }
    function cdIsPipeTableStart(lines, i) {
      var a = String(lines[i] || "");
      var b = String(lines[i + 1] || "");
      return /^\s*\|/.test(a) && /\|/.test(a) && /^\s*\|?\s*[-:| ]+$/.test(b) && /-{3,}/.test(b);
    }
    function cdSplitKv(line) {
      var s = String(line || "");
      if (/\t/.test(s)) {
        var p = s.split("\t").map(function (c) { return c.trim(); }).filter(Boolean);
        if (p.length >= 2) return p;
      }
      var dash = s.split(/\s+[—–]\s+/);
      if (dash.length === 2 && dash[0].trim() && dash[1].trim()) {
        return [dash[0].trim(), dash[1].trim()];
      }
      return null;
    }
    function cdFileLi(pathPart, desc) {
      var path = String(pathPart || "").trim();
      var extra = String(desc || "").trim();
      if (path.indexOf("\t") >= 0) {
        var tb = path.split("\t").map(function (x) { return x.trim(); }).filter(Boolean);
        path = tb[0] || path;
        extra = extra || tb.slice(1).join(" ");
      }
      var dm = path.split(/\s+[—–-]\s+/);
      if (dm.length >= 2 && !extra) {
        path = dm[0].trim();
        extra = dm.slice(1).join(" — ").trim();
      }
      return (
        "<li><code>" +
        cdEsc(path) +
        "</code>" +
        (extra ? "：" + cdInline(extra) : "") +
        "</li>"
      );
    }
    function cdExplodeFileChunks(s) {
      return String(s || "")
        .split(/(?=\s*-\s*(?:frontend|backend|apps|src|desktop|host)\/)/)
        .map(function (x) {
          return x.replace(/^[-*]\s*/, "").trim();
        })
        .filter(Boolean);
    }
    function cdBuildDocProseHtml(t) {
      var conclusion = [];
      var files = [];
      var rules = [];
      var checks = [];
      var mode = "conclusion";
      function pushFile(chunk) {
        var path = String(chunk || "").replace(/`/g, "");
        var sp = path.split(/[：:]/);
        if (sp.length < 2) sp = path.split(/\s+[—–-]\s+/);
        files.push({ path: (sp[0] || path).trim(), desc: sp.slice(1).join("：").trim() });
      }
      String(t || "")
        .split("\n")
        .forEach(function (line) {
          var s = line.trim().replace(/^[-*]\s+/, "");
          if (!s) return;
          var body = s.replace(/^#{1,3}\s*/, "");
          if (/^(结论|一句话结论|做了什么|说明方案)/.test(body)) {
            mode = "conclusion";
            var rest = body.replace(/^(说明方案|一句话结论|做了什么|结论)[：:]?/, "").trim();
            if (rest) conclusion.push(rest);
            return;
          }
          if (/^改动文件/.test(body)) {
            mode = "files";
            var after = body.replace(/^改动文件表?[：:]?/, "").trim();
            if (after) cdExplodeFileChunks(after).forEach(pushFile);
            return;
          }
          if (/^行为约定/.test(body)) {
            mode = "rules";
            var rrest = body.replace(/^行为约定[：:]?/, "").trim();
            if (rrest) rules.push(rrest);
            return;
          }
          if (/^验收/.test(body)) {
            mode = "checks";
            // 标题行「验收 / 验收步骤」本身不要进列表（否则会出现「1. 验收」）
            var crest = body
              .replace(/^验收(?:步骤)?[：:]?/, "")
              .trim()
              .replace(/^\d+[\.、]\s*/, "");
            if (crest) checks.push(crest);
            return;
          }
          if (/^(已删除|保留|未改动)/.test(s)) {
            mode = "rules";
            rules.push(s);
            return;
          }
          if (/^\d+[\.、]/.test(s)) {
            mode = "checks";
            checks.push(s.replace(/^\d+[\.、]\s*/, ""));
            return;
          }
          var chunks = cdExplodeFileChunks(s);
          var looksFiles =
            chunks.length > 1 ||
            cdLooksLikeFileChange(s) ||
            /^(frontend|backend|apps|src|desktop|host)\//.test(s) ||
            /`[^`]+\/[^`]+\.[A-Za-z0-9]+`/.test(s);
          if (looksFiles) {
            mode = "files";
            chunks.forEach(pushFile);
            return;
          }
          if (mode === "files" && files.length) {
            files[files.length - 1].desc += (files[files.length - 1].desc ? " " : "") + s;
            return;
          }
          if (mode === "rules") {
            rules.push(s);
            return;
          }
          if (mode === "checks") {
            checks.push(s);
            return;
          }
          conclusion.push(s);
        });
      conclusion = cdDedupeLines(conclusion);
      rules = cdDedupeLines(rules);
      checks = cdDedupeLines(checks);
      var html = "";
      if (conclusion.length) {
        html += "<h3>结论</h3>";
        String(conclusion.join(" "))
          .split(/([。！？])/)
          .reduce(function (acc, part, idx, arr) {
            if (/[。！？]/.test(part)) return acc;
            var mark = arr[idx + 1] && /[。！？]/.test(arr[idx + 1]) ? arr[idx + 1] : "";
            var s = (part + mark).trim();
            if (s) acc.push("<p>" + cdInline(s) + "</p>");
            return acc;
          }, [])
          .forEach(function (p) {
            html += p;
          });
      }
      if (files.length) {
        html +=
          "<h3>改动文件</h3><ul>" +
          files
            .map(function (f) {
              return cdFileLi(f.path, f.desc);
            })
            .join("") +
          "</ul>";
      }
      if (rules.length) {
        html +=
          "<h3>行为约定</h3><ul>" +
          rules
            .map(function (r) {
              return "<li>" + cdInline(r) + "</li>";
            })
            .join("") +
          "</ul>";
      }
      if (checks.length) {
        html +=
          "<h3>验收</h3><ol>" +
          checks
            .map(function (c) {
              return "<li>" + cdInline(c) + "</li>";
            })
            .join("") +
          "</ol>";
      }
      return html;
    }
    function cdStripAllCodeText(text) {
      var raw = String(text || "").replace(/\r\n/g, "\n");
      if (!raw.trim()) return "";
      if (raw.indexOf("```") >= 0) {
        var out = [];
        cdFenceParts(raw).forEach(function (part) {
          if (part.t === "code") return;
          var prose = cdStripAllCodeText(part.v);
          if (String(prose || "").trim()) out.push(prose);
        });
        return out.join("\n\n");
      }
      return cdStripBareCodeText(raw);
    }
    function cdBuildDocHtml(raw) {
      // 说明方案也不展示代码片段
      var prepared = cdStripAllCodeText(cdScrubAbs(cdNormalizeDelivery(raw)).replace(/\*\*/g, ""));
      if (!String(prepared || "").trim()) return "";
      return cdBuildDocProseHtml(prepared) || cdMdBlocksProse(prepared);
    }
    function cdStripBareCodeText(text) {
      var raw = String(text || "").replace(/\r\n/g, "\n");
      if (!raw.trim()) return "";
      if (raw.indexOf("```") >= 0) {
        var out = [];
        cdFenceParts(raw).forEach(function (part) {
          if (part.t === "code") {
            var body = String(part.v || "").trim();
            if (!body && !part.streaming) return;
            var lang = part.lang || cdGuessLang(body) || "text";
            out.push("```" + lang + "\n" + cdRepairFlattenedCode(body, lang) + "\n```");
            return;
          }
          var prose = cdStripBareCodeText(part.v);
          if (String(prose || "").trim()) out.push(prose);
        });
        return out.join("\n\n");
      }
      var kept = [];
      raw.split("\n").forEach(function (line) {
        var rawLine = String(line || "");
        if (/^```/.test(rawLine.trim())) return;
        var inner = cdStripLineBackticks(rawLine).trim();
        if (cdLineLooksLikeCode(inner) && !cdLineLooksLikeProse(rawLine)) return;
        if (inner) kept.push(rawLine);
      });
      return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    }
    function cdWrapCodeRunsInner(text) {
      var lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
      var out = [];
      var run = [];
      function flushRun() {
        if (!run.length) return;
        var norm = run.map(function (ln) {
          return cdStripLineBackticks(ln);
        });
        var body = norm.join("\n").replace(/^\n+|\n+$/g, "");
        run = [];
        if (!body.trim()) return;
        var lang = cdDetectCodeLangFromLines(norm) || cdGuessLang(body);
        if (lang === "text" && !cdLineLooksLikeCode(body.split("\n")[0] || "")) {
          out.push(body);
          return;
        }
        out.push("```" + lang + "\n" + cdRepairFlattenedCode(body, lang) + "\n```");
      }
      lines.forEach(function (line) {
        var raw = String(line || "");
        if (/^```/.test(raw.trim())) {
          flushRun();
          out.push(line);
          return;
        }
        var inner = cdStripLineBackticks(raw).trim();
        var wrapped = /^`[^`]+`$/.test(String(raw || "").trim());
        if (cdLineLooksLikeCode(raw) || wrapped || (run.length && !inner)) {
          run.push(wrapped ? inner : raw);
          return;
        }
        if (run.length && !cdLineLooksLikeProse(raw)) {
          run.push(raw);
          return;
        }
        flushRun();
        out.push(line);
      });
      flushRun();
      return out.join("\n");
    }
    function cdForceCodeFences(text) {
      var raw = String(text || "").replace(/\r\n/g, "\n");
      if (!raw.trim()) return raw;
      if (raw.indexOf("```") < 0) return cdWrapCodeRunsInner(raw);
      var out = [];
      cdFenceParts(raw).forEach(function (part) {
        if (part.t === "code") {
          var body = String(part.v || "").trim();
          if (!body && !part.streaming) return;
          var lang = part.lang || cdGuessLang(body) || "text";
          out.push("```" + lang + "\n" + cdRepairFlattenedCode(body, lang) + "\n```");
          return;
        }
        var prose = cdWrapCodeRunsInner(String(part.v || ""));
        if (String(prose || "").trim()) out.push(prose);
      });
      return out.join("\n\n");
    }
    function cdWrapCodeRuns(text) {
      return cdForceCodeFences(text);
    }
    function cdWrapMarkupRuns(text) {
      return cdForceCodeFences(text);
    }
    function cdNormalizeRawCodeFences(text) {
      var t = String(text || "").replace(/\r\n/g, "\n").trim();
      if (!t || t.indexOf("```") >= 0) return text || "";
      var langHead = t.match(/^(vue|javascript|typescript|python|json|html|css|bash|sh|sql|js|ts|tsx|jsx)\s*\n([\s\S]+)$/i);
      if (langHead && cdKnownLang(langHead[1].toLowerCase())) {
        return "```" + langHead[1].toLowerCase() + "\n" + langHead[2].trim() + "\n```";
      }
      var parts = t.split(/\n{2,}/);
      var out = [];
      var changed = false;
      parts.forEach(function (p) {
        var s = String(p || "").trim();
        if (!s) return;
        var lang = "";
        if (/^<(template|script|style)\b/i.test(s)) lang = "vue";
        else if (/^<[\w-]+/.test(s.trim()) || /<el-[\w-]+/.test(s)) lang = "vue";
        else if (/^(import |export |const |let |function |class |async function )/.test(s)) lang = "javascript";
        else if (/^(def |class .*:|from .* import)/.test(s)) lang = "python";
        else if (/^\{[\s\S]*\:\s*[\s\S]*\}$/.test(s) && s.indexOf('"') >= 0) lang = "json";
        if (lang) {
          changed = true;
          out.push("```" + lang + "\n" + s + "\n```");
        } else {
          out.push(s);
        }
      });
      return changed ? out.join("\n\n") : text || "";
    }
    function cdDetectCodeLangFromLines(para) {
      var lines = (para || []).map(function (l) {
        return cdStripLineBackticks(l);
      });
      if (!lines.length) return "";
      var joined = lines.join("\n").trim();
      if (!joined) return "";
      if (/^<script[\s>]/i.test(joined) || /<script[\s>]/i.test(joined)) return "vue";
      if (/^<(template|script|style)\b/i.test(joined)) return "vue";
      if (/^<[\w-]+/.test(joined.trim()) || /<el-[\w-]+/.test(joined)) return "vue";
      if (/^(import |export |const |let |function |class |async function )/m.test(joined)) return "javascript";
      if (/import\s+\{/.test(joined) && /from\s+['"]/.test(joined)) return "javascript";
      if (/^(def |class .*:|from .* import)/m.test(joined)) return "python";
      var head = lines[0].trim();
      if (/^(vue|javascript|typescript|python|json|html|css|bash|sh|sql|js|ts|tsx|jsx)$/i.test(head) && lines.length > 1) {
        return head.toLowerCase();
      }
      if (/^[\s<][\s\S]*>/.test(joined) && /<\/?[\w-]+/.test(joined)) return "vue";
      return "";
    }
    function cdCodeBodyFromPara(para, lang) {
      var lines = (para || []).map(function (l) {
        return cdStripLineBackticks(l);
      });
      var joined = lines.join("\n").trim();
      var head = lines[0] ? lines[0].trim() : "";
      if (
        lang &&
        head &&
        head.toLowerCase() === String(lang).toLowerCase() &&
        lines.length > 1
      ) {
        return lines.slice(1).join("\n").trim();
      }
      return joined;
    }
    function cdNormalizeFences(text) {
      var t = String(text || "").replace(/\r\n/g, "\n");
      t = t.replace(/([^\n])```/g, "$1\n```");
      t = t.replace(/```([A-Za-z][A-Za-z0-9_+-]*)\s*\{/g, "```$1\n{");
      t = t.replace(/\}```/g, "}\n```");
      return t;
    }
    function cdCodeExtForLang(lang) {
      var lg = String(lang || "text").toLowerCase();
      var map = {
        python: "py",
        py: "py",
        javascript: "js",
        js: "js",
        jsx: "jsx",
        typescript: "ts",
        ts: "ts",
        tsx: "tsx",
        vue: "vue",
        html: "html",
        css: "css",
        json: "json",
        bash: "sh",
        sh: "sh",
        sql: "sql",
        java: "java",
        go: "go",
        rust: "rs",
      };
      return map[lg] || "txt";
    }
    function cdCodeToolbarHtml(lang) {
      var ext = cdCodeExtForLang(lang);
      return (
        '<div class="wb-cd-codeacts">' +
        '<button type="button" class="wb-cd-codebtn" data-cd-copy title="复制代码">' +
        CD_ICON_COPY +
        '<span class="wb-cd-codebtn-label">复制</span></button>' +
        '<button type="button" class="wb-cd-codebtn" data-cd-download data-cd-ext="' +
        cdEsc(ext) +
        '" title="下载代码">' +
        CD_ICON_DOWNLOAD +
        '<span class="wb-cd-codebtn-label">下载</span></button></div>'
      );
    }
    function cdCodeHtml(lang, body, streaming) {
      var guessed = cdGuessLang(body);
      var langLabel = String(lang || guessed || "text").trim() || "text";
      if (langLabel === "text" && guessed !== "text") langLabel = guessed;
      var show = cdRepairFlattenedCode(String(body || ""), langLabel);
      if (!String(show || "").trim()) {
        if (streaming) show = "…";
        else return "";
      }
      var inner =
        streaming && show.length > 16000 ? cdEsc(show) : cdHighlightCode(langLabel, show);
      return (
        '<div class="wb-cd-codewrap' +
        (streaming ? " wb-cd-codewrap-streaming" : "") +
        '">' +
        '<div class="wb-cd-codebar">' +
        '<span class="wb-cd-codelang">' +
        cdEsc(langLabel) +
        "</span>" +
        cdCodeToolbarHtml(langLabel) +
        "</div>" +
        '<pre class="wb-cd-code"><code class="wb-hl-root">' +
        inner +
        "</code></pre></div>"
      );
    }
    function cdKnownLang(lang) {
      return /^(javascript|js|jsx|ts|tsx|typescript|vue|python|py|bash|sh|zsh|shell|json|html|css|scss|less|yaml|yml|diff|text|txt|plaintext|md|markdown|sql|go|rust|java|c|cpp|xml|toml|ini|dockerfile)$/i.test(
        String(lang || "").trim(),
      );
    }
    function cdSplitFenceLang(langLine) {
      var s = String(langLine || "").trim();
      var m = s.match(/^([A-Za-z][A-Za-z0-9_+-]*)([\s{\[\(<].*)?$/);
      if (m && cdKnownLang(m[1])) {
        return { lang: m[1], rest: String(m[2] || "").replace(/^\s+/, "") };
      }
      return { lang: s, rest: "" };
    }
    function cdFenceCloseAt(src, from) {
      var q = from;
      while (q < src.length) {
        var at = src.indexOf("```", q);
        if (at < 0) return -1;
        if (at === 0 || src[at - 1] === "\n") return at;
        q = at + 3;
      }
      return -1;
    }
    function cdFenceParts(raw) {
      var src = cdNormalizeFences(raw);
      var parts = [];
      var i = 0;
      while (i < src.length) {
        var start = src.indexOf("```", i);
        while (start > 0 && src[start - 1] !== "\n") {
          start = src.indexOf("```", start + 3);
        }
        if (start < 0) {
          parts.push({ t: "md", v: src.slice(i) });
          break;
        }
        if (start > i) parts.push({ t: "md", v: src.slice(i, start) });
        var after = start + 3;
        var nl = src.indexOf("\n", after);
        var langLine = ((nl < 0 ? src.slice(after) : src.slice(after, nl)) || "").trim();
        var splitLang = cdSplitFenceLang(langLine);
        var lang = splitLang.lang;
        var prefixBody = splitLang.rest;
        if (nl < 0) {
          if (cdKnownLang(lang) && prefixBody) {
            parts.push({ t: "code", lang: lang, v: prefixBody, streaming: true });
          } else if (cdKnownLang(lang)) {
            parts.push({ t: "code", lang: lang, v: "", streaming: true });
          } else {
            parts.push({ t: "md", v: src.slice(start).replace(/^```/, "") });
          }
          break;
        }
        var bodyStart = nl + 1;
        var close = cdFenceCloseAt(src, bodyStart);
        var rawBody = close < 0 ? src.slice(bodyStart) : src.slice(bodyStart, close);
        var body = ((prefixBody ? prefixBody + "\n" : "") + rawBody).replace(/\s+$/, "");
        var streaming = close < 0;
        if (cdKnownLang(lang)) {
          if (body || streaming) {
            parts.push({ t: "code", lang: lang || "text", v: body, streaming: streaming });
          }
          if (close < 0) break;
          i = close + 3;
          if (src[i] === "\n") i++;
          continue;
        }
        var junk =
          (!body && !streaming) ||
          /^[。．、，；;:!！？?\s`]+$/.test(body) ||
          (body.length < 12 && !cdKnownLang(lang) && /[\u4e00-\u9fff]/.test(body));
        if (junk || (!cdKnownLang(lang) && body.length < 48 && body.indexOf("\n") < 0 && !streaming)) {
          parts.push({ t: "md", v: body || lang });
          if (close < 0) break;
          i = close + 3;
          if (src[i] === "\n") i++;
          continue;
        }
        if (body || streaming) {
          parts.push({ t: "code", lang: lang || "text", v: body, streaming: streaming });
        }
        if (close < 0) break;
        i = close + 3;
        if (src[i] === "\n") i++;
      }
      return parts;
    }
    function cdPipeCells(line) {
      return String(line || "")
        .replace(/^\s*\|/, "")
        .replace(/\|\s*$/, "")
        .split("|")
        .map(function (c) {
          return c.trim();
        })
        .filter(Boolean);
    }
    function cdIsHeaderCells(cells) {
      var joined = (cells || []).join(" ");
      return /^(列|说明|文件|路径|改动)(\s+(列|说明|文件|路径|改动))*$/.test(joined);
    }
    function cdMdTable(rows) {
      var parsed = (rows || [])
        .filter(function (r) {
          return !cdIsSepOnly(r);
        })
        .map(cdPipeCells)
        .filter(function (r) {
          return r.length && !cdIsHeaderCells(r);
        });
      if (!parsed.length) return "";
      var items = parsed.map(function (r) {
        if (r.length >= 2 && (cdLooksLikeFileChange(r[0]) || /[./].+\.[A-Za-z0-9]+$/.test(r[0]))) {
          return cdFileLi(r[0], r.slice(1).join(" "));
        }
        if (r.length >= 2) {
          return (
            "<li><strong>" +
            cdInline(r[0]) +
            "</strong>：" +
            cdInline(r.slice(1).join(" ")) +
            "</li>"
          );
        }
        return "<li>" + cdInline(r[0]) + "</li>";
      });
      return "<ul>" + items.join("") + "</ul>";
    }
    function cdSectionTitle(line) {
      return String(line || "")
        .trim()
        .replace(/^#{1,3}\s*/, "")
        .replace(/^\*\*|\*\*$/g, "")
        .replace(/[\t ]+$/, "")
        .replace(/[:：]\s*$/, "");
    }
    function cdIsSectionLine(line) {
      var section = cdSectionTitle(line);
      return /^(说明方案|一句话结论|结论|做了什么|改动文件表|改动文件|行为约定.*|验收步骤|验收|菜单与路由|后端接口|页面功能|路由\/菜单|接口)$/.test(
        section,
      );
    }
    function cdProcNodeKind(tag, lines) {
      var blob = [tag].concat(lines || []).join(" ");
      if (/搜索|检索|查找|grep|Glob|定位待删|网页/.test(blob)) return "search";
      if (/查看|阅读|浏览|Read|打开|核对|确认.*路由|确认.*菜单|读盘/.test(blob)) return "read";
      if (/删除清单|清单|待删路径|阶段\s*\d+/.test(blob) || tag === "清单") return "list";
      return "dot";
    }
    function cdProcNodeHtml(kind, isLast) {
      var k = kind || "dot";
      var live = isLast ? " is-live" : "";
      if (k === "search") {
        return (
          '<span class="wb-cd-proc-node is-search' +
          live +
          '" aria-hidden="true">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg></span>'
        );
      }
      if (k === "read") {
        return (
          '<span class="wb-cd-proc-node is-read' +
          live +
          '" aria-hidden="true">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M7 4h8l3 3v13H7V4z"/><path d="M15 4v3h3"/><path d="M9 12h6M9 16h6"/></svg></span>'
        );
      }
      if (k === "list") {
        return (
          '<span class="wb-cd-proc-node is-list' +
          live +
          '" aria-hidden="true">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M8 7h11M8 12h11M8 17h11"/><circle cx="4.5" cy="7" r="1" fill="currentColor" stroke="none"/>' +
          '<circle cx="4.5" cy="12" r="1" fill="currentColor" stroke="none"/>' +
          '<circle cx="4.5" cy="17" r="1" fill="currentColor" stroke="none"/></svg></span>'
        );
      }
      return '<span class="wb-cd-proc-node is-dot' + live + '" aria-hidden="true"></span>';
    }
    function cdMdBlocksProseProcess(text) {
      // 过程正文：一步一块，方便扫读（不再把相邻行拼成一大段）
      var raw = String(text || "").replace(/\r\n/g, "\n");
      raw = raw
        .replace(
          /([^\n])\n(?!\n)(阶段\s*\d+\s*\/\s*\d+|开始处理|Cursor 定位说明|本机验尸|本机核对|本机代码已核对|正在同步|正在本机|已删除|已修补|定位过程|引擎将|引擎校验|引擎直接)/g,
          "$1\n\n$2",
        )
        .replace(/(Cursor 定位说明[：:])\s*/g, "$1\n")
        .replace(/([、，])(`(?:frontend|backend|apps|src)\/[^`]+`)/g, "$1\n$2");
      var chunks = raw
        .split(/\n{2,}/)
        .map(function (c) {
          return String(c || "").trim();
        })
        .filter(Boolean);
      if (!chunks.length) return "";
      var items = [];
      chunks.forEach(function (chunk) {
        var lines = chunk
          .split("\n")
          .map(function (ln) {
            return String(ln || "").trim();
          })
          .filter(function (ln) {
            return ln && !cdIsJunkHeader(ln) && !cdLineLooksLikeCode(ln);
          });
        if (!lines.length) return;
        var tag = "";
        var first = lines[0];
        var mStage = first.match(/^(阶段\s*\d+\s*\/\s*\d+)[：:]\s*(.*)$/);
        var mCursor = first.match(/^Cursor 定位说明[：:]?\s*(.*)$/i);
        var mPlan = first.match(/^#{0,3}\s*删除清单\s*$/);
        if (mStage) {
          tag = String(mStage[1] || "").replace(/\s+/g, "");
          var rest = String(mStage[2] || "").trim();
          lines = rest ? [rest].concat(lines.slice(1)) : lines.slice(1);
        } else if (mCursor) {
          tag = "定位";
          var restC = String(mCursor[1] || "").trim();
          lines = restC ? [restC].concat(lines.slice(1)) : lines.slice(1);
        } else if (mPlan) {
          tag = "清单";
          lines = lines.slice(1);
        }
        if (!lines.length) return;
        var pathLines = [];
        var textLines = [];
        lines.forEach(function (ln) {
          var pathOnly = ln.replace(/^[-*]\s*/, "").replace(/^`([^`]+)`$/, "$1");
          var mBullet = ln.match(/^[-*]\s+`([^`]+)`\s*[：:]?\s*(.*)$/);
          if (mBullet) {
            pathLines.push({ path: mBullet[1], desc: String(mBullet[2] || "").trim() });
            return;
          }
          if (/^(frontend|backend|apps|src)\//.test(pathOnly) && pathOnly.indexOf(" ") < 0) {
            pathLines.push({ path: pathOnly, desc: "" });
            return;
          }
          textLines.push(ln);
        });
        var kind = cdProcNodeKind(tag, textLines.length ? textLines : lines);
        var bodyHtml = "";
        if (tag) {
          bodyHtml += '<div class="wb-cd-proc-meta">' + cdInline(tag) + "</div>";
        }
        bodyHtml += textLines
          .map(function (ln) {
            return '<div class="wb-cd-proc-t">' + cdInline(ln) + "</div>";
          })
          .join("");
        if (pathLines.length) {
          if (tag === "清单" || kind === "list") {
            bodyHtml +=
              '<ul class="wb-cd-proc-links">' +
              pathLines
                .map(function (p) {
                  return (
                    "<li>" +
                    "<code>" +
                    cdInline(p.path) +
                    "</code>" +
                    (p.desc ? "：" + cdInline(p.desc) : "") +
                    "</li>"
                  );
                })
                .join("") +
              "</ul>";
          } else {
            bodyHtml += pathLines
              .map(function (p) {
                return '<div class="wb-cd-proc-path">' + cdInline(p.path) + (p.desc ? "：" + cdInline(p.desc) : "") + "</div>";
              })
              .join("");
          }
        }
        items.push({ kind: kind, bodyHtml: bodyHtml });
      });
      if (!items.length) return "";
      return (
        '<ul class="wb-cd-proc">' +
        items
          .map(function (it, idx) {
            return (
              '<li class="wb-cd-proc-li">' +
              '<span class="wb-cd-proc-rail">' +
              cdProcNodeHtml(it.kind, idx === items.length - 1) +
              "</span>" +
              '<div class="wb-cd-proc-body">' +
              it.bodyHtml +
              "</div></li>"
            );
          })
          .join("") +
        "</ul>"
      );
    }
    function cdMdBlocksProse(text) {
      var lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
      var html = [];
      var i = 0;
      while (i < lines.length) {
        var line = lines[i];
        if (!String(line || "").trim() || cdIsJunkHeader(line)) {
          i++;
          continue;
        }
        if (cdLineLooksLikeCode(line)) {
          var codeRun = [line];
          i++;
          while (
            i < lines.length &&
            (cdLineLooksLikeCode(lines[i]) ||
              !String(lines[i] || "").trim() ||
              /^\s{2,}\S/.test(String(lines[i] || "")))
          ) {
            if (String(lines[i] || "").trim()) codeRun.push(lines[i]);
            else if (codeRun.length) codeRun.push(lines[i]);
            i++;
          }
          var lang0 = cdDetectCodeLangFromLines(codeRun) || cdGuessLang(codeRun.join("\n"));
          if (lang0 !== "text" || cdLineLooksLikeCode(codeRun[0])) {
            html.push(cdCodeHtml(lang0 === "text" ? "javascript" : lang0, cdCodeBodyFromPara(codeRun, lang0), false));
            continue;
          }
        }
        var conc = String(line || "").match(/^#{0,3}\s*一句话结论\s*[：:]?\s*(.*)$/);
        if (conc && String(line || "").indexOf("一句话结论") >= 0) {
          html.push("<h3>一句话结论</h3>");
          if (String(conc[1] || "").trim()) {
            html.push("<p>" + cdInline(conc[1].trim()) + "</p>");
          }
          i++;
          continue;
        }
        var strippedLine = String(line || "").replace(/[\t ]+$/, "");
        if (cdIsSectionLine(strippedLine) && strippedLine.indexOf("\t") < 0) {
          html.push("<h3>" + cdInline(cdSectionTitle(strippedLine)) + "</h3>");
          i++;
          continue;
        }
        if (/^\s*\|/.test(line) || cdIsPipeTableStart(lines, i)) {
          var pipeRows = [];
          while (i < lines.length && (/^\s*\|/.test(lines[i] || "") || cdIsSepOnly(lines[i]))) {
            pipeRows.push(lines[i]);
            i++;
          }
          html.push(cdMdTable(pipeRows));
          continue;
        }
        if (/^### /.test(line)) {
          html.push("<h4>" + cdInline(line.slice(4)) + "</h4>");
          i++;
          continue;
        }
        if (/^## /.test(line)) {
          html.push("<h3>" + cdInline(line.slice(3)) + "</h3>");
          i++;
          continue;
        }
        if (/^# /.test(line)) {
          html.push("<h3>" + cdInline(line.slice(2)) + "</h3>");
          i++;
          continue;
        }
        if (/^[-*] /.test(line)) {
          var ul = [];
          while (i < lines.length && /^[-*] /.test(lines[i])) {
            ul.push("<li>" + cdInline(lines[i].replace(/^[-*] /, "")) + "</li>");
            i++;
          }
          html.push("<ul>" + ul.join("") + "</ul>");
          continue;
        }
        if (/^\d+\.\s/.test(line) || /^\d+\t/.test(line)) {
          var ol = [];
          while (i < lines.length && (/^\d+\.\s/.test(lines[i]) || /^\d+\t/.test(lines[i]))) {
            ol.push(
              "<li>" +
                cdInline(String(lines[i]).replace(/^\d+\.\s*/, "").replace(/^\d+\t\s*/, "")) +
                "</li>",
            );
            i++;
          }
          html.push("<ol>" + ol.join("") + "</ol>");
          continue;
        }
        var kv0 = cdSplitKv(line);
        var fileBits = [];
        while (i < lines.length) {
          var cur = lines[i];
          if (!String(cur || "").trim() || cdIsJunkHeader(cur)) break;
          if (cdIsSectionLine(String(cur).replace(/[\t ]+$/, "")) && String(cur).indexOf("\t") < 0) break;
          if (/^\d+\.\s/.test(cur) || /^\d+\t/.test(cur) || /^[-*] /.test(cur)) break;
          var kv = cdSplitKv(cur);
          if (kv && (cdLooksLikeFileChange(kv[1] || "") || /[./].+\.[A-Za-z0-9]+/.test(kv[1] || "") || kv[0] === "改动文件")) {
            fileBits.push(cdFileLi(kv[1], kv.slice(2).join(" ")));
            i++;
            continue;
          }
          if (kv && cdLooksLikeFileChange(kv[0] || "")) {
            fileBits.push(cdFileLi(kv[0], kv.slice(1).join(" ")));
            i++;
            continue;
          }
          if (cdLooksLikeFileChange(cur)) {
            var sp = String(cur).split(/\s+[—–-]\s+/);
            fileBits.push(cdFileLi(sp[0], sp.slice(1).join(" — ")));
            i++;
            continue;
          }
          break;
        }
        if (fileBits.length) {
          html.push("<ul>" + fileBits.join("") + "</ul>");
          continue;
        }
        if (kv0) {
          html.push(
            "<p><strong>" + cdInline(kv0[0]) + "</strong>：" + cdInline(kv0.slice(1).join(" ")) + "</p>",
          );
          i++;
          continue;
        }
        var para = [line];
        i++;
        while (
          i < lines.length &&
          String(lines[i] || "").trim() &&
          !cdIsJunkHeader(lines[i]) &&
          !/^#{1,3} /.test(lines[i]) &&
          !/^\s*\|/.test(lines[i]) &&
          !cdIsPipeTableStart(lines, i) &&
          !/^[-*] /.test(lines[i]) &&
          !/^\d+\.\s/.test(lines[i]) &&
          !/^\d+\t/.test(lines[i]) &&
          String(lines[i]).indexOf("一句话结论") !== 0 &&
          !cdIsSectionLine(lines[i]) &&
          !cdSplitKv(lines[i]) &&
          !cdLooksLikeFileChange(lines[i]) &&
          !cdLineLooksLikeCode(lines[i])
        ) {
          para.push(lines[i]);
          i++;
        }
        var codeLang = cdDetectCodeLangFromLines(para);
        if (codeLang) {
          html.push(cdCodeHtml(codeLang, cdCodeBodyFromPara(para, codeLang), false));
          continue;
        }
        html.push("<p>" + cdInline(para.join(" ")) + "</p>");
      }
      return html.join("");
    }
    function cdMdBlocks(text) {
      var t = String(text || "").replace(/\r\n/g, "\n");
      if (!t.trim()) return "";
      var forced = cdForceCodeFences(t);
      if (forced.indexOf("```") >= 0) {
        return cdFenceParts(forced)
          .map(function (part) {
            if (part.t === "code") return cdCodeHtml(part.lang, part.v, !!part.streaming);
            return cdMdBlocksProse(part.v);
          })
          .join("");
      }
      return cdMdBlocksProse(t);
    }
    function cdNormDialogKey(text) {
      return String(text || "")
        .replace(/[`「」→—–#*\-\s]/g, "")
        .replace(/[：:，,。．！？?；;、·•]/g, "")
        .replace(/[由的了则再]/g, "")
        .toLowerCase();
    }
    function cdCollapseDupProseSegment(text) {
      var raw = String(text || "").replace(/\r/g, "");
      if (cdDetectCodeLangFromLines(raw.split("\n")) || cdLineLooksLikeCode(raw.split("\n")[0] || raw)) {
        return raw.trim();
      }
      // 先按换行拆，再按句号拆；用归一化键去近重复（有空格/无空格同句）
      var chunks = [];
      raw.split(/\n+/).forEach(function (line) {
        var ln = String(line || "").trim();
        if (!ln) return;
        if (/^#{1,3}\s*删除清单/.test(ln) || /^[-*]\s+/.test(ln)) {
          chunks.push(ln);
          return;
        }
        var buf = "";
        for (var i = 0; i < ln.length; i++) {
          var ch = ln.charAt(i);
          buf += ch;
          if ("。！？".indexOf(ch) >= 0) {
            var s = buf.trim();
            if (s) chunks.push(s);
            buf = "";
          }
        }
        var tail = buf.trim();
        if (tail) chunks.push(tail);
      });
      var out = [];
      var keys = [];
      function prefer(a, b) {
        var sa = (String(a).match(/ /g) || []).length + (String(a).match(/`/g) || []).length * 2;
        var sb = (String(b).match(/ /g) || []).length + (String(b).match(/`/g) || []).length * 2;
        return sa >= sb ? a : b;
      }
      chunks.forEach(function (part) {
        var s = String(part || "").trim();
        if (!s) return;
        var key = cdNormDialogKey(s);
        if (!key) return;
        var hit = -1;
        for (var i = 0; i < keys.length; i++) {
          var old = keys[i];
          if (key === old || (key.length >= 12 && (key.indexOf(old) >= 0 || old.indexOf(key) >= 0))) {
            hit = i;
            break;
          }
        }
        if (hit >= 0) {
          out[hit] = prefer(out[hit], s);
          keys[hit] = cdNormDialogKey(out[hit]);
          return;
        }
        out.push(s);
        keys.push(key);
      });
      // 清单标题后改为紧凑列表；其余一句一段
      var rendered = [];
      var inPlan = false;
      out.forEach(function (ln) {
        if (/^#{0,3}\s*删除清单/.test(ln) || ln === "删除清单") {
          inPlan = true;
          rendered.push("## 删除清单");
          return;
        }
        if (inPlan && /^[-*]\s+/.test(ln)) {
          rendered.push(ln);
          return;
        }
        if (inPlan && /^(frontend|backend|apps|src)\//.test(ln.replace(/^[`*\-\s]+/, ""))) {
          rendered.push("- " + ln.replace(/^[-*\s]+/, ""));
          return;
        }
        inPlan = false;
        rendered.push(ln);
      });
      var htmlParts = [];
      var planBuf = [];
      function flushPlan() {
        if (!planBuf.length) return;
        htmlParts.push(planBuf.join("\n"));
        planBuf = [];
      }
      rendered.forEach(function (ln) {
        if (ln === "## 删除清单" || /^[-*]\s+/.test(ln)) {
          planBuf.push(ln);
          return;
        }
        flushPlan();
        htmlParts.push(ln);
      });
      flushPlan();
      return htmlParts.join("\n\n").trim();
    }
    function cdCollapseDupProse(text) {
      var raw = String(text || "");
      if (raw.indexOf("```") < 0) return cdCollapseDupProseSegment(raw);
      return cdFenceParts(raw)
        .map(function (part) {
          if (part.t === "code") {
            var lang = part.lang || "text";
            return "```" + lang + "\n" + String(part.v || "") + "\n```";
          }
          return cdCollapseDupProseSegment(part.v);
        })
        .join("\n\n");
    }
    function cdPrepProcess(text) {
      // 正文禁止代码片段：去掉围栏与裸代码，只流式展示说明文字
      var t = cdStripAllCodeText(text);
      t = cdScrubProcess(t);
      t = cdStripAllCodeText(t);
      // 粘连清单标题拉开
      t = t.replace(/##\s*删除清单/g, "\n\n## 删除清单\n");
      t = t.replace(/([。！？])\s*(#{1,3}\s*删除清单)/g, "$1\n\n$2");
      t = t.replace(/(结论[：:])\s*/g, "\n\n$1");
      t = cdCollapseDupProse(t);
      t = t.replace(/bash#\s*已删除/g, "\n已删除：\n");
      t = t.replace(
        /((?:frontend|backend|apps|src|desktop|host)\/[\w./@-]+\.[A-Za-z0-9]+)(?=(?:frontend|backend|apps|src|desktop|host)\/)/g,
        "$1\n",
      );
      return t.trim();
    }
    function cdSplitProse(text) {
      return String(text || "").replace(/([。！？])([^\n])/g, "$1\n\n$2");
    }
    function cdMdHtml(text) {
      return cdFenceParts(text)
        .map(function (part) {
          if (part.t === "code") return cdCodeHtml(part.lang, part.v, !!part.streaming);
          return cdMdBlocks(part.v);
        })
        .join("");
    }
    function cdProcessHtml(text) {
      var prose = cdPrepProcess(text);
      if (!String(prose || "").trim()) return "";
      return cdMdBlocksProseProcess(cdSplitProse(prose));
    }

    function cdThinkSummary(running, ms, elapsed) {
      if (running) return "思考中… · 已 " + cdFormatDuration(elapsed || 0);
      if (ms != null && ms !== "") return "已完成思考（" + cdFormatDuration(Number(ms) / 1000) + "）· 点击展开全文";
      return "已完成思考 · 点击展开全文";
    }
    function cdDedupeThinkText(text) {
      return cdCollapseDupProse(String(text || "").replace(/\r/g, "").trim());
    }
    function cdThinkSentences(text) {
      var t = cdDedupeThinkText(text);
      if (!t) return [];
      var parts = [];
      var buf = "";
      for (var i = 0; i < t.length; i++) {
        var ch = t[i];
        buf += ch;
        if ("。！？".indexOf(ch) >= 0) {
          var s = buf.trim();
          if (s) parts.push(s);
          buf = "";
        }
      }
      var tail = buf.trim();
      if (tail) parts.push(tail);
      var out = [];
      parts.forEach(function (sent) {
        var s = sent.trim();
        if (!s) return;
        if (out.length) {
          var prev = out[out.length - 1];
          if (s === prev) return;
          if (s.length > 18 && prev.length > 18 && (s.indexOf(prev) >= 0 || prev.indexOf(s) >= 0)) {
            if (s.length > prev.length) out[out.length - 1] = s;
            return;
          }
        }
        out.push(s);
      });
      return out.slice(-20);
    }
    function CdThinkMarquee(props) {
      var action = String(props.action || "").trim();
      var sents = cdThinkSentences(props.text);
      if (action && (!sents.length || sents[sents.length - 1] !== action)) sents.push(action);
      if (!sents.length) sents = [props.placeholder || "正在对照工作区…"];
      var n = sents.length;
      var _idx = useState(Math.max(0, n - 1));
      var idx = _idx[0];
      var setIdx = _idx[1];
      var _fade = useState(false);
      var fading = _fade[0];
      var setFade = _fade[1];
      useEffect(
        function () {
          setIdx(n - 1);
        },
        [n],
      );
      useEffect(
        function () {
          if (!props.running || n < 2) return undefined;
          var t = setInterval(function () {
            setFade(true);
            setTimeout(function () {
              setIdx(function (i) {
                var start = Math.max(0, n - 5);
                var next = i + 1;
                if (next >= n) return start;
                return next;
              });
              setFade(false);
            }, 280);
          }, 3800);
          return function () {
            clearInterval(t);
          };
        },
        [props.running, n],
      );
      var safeIdx = Math.max(0, Math.min(idx, n - 1));
      var line = sents[safeIdx] || sents[n - 1] || props.placeholder || "正在对照工作区…";
      return h(
        "div",
        { className: "wb-cd-think-ticker", "aria-live": "polite" },
        h("div", { key: safeIdx + ":" + line, className: "wb-cd-think-line is-solo" + (fading ? " is-fade" : "") }, line),
      );
    }
    function CdThinkPanel(props) {
      var running = !!props.running;
      var text = cdDedupeThinkText(props.text || "");
      var action = String(props.action || "").trim();
      if (running) {
        return h(
          "div",
          { className: "wb-cd-think is-live" },
          h("span", { className: "wb-cd-think-lab" }, "思考中"),
          h("span", { className: "wb-cd-think-rail", "aria-hidden": "true" }),
          h(CdThinkMarquee, {
            running: true,
            text: text,
            action: action,
            placeholder: "正在对照工作区…",
          }),
        );
      }
      return h(
        "details",
        { className: "wb-cd-think", open: false },
        h("summary", null, cdThinkSummary(false, props.ms, props.elapsed)),
        h("div", { className: "wb-cd-think-body" }, text || "本轮未捕获到思考正文"),
      );
    }

    function CdPlanView(planProps) {
      var steps = planProps.steps || [];
      var duration = planProps.duration || "";
      var visible = steps.filter(function (s) {
        return s.state !== "pending";
      });
      var list = visible.length
        ? visible
        : [{ id: "boot", title: "任务已排队", state: "running" }];
      var summary = planProps.summary || cdPlanSummary(list);
      return h(
        "div",
        { className: "wb-cd-plan" },
        h(
          "div",
          { className: "wb-cd-plan-head" },
          h("span", { className: "wb-cr-badge" }, "本轮进度"),
          h("span", { className: "sum" }, summary),
          duration ? h("span", { className: "dur" }, duration) : null,
        ),
        h(
          "ol",
          { className: "wb-cd-ol" },
          list.map(function (s, i) {
            var st = s.state || "pending";
            var icon =
              st === "running"
                ? h("span", { className: "wb-cd-dot-live", "aria-hidden": "true" })
                : st === "done"
                  ? "✓"
                  : st === "error"
                    ? "!"
                    : String(i + 1);
            var hint =
              st === "running"
                ? h("span", { className: "wb-cd-spin", role: "status", "aria-label": "进行中" })
                : st === "done"
                  ? "已完成"
                  : st === "error"
                    ? "失败"
                    : "等待中";
            return h(
              "li",
              { key: s.id, className: "wb-cd-li is-" + st },
              h("span", { className: "wb-cd-ico" }, icon),
              h(
                "div",
                null,
                h("span", { className: "wb-cd-title" }, s.title || s.id),
                h("span", { className: "wb-cd-state" }, hint),
              ),
            );
          }),
        ),
      );
    }

    function cdActivityPathKey(line) {
      var m = String(line || "").match(/`([^`]+)`/);
      if (m) return m[1].trim();
      var bare = String(line || "").trim().split("（")[0].trim();
      if (/^(查找文件|搜索|查看|检索|查看目录|执行)$/.test(bare)) return "";
      return bare;
    }
    function cdCompactToolLines(lines) {
      var out = [];
      var seen = {};
      (lines || []).forEach(function (ln) {
        var key = cdActivityPathKey(ln) || ln;
        if (key && seen[key]) return;
        if (key) seen[key] = true;
        out.push(ln);
      });
      return out.slice(-8);
    }

    function CdActivityFeed(props) {
      var lines = cdCompactToolLines(props.lines || []);
      var live = String(props.live || "").trim();
      if (!lines.length && !live) return null;
      var kids = lines.slice(-10).map(function (ln, i) {
        var isLast = i === lines.length - 1 && !live;
        return h(
          "li",
          { key: i + ":" + ln, className: isLast && props.running ? "is-live" : "" },
          ln,
        );
      });
      if (live && (props.running || lines.indexOf(live) < 0)) {
        kids.push(h("li", { key: "live", className: "is-live" }, live));
      }
      return h(
        "div",
        { className: "wb-cd-act" },
        h("div", { className: "wb-cd-act-h" }, "实时进展 · 同文件只保留最后一次"),
        h("ul", null, kids),
      );
    }

    var CD_FLOW_INTRO =
      "写码工具卡已打开。请先在本卡选择工程目录、填写诉求并完成确认；确认后才会启动 Cursor 写码与同步，不会自动 commit。";

    function cdStripBoilerplate(text) {
      var t = String(text || "");
      t = t.replace(
        /The development tool card has been opened for you\.[\s\S]*?in the tool card\.?\s*/gi,
        "",
      );
      t = t.replace(
        /Please complete the directory selection and requirement confirmation in the tool card\.?\s*/gi,
        "",
      );
      // 兼容「卡（…），请在卡片中…后开工」与「卡，…后再开工」
      t = t.replace(/已为您打开写码工具卡[（(，,][\s\S]*?后?再?(开工|执行)[。．]?\s*/g, "");
      t = t.replace(/已为您打开写码工具卡[\s\S]{0,200}?确认需求后开工[。．]?\s*/g, "");
      t = t.replace(/写码工具卡已打开[。．][\s\S]*?确认后再?(开工|执行)[。．]?\s*/g, "");
      // Agent 空转提示（卡已在 toolview，勿再复述）
      t = t.replace(/请在(上方)?工具卡(中)?确认[。．]?\s*/g, "");
      t = t.replace(/请在卡片中确认[。．]?\s*/g, "");
      return t.trim();
    }

    function CdFlowIntro() {
      return h("p", { className: "wb-cd-intro" }, CD_FLOW_INTRO);
    }

    function CdPipelineCards(props) {
      var steps = props.steps || [];
      return h(
        "div",
        { className: "wb-cd-pipe" },
        steps.map(function (s, i) {
          var st = s.state || "pending";
          var mark =
            st === "done"
              ? "✓"
              : st === "running"
                ? h("span", { className: "wb-cd-dot-live", "aria-hidden": "true" })
                : st === "error"
                  ? "!"
                  : st === "skipped"
                    ? "—"
                    : String(i + 1);
          var hint =
            st === "done"
              ? "已完成"
              : st === "running"
                ? h("span", { className: "wb-cd-spin", role: "status", "aria-label": "进行中" })
                : st === "error"
                  ? "失败"
                  : st === "skipped"
                    ? "已跳过"
                    : "等待中";
          return h(
            "div",
            { key: s.id, className: "wb-cd-pipecard is-" + st },
            h(
              "div",
              { className: "wb-cd-pipecard-h" },
              h("span", { className: "wb-cd-ico" }, mark),
              h("span", { className: "ttl" }, s.title || (CD_PIPELINE[i] && CD_PIPELINE[i].title) || s.id),
              h("span", { className: "hint" }, hint),
            ),
          );
        }),
      );
    }
    function CdDoneCard(props) {
      return h(
        "div",
        { className: "wb-cd-stepcard" },
        h(
          "div",
          { className: "wb-cd-stepcard-h" },
          h("span", { className: "wb-cd-ico" }, "✓"),
          h("span", null, props.title),
          h("span", { className: "hint" }, "已确认"),
        ),
        props.body ? h("pre", { className: "wb-cd-stepcard-b" }, props.body) : null,
      );
    }

    function CodeDevBeginCard(props) {
      ensureCss();
      var block = props.block;
      var toolCallId = String(props.callId || cdBlockCallId(block, "") || "").trim();
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var dshCwd = resolveDshCwd(props);
      var persistBoot = useMemo(
        function () {
          return cdPersistLoadForCard(block, props.sessionId, toolCallId);
        },
        [block, props.sessionId, toolCallId],
      );
      var persistKey = persistBoot.key;
      // 只恢复本 callId；meta 仍为 pick 时，本卡已落盘进度仍恢复（四车道会话契约）
      var bootSavedRaw =
        persistBoot.saved && cdPersistBelongsToCall(persistBoot.saved, toolCallId)
          ? cdPersistEnrichCardSaved(persistBoot.saved)
          : null;
      var bootSaved = null;
      if (bootSavedRaw) {
        if (cdPickMustStayHitl(wb, ui, bootSavedRaw, toolCallId)) {
          if (
            (bootSavedRaw.phase === "options" || bootSavedRaw.phase === "propose") &&
            cdPersistBelongsToCall(bootSavedRaw, toolCallId)
          ) {
            bootSaved = bootSavedRaw;
          }
        } else {
          bootSaved = bootSavedRaw;
        }
      }

      // 对齐原 WorkBuddy：form(原始诉求) → options → propose → confirm 开工
      var _phase = useState(function () {
        return (bootSaved && bootSaved.phase) || "form";
      }); // form | options | propose | running | done
      var phase = _phase[0];
      var setPhase = _phase[1];
      var _ws = useState(function () {
        return (bootSaved && bootSaved.workspace) || initialWorkspace(props, ui);
      });
      var workspace = _ws[0];
      var setWorkspace = _ws[1];
      var _req = useState(function () {
        return (bootSaved && bootSaved.requirement) || initialRequirement(props, ui);
      });
      var requirement = _req[0];
      var setRequirement = _req[1];
      var _goal = useState(function () {
        return (bootSaved && bootSaved.goal) || initialRequirement(props, ui);
      });
      var goal = _goal[0];
      var setGoal = _goal[1];
      var _brief = useState(function () {
        return (bootSaved && bootSaved.brief) || ui.brief || null;
      });
      var brief = _brief[0];
      var setBrief = _brief[1];
      var _optionsUi = useState(function () {
        return (bootSaved && bootSaved.optionsUi) || null;
      });
      var optionsUi = _optionsUi[0];
      var setOptionsUi = _optionsUi[1];
      var _proposeUi = useState(function () {
        return (bootSaved && bootSaved.proposeUi) || null;
      });
      var proposeUi = _proposeUi[0];
      var setProposeUi = _proposeUi[1];
      var _sel = useState(function () {
        return (bootSaved && bootSaved.selectedOpts) || {};
      });
      var selectedOpts = _sel[0];
      var setSelectedOpts = _sel[1];
      var _notes = useState(function () {
        return (bootSaved && bootSaved.notes) || "";
      });
      var notes = _notes[0];
      var setNotes = _notes[1];
      var _ack = useState(function () {
        return !!(bootSaved && bootSaved.ackWarn);
      });
      var ackWarn = _ack[0];
      var setAckWarn = _ack[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _jobId = useState(function () {
        return (bootSaved && bootSaved.jobId) || "";
      });
      var jobId = _jobId[0];
      var setJobId = _jobId[1];
      var _log = useState("");
      var log = _log[0];
      var setLog = _log[1];
      var _result = useState(function () {
        return (bootSaved && bootSaved.result) || "";
      });
      var result = _result[0];
      var setResult = _result[1];
      var _runtimeHint = useState(function () {
        return (bootSaved && bootSaved.runtimeHint) || "";
      });
      var runtimeHint = _runtimeHint[0];
      var setRuntimeHint = _runtimeHint[1];
      var _synced = useState(function () {
        return (bootSaved && bootSaved.synced) || [];
      });
      var synced = _synced[0];
      var setSynced = _synced[1];
      var _deferred = useState(function () {
        return (bootSaved && bootSaved.deferred) || [];
      });
      var deferred = _deferred[0];
      var setDeferred = _deferred[1];
      var _deleted = useState(function () {
        return (bootSaved && bootSaved.deleted) || [];
      });
      var deleted = _deleted[0];
      var setDeleted = _deleted[1];
      var _steps = useState(function () {
        var s = bootSaved;
        return (s && s.steps && s.steps.length && s.steps) || cdInitSteps();
      });
      var steps = _steps[0];
      var setSteps = _steps[1];
      var _stream = useState(function () {
        return (bootSaved && bootSaved.streamText) || "";
      });
      var streamText = _stream[0];
      var setStreamText = _stream[1];
      var _elapsed = useState(function () {
        return (bootSaved && bootSaved.elapsed) || 0;
      });
      var elapsed = _elapsed[0];
      var setElapsed = _elapsed[1];
      var _alive = useState(function () {
        return (bootSaved && bootSaved.aliveHint) || "准备启动…";
      });
      var aliveHint = _alive[0];
      var setAliveHint = _alive[1];
      var _think = useState(function () {
        return (bootSaved && bootSaved.thinkingText) || "";
      });
      var thinkingText = _think[0];
      var setThinkingText = _think[1];
      var _delivery = useState(function () {
        return (bootSaved && bootSaved.deliveryText) || "";
      });
      var deliveryText = _delivery[0];
      var setDeliveryText = _delivery[1];
      var _thinkMs = useState(function () {
        var s = bootSaved;
        return s && s.thinkingMs != null ? s.thinkingMs : null;
      });
      var thinkingMs = _thinkMs[0];
      var setThinkingMs = _thinkMs[1];
      var _action = useState("");
      var currentAction = _action[0];
      var setCurrentAction = _action[1];
      var _tools = useState([]);
      var toolLines = _tools[0];
      var setToolLines = _tools[1];

      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];
      var streamBoxRef = useRef(null);
      var composerRef = useRef(null);
      var restoreOnceRef = useRef(false);
      var resumeWatchRef = useRef("");
      var cancelRunningRef = useRef(null);
      var _cancelling = useState(false);
      var cancelling = _cancelling[0];
      var setCancelling = _cancelling[1];

      useEffect(
        function () {
          if (dshCwd && !String(workspace || "").trim()) setWorkspace(dshCwd);
        },
        [dshCwd],
      );
      useEffect(
        function () {
          var el = streamBoxRef.current;
          if (el) el.scrollTop = el.scrollHeight;
        },
        [streamText, phase],
      );
      useEffect(
        function () {
          var el = composerRef.current;
          if (!el) return;
          function codeFromWrap(wrap) {
            var codeEl = wrap ? wrap.querySelector("code") : null;
            return codeEl ? String(codeEl.textContent || "") : "";
          }
          function markCopied(btn) {
            btn.classList.add("is-copied");
            var label = btn.querySelector(".wb-cd-codebtn-label");
            if (label) label.textContent = "已复制";
            setTimeout(function () {
              btn.classList.remove("is-copied");
              if (label) label.textContent = "复制";
            }, 1600);
          }
          function copyText(text, btn) {
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(text).then(function () {
                markCopied(btn);
              }).catch(function () {
                try {
                  var ta = document.createElement("textarea");
                  ta.value = text;
                  ta.style.position = "fixed";
                  ta.style.left = "-9999px";
                  document.body.appendChild(ta);
                  ta.select();
                  document.execCommand("copy");
                  document.body.removeChild(ta);
                  markCopied(btn);
                } catch (e0) {}
              });
            }
          }
          function onCodeAction(ev) {
            var copyBtn = ev.target && ev.target.closest ? ev.target.closest("[data-cd-copy]") : null;
            var dlBtn = ev.target && ev.target.closest ? ev.target.closest("[data-cd-download]") : null;
            var btn = copyBtn || dlBtn;
            if (!btn || !el.contains(btn)) return;
            ev.preventDefault();
            ev.stopPropagation();
            var wrap = btn.closest ? btn.closest(".wb-cd-codewrap") : null;
            var text = codeFromWrap(wrap);
            if (!text) return;
            if (copyBtn) {
              copyText(text, copyBtn);
              return;
            }
            var ext = btn.getAttribute("data-cd-ext") || "txt";
            try {
              var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
              var url = URL.createObjectURL(blob);
              var a = document.createElement("a");
              a.href = url;
              a.download = "snippet." + ext;
              a.style.display = "none";
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            } catch (e1) {}
          }
          el.addEventListener("click", onCodeAction);
          return function () {
            el.removeEventListener("click", onCodeAction);
          };
        },
        [streamText, phase],
      );

      function cdSnapshotPersist(extra) {
        cdPersistSaveCard(
          block,
          props.sessionId,
          toolCallId,
          Object.assign(
            {
              phase: phase,
              jobId: jobId,
              callId: toolCallId || cdBlockCallId(block),
              sessionId: cdBlockSessionId(block, props.sessionId),
              workspace: workspace,
              requirement: requirement,
              goal: goal,
              brief: brief,
              optionsUi: optionsUi,
              proposeUi: proposeUi,
              selectedOpts: selectedOpts,
              notes: notes,
              ackWarn: ackWarn,
              streamText: streamText,
              deliveryText: deliveryText,
              steps: steps,
              elapsed: elapsed,
              aliveHint: aliveHint,
              thinkingText: thinkingText,
              thinkingMs: thinkingMs,
              synced: synced,
              deferred: deferred,
              deleted: deleted,
              result: result,
              runtimeHint: runtimeHint,
            },
            extra || {},
          ),
        );
        if (persistBoot.migrateFrom && persistBoot.migrateFrom !== persistKey) {
          try {
            localStorage.removeItem(persistBoot.migrateFrom);
          } catch (eMig) {}
          persistBoot.migrateFrom = "";
        }
      }

      function hydrateFromJob(job, pack) {
        if (!job || typeof job !== "object") return;
        if (job.workspace) setWorkspace(String(job.workspace));
        if (job.live_text) setStreamText(String(job.live_text));
        if (job.delivery_text) setDeliveryText(String(job.delivery_text));
        if (job.thinking_text) setThinkingText(cdDedupeThinkText(String(job.thinking_text)));
        if (job.thinking_duration_ms != null) setThinkingMs(job.thinking_duration_ms);
        if (job.synced_files) setSynced(job.synced_files || []);
        if (job.deferred_files) setDeferred(job.deferred_files || []);
        if (job.deleted_files) setDeleted(job.deleted_files || []);
        if (job.runtime_hint) setRuntimeHint(String(job.runtime_hint));
        setSteps(cdJobStepsFromRecord(job));
        setElapsed(cdJobElapsed(job));
        var st = String(job.status || "");
        if (st === "succeeded" || st === "failed" || st === "cancelled") {
          setPhase("done");
          setBusy(false);
          setAliveHint(cdJobAliveHint(job));
          if (pack && pack.reply) setResult(String(pack.reply));
          if (st === "failed") setErr(String(job.error || (pack && pack.detail) || "写码失败"));
        } else if (st === "queued" || st === "running") {
          setPhase("running");
          setBusy(true);
          setAliveHint(String(job.progress || "写码进行中…"));
        }
      }

      function head(hint) {
        return h(
          "div",
          { className: "wb-cr-head" },
          h("span", { className: "wb-cr-badge" }, "本机写码"),
          h("span", { className: "wb-cr-hint" }, hint),
        );
      }

      function browse() {
        setBusy(true);
        setErr("请在弹出的系统对话框中选择目录（若看不到，请看 Dock / 其它窗口后面）");
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = setTimeout(function () {
          try {
            if (ctrl) ctrl.abort();
          } catch (e0) {}
        }, 120000);
        pickLocalFolder("选择要写码的本机工程目录", ctrl ? ctrl.signal : undefined)
          .then(function (d) {
            clearTimeout(timer);
            setBusy(false);
            if (d && d.ok && d.path) {
              setWorkspace(String(d.path));
              setErr("");
            } else {
              setErr((d && (d.detail || d.message)) || "未选择目录");
            }
          })
          .catch(function (e) {
            clearTimeout(timer);
            setBusy(false);
            setErr("选目录失败：" + (e && e.name === "AbortError" ? "超时或已取消" : e && e.message ? e.message : e));
          });
      }

      function applyDiscussResult(d) {
        if (d && d.code_dev_brief) setBrief(d.code_dev_brief);
        var nextUi = (d && d.code_dev_ui) || null;
        if (!nextUi || !nextUi.kind) {
          setErr((d && (d.reply || d.detail)) || "未返回选项卡/确认卡，请补充诉求后再试");
          return;
        }
        if (nextUi.workspace) setWorkspace(String(nextUi.workspace));
        if (nextUi.original_goal) setGoal(String(nextUi.original_goal));
        else if (d.code_dev_brief && d.code_dev_brief.original_goal) {
          setGoal(String(d.code_dev_brief.original_goal));
        }
        if (nextUi.kind === "options") {
          setOptionsUi(nextUi);
          setSelectedOpts({});
          setNotes("");
          setPhase("options");
          return;
        }
        if (nextUi.kind === "propose") {
          var req0 =
            nextUi.requirement ||
            (nextUi.propose && nextUi.propose.requirement) ||
            requirement ||
            "";
          setProposeUi(nextUi);
          setRequirement(String(req0));
          setAckWarn(false);
          setPhase("propose");
          return;
        }
        setErr("未知写码卡片：" + nextUi.kind);
      }

      function runDiscuss(messageOverride, briefOverride) {
        var ws = String(workspace || "").trim();
        var msg = String(messageOverride != null ? messageOverride : requirement || "").trim();
        if (!ws) {
          setErr("请填写或浏览选择本机工程目录");
          return;
        }
        if (!msg) {
          setErr("请先填写原始写码诉求");
          return;
        }
        setBusy(true);
        setErr("");
        var briefPayload =
          briefOverride ||
          brief || {
            original_goal: goal || msg,
            workspace: ws,
            selections: [],
            notes: [],
            option_rounds: 0,
          };
        if (!briefPayload.original_goal) briefPayload.original_goal = goal || msg;
        if (!briefPayload.workspace) briefPayload.workspace = ws;
        fetch(engineBase() + "/api/code-dev/discuss", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: msg,
            workspace: ws,
            code_dev_brief: briefPayload,
          }),
        })
          .then(function (r) {
            return r.json().then(function (d) {
              return { ok: r.ok, d: d };
            });
          })
          .then(function (pack) {
            setBusy(false);
            var d = pack.d || {};
            if (!pack.ok && d.ok === false) {
              setErr(d.detail || d.reply || "需求讨论失败");
              return;
            }
            if (d.ok === false && !d.code_dev_ui) {
              setErr(d.detail || d.reply || "需求讨论失败");
              return;
            }
            applyDiscussResult(d);
          })
          .catch(function (e) {
            setBusy(false);
            setErr("需求讨论失败：" + (e && e.message ? e.message : e));
          });
      }

      function submitOptions() {
        var nextUi = optionsUi || {};
        var opts = nextUi.options || {};
        var groups = Array.isArray(opts.groups) ? opts.groups : [];
        for (var i = 0; i < groups.length; i++) {
          var g = groups[i];
          if (g.required === false) continue;
          if (!(selectedOpts[g.id] || []).length) {
            setErr("请先选择：「" + (g.label || g.id) + "」");
            return;
          }
        }
        var noteText = String(notes || "").trim();
        if (opts.notes_required && !noteText) {
          setErr("请填写备注：业务模块、页面名称、接口路径等（必填）");
          return;
        }
        var lines = ["【写码需求选项已确认】"];
        var ws = String(workspace || "").trim();
        if (ws) lines.push("工程路径：" + ws);
        groups.forEach(function (g) {
          var ids = selectedOpts[g.id] || [];
          var labels = (g.options || [])
            .filter(function (o) {
              return ids.indexOf(o.id) >= 0;
            })
            .map(function (o) {
              return o.label || o.id;
            });
          if (labels.length) lines.push((g.label || g.id) + "：" + labels.join("、"));
        });
        if (noteText) lines.push("备注：" + noteText);
        runDiscuss(lines.join("\n"), brief || nextUi.brief || null);
      }

      function watchJob(jid, opts) {
        opts = opts || {};
        var resume = !!opts.resume;
        setPhase("running");
        setBusy(true);
        if (!resume) {
          setSteps(
            cdInitSteps().map(function (s) {
              return s.id === "brief" ? Object.assign({}, s, { state: "done" }) : s;
            }),
          );
          setStreamText("");
          setThinkingText("正在对照工作区…");
          setThinkingMs(null);
          setCurrentAction("");
          setToolLines([]);
          setElapsed(0);
          setAliveHint("任务已启动，正在连接进度流…");
          setLog("");
          setErr("");
        }
        cdSnapshotPersist({ phase: "running", jobId: jid });
        var logAcc = log || "";
        var streamAcc = resume ? cdStripExplorationFromProcess(cdStripBoilerplate(String(streamText || ""))) : "";
        var deliveryAcc = resume ? String(deliveryText || "") : "";
        var thinkAcc =
          resume && thinkingText
            ? cdDedupeThinkText(String(thinkingText))
            : "正在对照工作区…";
        var toolAcc = toolLines.slice();
        var stepState =
          resume && steps && steps.length
            ? steps.slice()
            : cdInitSteps().map(function (s) {
                return s.id === "brief" ? Object.assign({}, s, { state: "done" }) : s;
              });
        var finished = false;
        var startedAt = Date.now() - (resume ? Math.max(0, Number(elapsed) || 0) * 1000 : 0);
        var lastFlush = 0;
        /** 引擎 job.live_text 已是过程通道，禁止再走终稿路由（会把过程正文剥空）。 */
        function applyJobProcessText(raw, keepPrev) {
          var prev = String(keepPrev || streamAcc || "");
          var t = cdStripExplorationFromProcess(
            cdStripBoilerplate(String(raw || "")),
          );
          if (t) {
            streamAcc = t;
          } else if (prev) {
            streamAcc = prev;
          } else {
            streamAcc = String(raw || "");
          }
          flushStream(true);
        }
        function applyStreamPayload(raw) {
          var t = String(raw || "");
          var prev = String(streamAcc || "");
          // 过程正文：有「说明方案」才拆终稿；否则整段当正文，避免流式过程被路由吃掉
          if (/说明方案|一句话结论/.test(t)) {
            var routed = cdRouteStreamChannels(t);
            streamAcc = routed.process || cdStripAllCodeText(t) || prev;
            if (routed.delivery) {
              deliveryAcc = routed.delivery;
              setDeliveryText(deliveryAcc);
            }
          } else {
            streamAcc = cdStripAllCodeText(t) || t || prev;
          }
          flushStream(true);
        }
        function applyJobSnapshot(job) {
          if (!job || typeof job !== "object") return;
          if (job.live_text != null) {
            applyJobProcessText(job.live_text, streamAcc);
          }
          if (job.delivery_text != null && String(job.delivery_text || "").trim()) {
            deliveryAcc = String(job.delivery_text || "");
            setDeliveryText(deliveryAcc);
          }
          if (job.thinking_text) {
            thinkAcc = cdDedupeThinkText(String(job.thinking_text || ""));
            setThinkingText(thinkAcc);
          }
          if (job.thinking_duration_ms != null) setThinkingMs(job.thinking_duration_ms);
        }
        fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jid))
          .then(function (r) {
            return r.json();
          })
          .then(function (jd) {
            if (jd && jd.ok && jd.job) applyJobSnapshot(jd.job);
          })
          .catch(function () {});
        var tickTimer = setInterval(function () {
          if (finished) {
            clearInterval(tickTimer);
            return;
          }
          var sec = Math.floor((Date.now() - startedAt) / 1000);
          setElapsed(sec);
          setAliveHint("Cursor 仍在工作 · 已运行 " + cdFormatDuration(sec) + "（界面未卡住，请稍候）");
        }, 1000);
        function flushStream(force) {
          var now = Date.now();
          if (!force && now - lastFlush < 20) return;
          lastFlush = now;
          setStreamText(streamAcc);
        }
        function pushLog(line) {
          if (!line) return;
          logAcc += line + "\n";
          setLog(logAcc);
        }
        function finish(ev) {
          if (finished) return;
          finished = true;
          clearInterval(tickTimer);
          cancelRunningRef.current = null;
          setCancelling(false);
          flushStream(true);
          setBusy(false);
          setPhase("done");
          var termSt = String(
            (ev && ev.status) || (ev && ev.job && ev.job.status) || (ev && ev.ok === false ? "failed" : "succeeded"),
          );
          var isCancelled = termSt === "cancelled";
          var asError = termSt === "failed" || isCancelled || !!(ev && ev.ok === false && termSt !== "succeeded");
          var sealed = cdFinalizeSteps(stepState, ev, asError);
          setSteps(sealed);
          var dur = Math.floor((Date.now() - startedAt) / 1000);
          setElapsed(dur);
          setAliveHint(
            isCancelled
              ? "任务已取消 · 共 " + cdFormatDuration(dur)
              : asError
                ? "任务结束（失败）· 共 " + cdFormatDuration(dur)
                : "任务完成 · 共 " + cdFormatDuration(dur),
          );
          if (ev && ev.synced_files) setSynced(ev.synced_files || []);
          if (ev && ev.deferred_files) setDeferred(ev.deferred_files || []);
          if (ev && ev.deleted_files) setDeleted(ev.deleted_files || []);
          if (ev && ev.job) {
            if (ev.job.synced_files) setSynced(ev.job.synced_files || []);
            if (ev.job.deferred_files) setDeferred(ev.job.deferred_files || []);
            if (ev.job.deleted_files) setDeleted(ev.job.deleted_files || []);
            if (ev.job.runtime_hint) setRuntimeHint(String(ev.job.runtime_hint));
            if (ev.job.thinking_text) setThinkingText(cdDedupeThinkText(String(ev.job.thinking_text)));
            if (ev.job.thinking_duration_ms != null) setThinkingMs(ev.job.thinking_duration_ms);
            if (ev.job.live_text) {
              applyJobProcessText(ev.job.live_text, streamAcc);
            }
            if (ev.job.delivery_text) {
              deliveryAcc = String(ev.job.delivery_text);
              setDeliveryText(deliveryAcc);
            }
            if (ev.job.workspace) setWorkspace(String(ev.job.workspace));
          }
          var ok = termSt === "succeeded";
          var resultText =
            (ev && (ev.reply || ev.error || ev.detail)) ||
            (isCancelled ? "任务已取消" : ok ? "写码任务已结束" : "写码失败");
          setResult(resultText);
          if (isCancelled) setErr((ev && (ev.error || ev.detail)) || "任务已取消");
          else if (!ok) setErr((ev && (ev.error || ev.detail || ev.reply)) || "写码失败");
          else if (ev && (ev.deferred_files || []).length) {
            setErr(
              "有 " +
                ev.deferred_files.length +
                " 个文件因写范围未同步（含路由/菜单时会导致刷新看不到新界面）：" +
                ev.deferred_files.slice(0, 6).join("、"),
            );
          }
          cdPersistSaveCard(block, props.sessionId, toolCallId, {
            phase: "done",
            jobId: jid,
            callId: toolCallId || cdBlockCallId(block),
            sessionId: cdBlockSessionId(block, props.sessionId),
            workspace: (ev && ev.job && ev.job.workspace) || workspace,
            requirement: requirement,
            goal: goal,
            brief: brief,
            streamText: streamAcc,
            deliveryText: deliveryAcc,
            steps: sealed,
            elapsed: dur,
            aliveHint: asError
              ? "任务结束（失败）· 共 " + cdFormatDuration(dur)
              : "任务完成 · 共 " + cdFormatDuration(dur),
            thinkingText: thinkAcc,
            thinkingMs: ev && ev.job ? ev.job.thinking_duration_ms : thinkingMs,
            synced: (ev && ev.synced_files) || (ev && ev.job && ev.job.synced_files) || synced,
            deferred: (ev && ev.deferred_files) || (ev && ev.job && ev.job.deferred_files) || deferred,
            deleted: (ev && ev.deleted_files) || (ev && ev.job && ev.job.deleted_files) || deleted,
            result: resultText,
            runtimeHint:
              (ev && ev.job && ev.job.runtime_hint) ||
              runtimeHint ||
              "",
          });
        }
        cancelRunningRef.current = function () {
          if (finished || cancelling) return;
          setCancelling(true);
          setAliveHint("正在取消任务…");
          fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jid) + "/cancel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
          })
            .then(function (r) {
              return r.json();
            })
            .then(function (d) {
              if (!d || !d.ok) {
                throw new Error((d && (d.detail || d.reply)) || "取消失败");
              }
              var job = d.job || {};
              finish({
                ok: false,
                status: "cancelled",
                error: job.error || "用户取消",
                reply: d.reply || "任务已取消",
                job: job,
              });
            })
            .catch(function (e) {
              setCancelling(false);
              setErr((e && e.message) || "取消失败");
            });
        };
        fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jid) + "/stream", {
          headers: { Accept: "text/event-stream" },
        })
          .then(function (r) {
            if (!r.ok || !r.body || !r.body.getReader) {
              throw new Error("无法订阅进度流");
            }
            setAliveHint("已连接进度流 · Cursor 写码过程会实时刷新");
            var reader = r.body.getReader();
            var decoder = new TextDecoder();
            var pending = "";
            function onEvent(ev) {
              if (!ev || typeof ev !== "object") return;
              if (ev.type === "step") {
                stepState = cdApplyStep(stepState, ev);
                setSteps(stepState.slice());
                var line = ev.title || ev.detail || ev.id || "";
                if (line) pushLog(line);
                if (ev.state === "running" && line) {
                  setAliveHint(line + " · 已运行 " + cdFormatDuration(Math.floor((Date.now() - startedAt) / 1000)));
                }
              } else if (ev.type === "status") {
                var st = ev.text || ev.detail || "";
                if (st) {
                  pushLog(st);
                  setAliveHint(st + " · 已运行 " + cdFormatDuration(Math.floor((Date.now() - startedAt) / 1000)));
                }
              } else if (ev.type === "token") {
                // SSE 增量：直接拼到过程正文，避免再被路由拆丢
                streamAcc = String(streamAcc || "") + String(ev.text || "");
                if (streamAcc.length > 100000) streamAcc = streamAcc.slice(-100000);
                flushStream(true);
              } else if (ev.type === "token_delivery") {
                deliveryAcc = String(deliveryAcc || "") + String(ev.text || "");
                if (deliveryAcc.length > 100000) deliveryAcc = deliveryAcc.slice(-100000);
                setDeliveryText(deliveryAcc);
              } else if (ev.type === "replace_text") {
                applyStreamPayload(String(ev.text || ""));
              } else if (ev.type === "replace_delivery") {
                deliveryAcc = String(ev.text || "");
                setDeliveryText(deliveryAcc);
                var routedDel = cdRouteStreamChannels(streamAcc + "\n\n" + deliveryAcc);
                if (routedDel.process !== streamAcc) {
                  streamAcc = routedDel.process;
                  flushStream(true);
                }
              } else if (ev.type === "thinking") {
                if (ev.text) thinkAcc = cdDedupeThinkText(String(ev.text || ""));
                else if (ev.delta) thinkAcc = cdDedupeThinkText(thinkAcc + String(ev.delta || ""));
                if (thinkAcc.length > 12000) thinkAcc = thinkAcc.slice(-12000);
                if (thinkAcc) setThinkingText(thinkAcc);
              } else if (ev.type === "tool_call") {
                var toolLine = String(ev.text || ev.detail || "").trim();
                if (toolLine) {
                  setCurrentAction(toolLine);
                  var pkey = cdActivityPathKey(toolLine);
                  toolAcc = toolAcc.filter(function (x) {
                    return !pkey || cdActivityPathKey(x) !== pkey;
                  });
                  toolAcc = cdCompactToolLines(toolAcc.concat([toolLine])).slice(-8);
                  setToolLines(toolAcc.slice());
                }
              } else if (ev.type === "done") {
                finish(ev);
              } else if (ev.type === "error") {
                finish({ ok: false, error: ev.message || ev.detail, reply: ev.message || ev.detail });
              }
            }
            function pump() {
              return reader.read().then(function (res) {
                if (res.done) {
                  if (!finished) {
                    fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jid))
                      .then(function (r2) {
                        return r2.json();
                      })
                      .then(function (jd) {
                        var job = (jd && jd.job) || jd || {};
                        var st = job.status || "";
                        if (job.live_text) {
                          applyJobProcessText(job.live_text, streamAcc);
                        }
                        if (job.delivery_text) {
                          deliveryAcc = String(job.delivery_text);
                          setDeliveryText(deliveryAcc);
                        }
                        if (job.thinking_text) {
                          thinkAcc = cdDedupeThinkText(String(job.thinking_text));
                          setThinkingText(thinkAcc);
                        }
                        if (job.thinking_duration_ms != null) setThinkingMs(job.thinking_duration_ms);
                        finish({
                          ok: st === "succeeded",
                          status: st,
                          reply: (jd && jd.reply) || "",
                          job: job,
                          synced_files: job.synced_files || [],
                          deferred_files: job.deferred_files || [],
                          deleted_files: job.deleted_files || [],
                          error: job.error || "",
                        });
                      })
                      .catch(function () {
                        finish({ ok: false, error: "流式结束但未收到完成事件" });
                      });
                  }
                  return;
                }
                pending += decoder.decode(res.value, { stream: true });
                var chunks = pending.split("\n\n");
                pending = chunks.pop() || "";
                chunks.forEach(function (blk) {
                  blk.split("\n").forEach(function (line) {
                    if (line.indexOf("data:") !== 0) return;
                    var raw = line.slice(5).trim();
                    if (!raw) return;
                    try {
                      onEvent(JSON.parse(raw));
                    } catch (e1) {}
                  });
                });
                return pump();
              });
            }
            return pump();
          })
          .catch(function (e) {
            finished = true;
            clearInterval(tickTimer);
            setPhase("done");
            setBusy(false);
            setSteps(cdSealSteps(stepState, true));
            setErr("订阅进度失败：" + (e && e.message ? e.message : e));
          });
      }

      useEffect(
        function () {
          if (restoreOnceRef.current) return;
          restoreOnceRef.current = true;
          var pack = cdPersistLoadForCard(block, props.sessionId, toolCallId);
          var savedRaw =
            pack.saved && cdPersistBelongsToCall(pack.saved, toolCallId)
              ? cdPersistEnrichCardSaved(pack.saved)
              : null;
          var forceHitl = cdPickMustStayHitl(wb, ui, savedRaw, toolCallId);
          var saved = null;
          if (savedRaw && !forceHitl) saved = savedRaw;
          else if (
            savedRaw &&
            forceHitl &&
            (savedRaw.phase === "options" || savedRaw.phase === "propose")
          ) {
            saved = savedRaw;
          }

          // 仅「真正的新 pick」停 HITL；本 callId 已有进度时继续 hydrate（契约）
          if (forceHitl || !toolCallId) {
            var sidClr = cdBlockSessionId(block, props.sessionId);
            ["wb-cd-card:anon"]
              .concat(
                sidClr ? ["wb-cd-card:" + sidClr, "wb-cd-card:session:" + sidClr + ":lone"] : [],
              )
              .forEach(function (sharedKey) {
                try {
                  localStorage.removeItem(sharedKey);
                } catch (eRm) {}
              });
            if (phase === "done" || phase === "running") {
              setPhase(
                saved && (saved.phase === "options" || saved.phase === "propose")
                  ? saved.phase
                  : "form",
              );
              setJobId("");
              setResult("");
              setDeliveryText("");
              setStreamText("");
              setSteps(cdInitSteps());
              setAliveHint("准备启动…");
            }
            if (saved && (saved.phase === "options" || saved.phase === "propose")) {
              cdPersistSaveCard(block, props.sessionId, toolCallId, saved);
            }
            return;
          }
          // pick meta 仍可能出现在已开工卡上：只清共享键污染，不打断恢复
          if ((ui && ui.kind === "pick") || (wb && wb.t === "cd-pick")) {
            var sidPick = cdBlockSessionId(block, props.sessionId);
            ["wb-cd-card:anon"]
              .concat(
                sidPick ? ["wb-cd-card:" + sidPick, "wb-cd-card:session:" + sidPick + ":lone"] : [],
              )
              .forEach(function (sharedKey) {
                try {
                  localStorage.removeItem(sharedKey);
                } catch (eRm2) {}
              });
          }

          var jid =
            (saved && saved.jobId) ||
            (wb && wb.t === "cd-job" && wb.job_id) ||
            "";

          function hydrateJobId(foundId) {
            if (!foundId) return Promise.resolve();
            // 未确认的 pick 卡禁止 hydrate
            if ((ui && ui.kind === "pick") || (wb && wb.t === "cd-pick")) {
              if (!saved || !saved.jobId || String(saved.jobId) !== String(foundId)) {
                return Promise.resolve();
              }
              if (!cdPersistBelongsToCall(saved, toolCallId)) return Promise.resolve();
            }
            return fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(foundId))
              .then(function (r) {
                return r.json();
              })
              .then(function (jd) {
                if (!jd || !jd.ok) return;
                var job = jd.job || {};
                var jobCall = String(job.ui_call_id || "").trim();
                var savedBond =
                  saved && String(saved.jobId || "") === String(foundId);
                if (toolCallId && jobCall && jobCall !== toolCallId) return;
                // 无 ui_call_id 时：仅允许已持久化绑定的 job 恢复（防误挂历史 job）
                if (toolCallId && !jobCall && !savedBond) return;
                setJobId(foundId);
                hydrateFromJob(job, jd);
                cdPersistSaveCard(block, props.sessionId, toolCallId, {
                  phase:
                    String(job.status || "") === "queued" || String(job.status || "") === "running"
                      ? "running"
                      : "done",
                  jobId: foundId,
                  callId: toolCallId,
                  sessionId: props.sessionId || "",
                  workspace: job.workspace || workspace,
                  requirement: requirement,
                  goal: goal,
                  brief: brief,
                  deliveryText: job.delivery_text || "",
                  streamText: job.live_text || "",
                  thinkingText: job.thinking_text || "",
                  thinkingMs: job.thinking_duration_ms,
                  steps: cdJobStepsFromRecord(job),
                  synced: job.synced_files || [],
                  deferred: job.deferred_files || [],
                  deleted: job.deleted_files || [],
                  result: (jd && jd.reply) || "",
                  runtimeHint: job.runtime_hint || "",
                  aliveHint: cdJobAliveHint(job),
                });
                var st = String(job.status || "");
                if (st === "queued" || st === "running") {
                  resumeWatchRef.current = foundId;
                }
              })
              .catch(function () {});
          }

          if (jid) {
            hydrateJobId(jid);
            return;
          }

          // 完成态但 localStorage 已剥正文：用 job 快照先填一版，再等引擎对齐
          if (
            saved &&
            saved.jobId &&
            (saved.phase === "done" || saved.phase === "running") &&
            !saved.streamText &&
            !saved.deliveryText
          ) {
            var snapOnly = cdPersistLoadJobSnapshot(saved.jobId);
            if (snapOnly) {
              hydrateFromJob(
                {
                  workspace: snapOnly.workspace,
                  live_text: snapOnly.streamText,
                  delivery_text: snapOnly.deliveryText,
                  thinking_text: snapOnly.thinkingText,
                  thinking_duration_ms: snapOnly.thinkingMs,
                  synced_files: snapOnly.synced,
                  deferred_files: snapOnly.deferred,
                  deleted_files: snapOnly.deleted,
                  runtime_hint: snapOnly.runtimeHint,
                  status:
                    snapOnly.phase === "running" ? "running" : "succeeded",
                },
                { reply: snapOnly.result },
              );
            }
            hydrateJobId(String(saved.jobId));
            return;
          }

          if (toolCallId) {
            fetch(
              engineBase() +
                "/api/code-dev/jobs?limit=5&ui_call_id=" +
                encodeURIComponent(toolCallId),
            )
              .then(function (r) {
                return r.json();
              })
              .then(function (d) {
                var rows = (d && d.jobs) || [];
                if (!rows.length) {
                  if (saved && (saved.phase === "options" || saved.phase === "propose")) {
                    cdPersistSaveCard(block, props.sessionId, toolCallId, saved);
                  }
                  return;
                }
                // 仅当本卡已有同 job 持久化才 hydrate（防止仅凭 callId 误挂历史）
                if (!saved || !saved.jobId) return;
                var hit = rows.filter(function (row) {
                  return String((row && row.id) || "") === String(saved.jobId);
                })[0];
                if (!hit) return;
                return hydrateJobId(String(hit.id || ""));
              })
              .catch(function () {});
            return;
          }

          if (saved && (saved.phase === "options" || saved.phase === "propose")) {
            cdPersistSaveCard(block, props.sessionId, toolCallId, saved);
          }
        },
        [persistKey, toolCallId],
      );

      useEffect(
        function () {
          if (!resumeWatchRef.current) return;
          var jid = resumeWatchRef.current;
          resumeWatchRef.current = "";
          watchJob(jid, { resume: true });
        },
      );

      useEffect(
        function () {
          if (
            phase === "running" ||
            phase === "done" ||
            phase === "options" ||
            phase === "propose" ||
            (phase === "form" && (requirement || workspace || optionsUi || proposeUi))
          ) {
            cdSnapshotPersist();
          }
        },
        [
          persistKey,
          phase,
          jobId,
          workspace,
          requirement,
          goal,
          streamText,
          steps,
          elapsed,
          aliveHint,
          thinkingText,
          thinkingMs,
          synced,
          deferred,
          deleted,
          result,
          optionsUi,
          proposeUi,
          selectedOpts,
          notes,
          ackWarn,
          brief,
        ],
      );

      function confirmStart() {
        var ws = String(workspace || "").trim();
        var req = String(requirement || "").trim();
        var pui = proposeUi || {};
        var val = pui.validation || {};
        if (!ws) {
          setErr("请填写或浏览选择本机工程目录");
          return;
        }
        if (!req) {
          setErr("请填写需求摘要");
          return;
        }
        if (val.errors && val.errors.length) {
          setErr(val.errors.join("；"));
          return;
        }
        if (val.warnings && val.warnings.length && !ackWarn) {
          setErr("请先勾选确认：摘要与原始诉求一致");
          return;
        }
        setBusy(true);
        setErr("");
        issueHitl("code-dev.confirm", { workspace: ws, requirement: req })
          .then(function (nonce) {
            return fetch(engineBase() + "/api/code-dev/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                workspace: ws,
                requirement: req,
                code_dev_brief:
                  brief ||
                  pui.brief || {
                    original_goal: goal || req,
                    workspace: ws,
                    selections: [],
                    notes: [],
                    option_rounds: 0,
                  },
                write_scope:
                  pui.write_scope && pui.write_scope.length ? pui.write_scope : undefined,
                source_gate_job_id: pui.source_gate_job_id || undefined,
                nonce: nonce,
                ui_call_id: toolCallId || undefined,
                ui_session_id: props.sessionId || undefined,
              }),
            });
          })
          .then(function (r) {
            return r.json().then(function (d) {
              return { status: r.status, d: d };
            });
          })
          .then(function (pack) {
            var d = pack.d || {};
            if (!d.ok) {
              setBusy(false);
              setErr(d.detail || d.reply || "启动失败");
              if (d.validation) {
                setProposeUi(
                  Object.assign({}, pui, {
                    validation: d.validation,
                    requirement: req,
                    workspace: ws,
                  }),
                );
              }
              return;
            }
            var jid = String(d.job_id || "");
            setJobId(jid);
            setPhase("running");
            setLog((d.reply || "已启动") + "\n");
            setResult("");
            if (jid) {
              cdPersistSaveCard(block, props.sessionId, toolCallId, {
                phase: "running",
                jobId: jid,
                callId: toolCallId || "",
                sessionId: props.sessionId || "",
                workspace: ws,
                requirement: req,
                goal: goal || req,
                brief: brief,
              });
              watchJob(jid);
            } else {
              setPhase("done");
              setBusy(false);
              setResult(d.reply || "已启动（无 job_id）");
            }
          })
          .catch(function (e) {
            setBusy(false);
            setErr("请求失败：" + (e && e.message ? e.message : e));
          });
      }

      function optionSummaryText() {
        if (!optionsUi) return "";
        var groups = ((optionsUi.options || {}).groups) || [];
        var lines = [];
        groups.forEach(function (g) {
          var ids = selectedOpts[g.id] || [];
          var labels = (g.options || [])
            .filter(function (o) {
              return ids.indexOf(o.id) >= 0;
            })
            .map(function (o) {
              return o.label || o.id;
            });
          if (labels.length) lines.push((g.label || g.id) + "：" + labels.join("、"));
        });
        if (notes) lines.push("备注：" + notes);
        return lines.join("\n");
      }
      function confirmTrailCards() {
        var cards = [];
        if (phase === "form") return cards;
        cards.push(
          h(CdDoneCard, {
            key: "t-form",
            title: "1 · 选目录与诉求",
            body:
              String(workspace || "") +
              (requirement ? "\n" + String(requirement).slice(0, 280) : ""),
          }),
        );
        if (optionsUi && phase !== "options") {
          cards.push(
            h(CdDoneCard, {
              key: "t-opt",
              title: "2 · 需求选项",
              body: optionSummaryText() || "已确认选项",
            }),
          );
        }
        var nConfirm = optionsUi ? "3" : "2";
        var nGo = optionsUi ? "4" : "3";
        if ((phase === "running" || phase === "done") && proposeUi) {
          cards.push(
            h(CdDoneCard, {
              key: "t-propose",
              title: nConfirm + " · 核对写码摘要",
              body: String(requirement || goal || "").slice(0, 280) || "已核对摘要",
            }),
          );
        }
        if (phase === "running" || phase === "done") {
          cards.push(
            h(CdDoneCard, {
              key: "t-go",
              title: nGo + " · 确认开工",
              body: "已启动 Cursor 写码" + (jobId ? " · " + jobId : ""),
            }),
          );
        }
        return cards;
      }
      function pipelineForHitl() {
        // HITL 未开工：四步全是「等待中」，不要把第 1 步伪装成进行中（刷新后易被当成任务又跑回去了）
        return CD_PIPELINE.map(function (p) {
          return {
            id: p.id,
            title: p.title,
            state: "pending",
          };
        });
      }
      function wrapStack(active) {
        return h("div", { className: "wb-cd-stack" }, [
          h(CdFlowIntro, { key: "intro" }),
          h(CdPipelineCards, { key: "pipe", steps: pipelineForHitl() }),
          active,
        ]);
      }

      if (phase === "running" || phase === "done") {
        // 终稿已在独立通道时，过程正文不再二次路由（避免探索文过滤清空流式步骤）
        var processText = String(streamText || "");
        var showDelivery = String(deliveryText || "").trim();
        if (!showDelivery && /说明方案|一句话结论/.test(processText)) {
          var routedView = cdRouteStreamChannels(processText);
          processText = routedView.process || processText;
          showDelivery = String(routedView.delivery || "").trim();
        }
        // 仅当过程正文几乎整段是思考复读且很短时才隐藏，避免误杀流式正文
        if (
          thinkingText &&
          processText &&
          processText.replace(/\s+/g, "").length < 64 &&
          cdProcessOverlapsThink(processText, thinkingText)
        ) {
          processText = "";
        }
        if (!showDelivery) {
          var splitFb = cdSplitDelivery(cdStripBoilerplate(streamText));
          if (splitFb.delivery) showDelivery = splitFb.delivery;
        }
        // 终稿出现时仍保留过程正文（用户要看流式过程，不只看终稿）
        if (phase === "running" && !processText && toolLines.length) {
          processText = toolLines.slice(-8).join("\n");
        }
        var wsShort = String(workspace || "").replace(/\/+$/, "");
        var slash = wsShort.lastIndexOf("/");
        if (slash > 0) wsShort = wsShort.slice(slash + 1);
        var pipeSteps = steps && steps.length ? steps : cdInitSteps();
        var thinkEl =
          phase === "running" || thinkingText || thinkingMs != null
            ? h(CdThinkPanel, {
                running: phase === "running",
                text: thinkingText,
                action: currentAction,
                ms: thinkingMs,
                elapsed: elapsed,
              })
            : null;
        var bodyKids = [];
        if (thinkEl) bodyKids.push(thinkEl);
        if (phase === "running" && (toolLines.length || currentAction)) {
          bodyKids.push(
            h(CdActivityFeed, {
              lines: toolLines,
              live: currentAction,
              running: phase === "running",
            }),
          );
        }
        var showProcess = processText;
        if (showProcess) {
          bodyKids.push(
            h("div", {
              className: "wb-cd-md",
              ref: streamBoxRef,
              dangerouslySetInnerHTML: { __html: cdProcessHtml(showProcess) },
            }),
          );
        } else if (phase === "running" && !showProcess && !showDelivery) {
          bodyKids.push(
            h(
              "p",
              { className: "wb-cr-dsh" },
              "正在定位与改码；正文将在内容取齐后流式刷新…",
            ),
          );
        }
        if (showDelivery) {
          bodyKids.push(
            h("div", {
              className: "wb-cd-doc wb-cd-md",
              dangerouslySetInnerHTML: { __html: cdBuildDocHtml(showDelivery) },
            }),
          );
        }
        if (synced && synced.length) {
          bodyKids.push(
            h(
              "div",
              { className: "wb-cr-files", style: { marginTop: 10 } },
              h("div", { className: "wb-cr-label", style: { marginBottom: 6 } }, "已同步文件"),
              synced.slice(0, 40).map(function (f, i) {
                return h("div", { key: i, className: "wb-cr-file" }, h("span", null, String(f)));
              }),
            ),
          );
        }
        if (deleted && deleted.length) {
          bodyKids.push(
            h(
              "div",
              { className: "wb-cr-files", style: { marginTop: 10 } },
              h("div", { className: "wb-cr-label", style: { marginBottom: 6 } }, "已从本机删除"),
              deleted.slice(0, 40).map(function (f, i) {
                return h("div", { key: "d" + i, className: "wb-cr-file" }, h("span", null, String(f)));
              }),
            ),
          );
        }
        if (deferred && deferred.length) {
          var deferWiring = deferred.some(function (f) {
            var s = String(f || "").replace(/\\/g, "/");
            return (
              s.indexOf("frontend/src/config/") >= 0 ||
              s.indexOf("frontend/src/router/") >= 0 ||
              s.indexOf("frontend/src/layouts/") >= 0 ||
              /reportFeatures|reportIcons|menu/i.test(s)
            );
          });
          bodyKids.push(
            h(
              "div",
              { className: "wb-cr-warn", style: { marginTop: 8 } },
              (deferWiring
                ? "⚠ 菜单/路由配置未同步到本机，浏览器可能看不到新菜单（勿信「已上菜单」交付文案）。请重新开工或扩大写范围。\n"
                : "") +
                "未同步 " +
                deferred.length +
                " 个文件：\n" +
                deferred.slice(0, 12).join("\n"),
            ),
          );
        }
        return h(
          "div",
          { className: "wb-cd-composer", ref: composerRef },
          h(
            "div",
            { className: "wb-cd-composer-bar" },
            phase === "running" ? h("span", { className: "wb-cd-pulse" }) : null,
            h(
              "span",
              null,
              phase === "running"
                ? "写作中 · " + cdFormatDuration(elapsed)
                : aliveHint || "已完成 · " + cdFormatDuration(elapsed),
            ),
            h("span", { className: "ws", title: workspace }, wsShort || workspace || ""),
            h("span", { className: "ws", title: "写码 UI 版本 " + CD_UI_REV, style: { fontSize: 10, opacity: 0.55 } }, CD_UI_REV),
            phase === "running"
              ? h(
                  "button",
                  {
                    type: "button",
                    className: "wb-cr-btn",
                    disabled: cancelling,
                    style: { marginLeft: 8, fontSize: 12, padding: "2px 10px" },
                    onClick: function () {
                      if (cancelRunningRef.current) cancelRunningRef.current();
                    },
                  },
                  cancelling ? "取消中…" : "取消任务",
                )
              : null,
          ),
          h(CdPipelineCards, { steps: pipeSteps }),
          bodyKids.length ? h("div", { className: "wb-cd-stream" }, bodyKids) : null,
          runtimeHint
            ? h(
                "div",
                { className: "wb-cr-warn", style: { marginTop: 10 } },
                runtimeHint,
              )
            : null,
          err ? h("p", { className: "wb-cr-err" }, err) : null,
        );
      }

      if (
        (phase === "options" || phase === "propose") &&
        (!wb || (wb.t !== "cd-pick" && !(ui && ui.kind === "pick"))) &&
        !(ui && (ui.kind === "pick" || ui.kind === "propose" || ui.kind === "options"))
      ) {
        var outFallback =
          block && "kind" in block
            ? (block.content || [])
                .map(function (c) {
                  return c && c.type === "text" ? c.text : "";
                })
                .filter(Boolean)
                .join("\n")
            : "写码进行中…";
        return h(
          "div",
          { className: "wb-cr" },
          h(
            "div",
            { className: "wb-cr-head" },
            h("span", { className: "wb-cr-badge" }, "本机写码"),
            h("span", { className: "wb-cr-hint" }, "结果"),
          ),
          h(
            "div",
            { className: "wb-cr-body" },
            h("pre", { className: "wb-cr-progress", style: { margin: 0 } }, outFallback || "（无详情）"),
          ),
        );
      }

      if (phase === "options" && optionsUi) {
        var opts = optionsUi.options || {};
        var groups = Array.isArray(opts.groups) ? opts.groups : [];
        var og = optionsUi.original_goal || (optionsUi.brief && optionsUi.brief.original_goal) || goal;
        return wrapStack(h(
          "div",
          { className: "wb-cr" },
          head("需求选项 · 勾选后继续（不会立刻写码）"),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, opts.title || "请确认以下关键项"),
            opts.summary ? h("p", { className: "wb-cr-dsh" }, opts.summary) : null,
            og ? h("p", { className: "wb-cr-dsh" }, "原始诉求：", h("code", null, og)) : null,
            groups.map(function (g) {
              return h(
                "div",
                { key: g.id, style: { marginBottom: 10 } },
                h(
                  "div",
                  { className: "wb-cr-label" },
                  (g.label || g.id) +
                    (g.required === false ? "" : " · 必选") +
                    (g.multi ? " · 可多选" : " · 单选"),
                ),
                h(
                  "div",
                  { className: "wb-cr-chips" },
                  (g.options || []).map(function (o) {
                    var on = (selectedOpts[g.id] || []).indexOf(o.id) >= 0;
                    return h(
                      "button",
                      {
                        key: o.id,
                        type: "button",
                        className: "wb-cr-chip" + (on ? " on" : ""),
                        style: on
                          ? { borderColor: "#0ea5e9", color: "#0369a1", background: "#e0f2fe" }
                          : undefined,
                        onClick: function () {
                          setSelectedOpts(function (prev) {
                            var next = Object.assign({}, prev);
                            var cur = (next[g.id] || []).slice();
                            if (g.multi) {
                              var ix = cur.indexOf(o.id);
                              if (ix >= 0) cur.splice(ix, 1);
                              else cur.push(o.id);
                            } else {
                              cur = [o.id];
                            }
                            next[g.id] = cur;
                            return next;
                          });
                        },
                      },
                      o.label || o.id,
                    );
                  }),
                ),
              );
            }),
            h(
              "label",
              { className: "wb-cr-label" },
              opts.notes_required ? "备注（必填）" : "备注（可选）",
            ),
            h("textarea", {
              className: "wb-cr-input",
              style: { width: "100%", minHeight: 72, boxSizing: "border-box", marginBottom: 8 },
              value: notes,
              placeholder: opts.notes_placeholder || "补充约束、验收点…",
              onChange: function (e) {
                setNotes(e.target.value);
              },
            }),
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  disabled: busy,
                  onClick: function () {
                    setPhase("form");
                    setErr("");
                  },
                },
                "返回改诉求",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn primary",
                  disabled: busy,
                  onClick: submitOptions,
                },
                busy ? "梳理中…" : "确认选项",
              ),
            ),
          ),
        ));
      }

      if (phase === "propose") {
        var pui = proposeUi || {};
        var val = pui.validation || {};
        var mod = (pui.target_hints && pui.target_hints.module) || "";
        var paths = (pui.target_hints && pui.target_hints.expected_paths) || [];
        var og2 = pui.original_goal || (pui.brief && pui.brief.original_goal) || goal;
        var hasErr = !!(val.errors && val.errors.length);
        var hasWarn = !!(val.warnings && val.warnings.length) && !hasErr;
        return wrapStack(h(
          "div",
          { className: "wb-cr" },
          head("写码确认 · 核对后再开工"),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, "请确认原始诉求、目标模块与需求摘要；确认后才会启动 Cursor。"),
            og2 ? h("p", { className: "wb-cr-dsh" }, "原始诉求：", h("code", null, og2)) : null,
            mod ? h("p", { className: "wb-cr-dsh" }, "目标模块：", h("code", null, mod)) : null,
            paths.length
              ? h(
                  "p",
                  { className: "wb-cr-dsh" },
                  "预期改动：",
                  paths.slice(0, 6).join(" · "),
                )
              : null,
            hasErr
              ? h("div", { className: "wb-cr-err" }, val.errors.join("\n"))
              : null,
            hasWarn
              ? h("div", { className: "wb-cr-warn" }, val.warnings.join("\n"))
              : null,
            h(WorkspaceMismatchHint, {
              dshCwd: dshCwd,
              workspace: workspace,
              home: props.home,
              onUseDsh: function () {
                setWorkspace(dshCwd);
              },
            }),
            h("label", { className: "wb-cr-label" }, "本机工程目录"),
            h(
              "div",
              { className: "wb-cr-row" },
              h("input", {
                className: "wb-cr-input",
                value: workspace,
                onChange: function (e) {
                  setWorkspace(e.target.value);
                },
              }),
              h(
                "button",
                { type: "button", className: "wb-cr-btn", disabled: busy, onClick: browse },
                "浏览…",
              ),
            ),
            h("label", { className: "wb-cr-label" }, "需求摘要（可编辑，须含原始业务名称）"),
            h("textarea", {
              className: "wb-cr-input",
              style: {
                width: "100%",
                minHeight: 120,
                boxSizing: "border-box",
                fontFamily: "inherit",
                marginBottom: 8,
              },
              value: requirement,
              onChange: function (e) {
                setRequirement(e.target.value);
              },
            }),
            hasWarn
              ? h(
                  "label",
                  { className: "wb-set-check" },
                  h("input", {
                    type: "checkbox",
                    checked: ackWarn,
                    onChange: function (e) {
                      setAckWarn(e.target.checked);
                    },
                  }),
                  h("span", null, "我已核对原始诉求与目标模块，确认摘要不偏离业务目标"),
                )
              : null,
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  disabled: busy,
                  onClick: function () {
                    setPhase("form");
                    setErr("");
                  },
                },
                "返回改诉求",
              ),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn primary",
                  disabled: busy || hasErr,
                  onClick: confirmStart,
                },
                busy ? "启动中…" : "确认并用 Cursor 写入本机",
              ),
            ),
          ),
        ));
      }

      // form：只收集目录 + 原始诉求，再进入讨论（禁止直接 confirm）
      // 引导文案只保留顶部 CdFlowIntro，避免与卡内说明叠成「两个确认框」
      return wrapStack(h(
        "div",
        { className: "wb-cr" },
        head("选择目录 · 填写诉求 · 先梳理需求"),
        h(
          "div",
          { className: "wb-cr-body" },
          h(WorkspaceMismatchHint, {
            dshCwd: dshCwd,
            workspace: workspace,
            home: props.home,
            onUseDsh: function () {
              setWorkspace(dshCwd);
            },
          }),
          h("label", { className: "wb-cr-label" }, "本机工程目录"),
          h(
            "div",
            { className: "wb-cr-row" },
            h("input", {
              className: "wb-cr-input",
              value: workspace,
              placeholder: "/Users/你/项目",
              onChange: function (e) {
                setWorkspace(e.target.value);
              },
            }),
            h(
              "button",
              { type: "button", className: "wb-cr-btn", disabled: busy, onClick: browse },
              busy ? "选择中…" : "浏览…",
            ),
          ),
          suggestions.length
            ? h(
                "div",
                { className: "wb-cr-chips" },
                suggestions.map(function (s, i) {
                  var p = typeof s === "string" ? s : (s && s.path) || "";
                  var lab = typeof s === "object" && s.label ? s.label + " · " : "";
                  if (!p) return null;
                  return h(
                    "button",
                    {
                      key: i + p,
                      type: "button",
                      className: "wb-cr-chip",
                      title: p,
                      onClick: function () {
                        setWorkspace(p);
                      },
                    },
                    lab + p,
                  );
                }),
              )
            : null,
          h("label", { className: "wb-cr-label" }, "原始写码诉求（一句话也行，下一步会帮你补全）"),
          h("textarea", {
            className: "wb-cr-input",
            style: {
              width: "100%",
              minHeight: 96,
              boxSizing: "border-box",
              fontFamily: "inherit",
              marginBottom: 10,
            },
            value: requirement,
            placeholder: "例如：MES系统仓库管理菜单新增物料出库界面",
            onChange: function (e) {
              setRequirement(e.target.value);
              setGoal(e.target.value);
            },
          }),
          err ? h("p", { className: "wb-cr-err" }, err) : null,
          h(
            "div",
            { className: "wb-cr-actions" },
            h(
              "button",
              {
                type: "button",
                className: "wb-cr-btn primary",
                disabled: busy,
                onClick: function () {
                  setGoal(requirement);
                  runDiscuss();
                },
              },
              busy ? "梳理中…" : "下一步：梳理需求",
            ),
          ),
        ),
      ));
    }

    var CDP_UI_REV = "2026-09-10o-cdp-session";
    var CDP_PERSIST_VER = 1;

    function cdpBlockCallId(block, callIdProp) {
      if (callIdProp != null && String(callIdProp).trim()) return String(callIdProp).trim();
      if (!block) return "";
      var nested = block.call && typeof block.call === "object" ? block.call : null;
      return String(
        block.callId ||
          block.toolCallId ||
          (nested && (nested.callId || nested.toolCallId || nested.id)) ||
          block.id ||
          "",
      ).trim();
    }

    function cdpBlockSessionId(block, sessionId) {
      return String(
        sessionId ||
          (block &&
            (block.threadId ||
              block.thread_id ||
              block.sessionId ||
              block.session_id ||
              block.conversationId ||
              "")) ||
          "",
      ).trim();
    }

    function cdpPersistKey(block, sessionId, callIdProp) {
      var callId = cdpBlockCallId(block, callIdProp);
      var sid = cdpBlockSessionId(block, sessionId);
      if (callId && sid) return "wb-cdp-card:" + sid + ":" + callId;
      if (callId) return "wb-cdp-card:call:" + callId;
      if (sid) return "wb-cdp-card:session:" + sid + ":lone";
      return "wb-cdp-card:anon";
    }

    function cdpPersistKeyAliases(block, sessionId, callIdProp) {
      var callId = cdpBlockCallId(block, callIdProp);
      var sid = cdpBlockSessionId(block, sessionId);
      var keys = [cdpPersistKey(block, sessionId, callIdProp)];
      if (callId) {
        keys.push("wb-cdp-card:call:" + callId, "wb-cdp-card:block:" + callId);
        if (sid) keys.push("wb-cdp-card:" + sid + ":" + callId);
      } else if (sid) {
        keys.push("wb-cdp-card:" + sid, "wb-cdp-card:session:" + sid + ":lone");
      } else {
        keys.push("wb-cdp-card:anon");
      }
      var uniq = [];
      var seen = {};
      keys.forEach(function (k) {
        if (!k || seen[k]) return;
        seen[k] = true;
        uniq.push(k);
      });
      return uniq;
    }

    function cdpPersistBelongsToCall(saved, callId) {
      if (!saved || typeof saved !== "object") return false;
      var cid = String(callId || "").trim();
      if (!cid) return false;
      return String(saved.callId || "").trim() === cid;
    }

    function cdpPersistNormalize(o) {
      if (!o || typeof o !== "object") return null;
      if (Number(o.v || 0) < 1) return null;
      return o;
    }

    function cdpPersistLoad(key) {
      try {
        var raw = localStorage.getItem(key);
        if (!raw) return null;
        return cdpPersistNormalize(JSON.parse(raw));
      } catch (e) {
        return null;
      }
    }

    function cdpPersistLoadForCard(block, sessionId, callIdProp) {
      try {
        var callId = cdpBlockCallId(block, callIdProp);
        var key = cdpPersistKey(block, sessionId, callIdProp);
        var aliases = cdpPersistKeyAliases(block, sessionId, callIdProp);
        for (var i = 0; i < aliases.length; i++) {
          var hit = cdpPersistLoad(aliases[i]);
          if (hit && cdpPersistBelongsToCall(hit, callId) && (hit.done || hit.phase === "done")) {
            return { key: key, saved: hit };
          }
        }
        return { key: key, saved: null };
      } catch (eLoad) {
        return { key: cdpPersistKey(block, sessionId, callIdProp), saved: null };
      }
    }

    function cdpPersistSaveCard(block, sessionId, callIdProp, data) {
      var callId = cdpBlockCallId(block, callIdProp) || (data && data.callId) || "";
      if (!callId) return "";
      var aliases = cdpPersistKeyAliases(block, sessionId, callIdProp);
      var payload = Object.assign({ v: CDP_PERSIST_VER, at: Date.now() }, data || {}, {
        callId: callId,
        sessionId: cdpBlockSessionId(block, sessionId) || (data && data.sessionId) || "",
      });
      aliases.forEach(function (k) {
        try {
          localStorage.setItem(k, JSON.stringify(payload));
        } catch (e0) {}
      });
      return aliases[0];
    }

    /** 一体部署确认卡：单卡一步确认（精简 meta，避免工具卡丢 units） */
    function CodeDeployConfirmCard(props) {
      ensureCss();
      var block = props.block;
      var toolCallId = String(props.callId || cdpBlockCallId(block, "") || "").trim();
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var kind = String(ui.kind || (wb && String(wb.t || "").replace(/^cdp-/, "")) || "confirm");
      var persistBoot = useMemo(
        function () {
          return cdpPersistLoadForCard(block, props.sessionId, toolCallId);
        },
        [block, props.sessionId, toolCallId],
      );
      var bootSaved =
        persistBoot.saved && cdpPersistBelongsToCall(persistBoot.saved, toolCallId)
          ? persistBoot.saved
          : null;

      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _done = useState(function () {
        if (bootSaved && (bootSaved.done || bootSaved.phase === "done")) return true;
        return kind === "success";
      });
      var done = _done[0];
      var setDone = _done[1];
      var _success = useState(function () {
        if (bootSaved && bootSaved.success) return bootSaved.success;
        return kind === "success" ? ui : null;
      });
      var success = _success[0];
      var setSuccess = _success[1];

      function cdpSnapshot(doneFlag, successObj) {
        if (!toolCallId) return;
        cdpPersistSaveCard(block, props.sessionId, toolCallId, {
          phase: "done",
          done: !!doneFlag,
          success: successObj || null,
          jobId: (ui && ui.job_id) || (successObj && successObj.job_id) || "",
        });
      }

      function resolveIds(src) {
        var u = src || {};
        if (Array.isArray(u.unit_ids) && u.unit_ids.length) {
          return u.unit_ids.map(String).filter(Boolean);
        }
        var exec = u.execution || {};
        if (Array.isArray(exec.unit_ids) && exec.unit_ids.length) {
          return exec.unit_ids.map(String).filter(Boolean);
        }
        var list =
          u.mode === "full" || u.force_full
            ? u.units_full || u.units || []
            : u.units_incremental || u.units || [];
        return (list || [])
          .map(function (x) {
            return typeof x === "string" ? x : (x && x.id) || "";
          })
          .filter(Boolean);
      }

      var forceFull = !!(ui.force_full || ui.locked_mode === "full");
      var mode = forceFull ? "full" : ui.mode === "full" ? "full" : "incremental";
      var ids = resolveIds(ui);
      var unitCount = Number(ui.unit_count) || ids.length;
      var entry = ui.entry_url || ui.access_url || ui.health_url || "";
      var canGo = ui.can_deploy !== false && !!ui.job_id && (ids.length > 0 || unitCount > 0);

      // 准备失败时不要画空确认卡（——:— / 0 单元）；已完成态优先恢复
      if (!done && kind === "confirm" && !ui.job_id) {
        return h(
          "div",
          { className: "wb-cr" },
          h("div", { className: "wb-cr-head" }, h("span", { className: "wb-cr-badge" }, "部署未就绪")),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-err" }, "请再说一次「部署上线」（勿选 production）"),
          ),
        );
      }

      function doReject() {
        if (!ui.job_id) {
          setDone(true);
          setSuccess({ cancelled: true });
          cdpSnapshot(true, { cancelled: true });
          return;
        }
        setBusy(true);
        setErr("");
        issueHitl("code-deploy.confirm", { job_id: ui.job_id })
          .then(function (nonce) {
            return fetch(engineBase() + "/api/code-deploy/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ job_id: ui.job_id, decision: "reject", nonce: nonce }),
            }).then(function (r) {
              return r.json();
            });
          })
          .then(function () {
            setDone(true);
            setSuccess({ cancelled: true });
            cdpSnapshot(true, { cancelled: true });
            setBusy(false);
          })
          .catch(function (e) {
            setErr((e && e.message) || "取消失败");
            setBusy(false);
          });
      }

      function doApprove() {
        var sendIds = ids.length ? ids : resolveIds(ui);
        if (!ui.job_id || (!sendIds.length && !unitCount)) {
          setErr("没有可同步的单元");
          return;
        }
        if (!canGo && !sendIds.length) {
          setErr("当前不可部署，请检查配置");
          return;
        }
        setBusy(true);
        setErr("");
        issueHitl("code-deploy.confirm", { job_id: ui.job_id })
          .then(function (nonce) {
            return fetch(engineBase() + "/api/code-deploy/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                job_id: ui.job_id,
                decision: "approve",
                mode: mode,
                unit_ids: sendIds,
                nonce: nonce,
              }),
            }).then(function (r) {
              return r.json();
            });
          })
          .then(function (d) {
            if (!d || !d.ok) {
              setErr((d && (d.detail || d.reply)) || "部署失败");
              setBusy(false);
              return;
            }
            var succ = d.deploy_success || d.code_deploy_ui || {};
            var successObj = {
              title: succ.title || (mode === "full" ? "全量部署完成" : "增量部署完成"),
              entry_url: succ.entry_url || succ.access_url || succ.health_url || entry,
              remote: succ.remote || "",
              env: succ.env || ui.env || "",
              units: succ.units || ids,
              actions: succ.actions || [],
              job_id: ui.job_id,
            };
            setSuccess(successObj);
            setDone(true);
            cdpSnapshot(true, successObj);
            setBusy(false);
          })
          .catch(function (e) {
            setErr((e && e.message) || "部署请求失败");
            setBusy(false);
          });
      }

      if (done && success) {
        if (success.cancelled) {
          return h(
            "div",
            { className: "wb-cr" },
            h(
              "div",
              { className: "wb-cr-head" },
              h("span", { className: "wb-cr-badge" }, "已取消"),
              h("span", { className: "wb-cr-hint" }, CDP_UI_REV),
            ),
            h("div", { className: "wb-cr-body" }, h("p", { className: "wb-cr-sum" }, "未执行同步")),
          );
        }
        return h(
          "div",
          { className: "wb-cr" },
          h(
            "div",
            { className: "wb-cr-head" },
            h("span", { className: "wb-cr-badge" }, "部署完成"),
            h("span", { className: "wb-cr-hint" }, CDP_UI_REV),
          ),
          h(
            "div",
            { className: "wb-cr-body" },
            h("p", { className: "wb-cr-sum" }, success.title || "部署完成"),
            success.remote ? h("p", { className: "wb-cr-sum" }, success.remote) : null,
            success.entry_url
              ? h(
                  "p",
                  { className: "wb-cr-sum" },
                  h(
                    "a",
                    { href: success.entry_url, target: "_blank", rel: "noopener noreferrer" },
                    success.entry_url,
                  ),
                )
              : null,
            Array.isArray(success.actions) && success.actions.length
              ? h(
                  "ul",
                  { className: "wb-cr-units", style: { display: "block", marginTop: "8px" } },
                  success.actions.map(function (a, i) {
                    return h("li", { key: String(i) }, String(a));
                  }),
                )
              : null,
          ),
        );
      }

      var title = forceFull || mode === "full" ? "确认全量部署" : "确认增量部署";
      var remote =
        (ui.ssh_host || "—") + ":" + (ui.ssh_app_path || "—");
      var unitRows = Array.isArray(ui.units) && ui.units.length
        ? ui.units
        : ids.map(function (id) {
            return { id: id, label: id, kind: "" };
          });
      var gitLine = "";
      if (ui.head_sha_short || ui.head_ref) {
        gitLine =
          (ui.head_ref || "HEAD") +
          (ui.head_sha_short ? " @" + ui.head_sha_short : "");
        if (ui.base_ref && ui.base_ref !== "(none)") {
          gitLine = String(ui.base_ref).slice(0, 10) + " → " + gitLine;
        }
      }

      function kv(label, node) {
        if (!node) return null;
        return [h("dt", null, label), h("dd", null, node)];
      }

      return h(
        "div",
        { className: "wb-cr" },
        h(
          "div",
          { className: "wb-cr-head" },
          h("span", { className: "wb-cr-badge" }, title),
          h(
            "span",
            { className: "wb-cr-hint" },
            ui.unified_product
              ? "点确认后才会同步并拉起远端入口"
              : "点确认后才会同步文件",
          ),
        ),
        h(
          "div",
          { className: "wb-cr-body" },
          h(
            "dl",
            { className: "wb-cr-kv" },
            kv("环境", ui.env || "staging"),
            kv("远端", remote),
            entry
              ? kv(
                  "入口",
                  h(
                    "a",
                    { href: entry, target: "_blank", rel: "noopener noreferrer" },
                    entry,
                  ),
                )
              : null,
            ui.workspace ? kv("本机仓", ui.workspace) : null,
            gitLine ? kv("版本", gitLine) : null,
            kv(
              "范围",
              (unitCount || ids.length) +
                " 个单元 · " +
                (forceFull ? "全量锁定" : mode === "full" ? "全量" : "增量"),
            ),
          ),
          unitRows.length
            ? h(
                "div",
                { className: "wb-cr-units" },
                unitRows.map(function (u) {
                  var id = typeof u === "string" ? u : u.id;
                  var label = typeof u === "string" ? u : u.label || u.id;
                  var kind = typeof u === "string" ? "" : u.kind || "";
                  return h(
                    "span",
                    { key: id, className: "wb-cr-unit", title: id },
                    kind ? h("span", { className: "k" }, kind) : null,
                    label,
                  );
                }),
              )
            : null,
          ui.reason || ui.note
            ? h(
                "p",
                { className: "wb-cr-note" },
                ui.reason || ui.note,
              )
            : null,
          err ? h("p", { className: "wb-cr-err" }, err) : null,
          h(
            "div",
            { className: "wb-cr-actions" },
            h(
              "button",
              { type: "button", className: "wb-cr-btn", disabled: busy, onClick: doReject },
              "取消",
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-cr-btn primary",
                disabled: busy || !canGo,
                onClick: doApprove,
              },
              busy ? "部署中…" : "确认部署",
            ),
          ),
        ),
      );
    }

    function field(label, props, full) {
      return h(
        "div",
        { className: "wb-set-field" + (full ? " full" : "") },
        h("label", null, label),
        h("input", props),
      );
    }

    function emptyDraft() {
      return {
        mes: {
          base_url: "",
          auth_type: "password",
          username: "",
          password: "",
          token: "",
          enterprise_code: "",
          extra_headers: "{}",
          verify_ssl: true,
          timeout: 30,
        },
        deepseek: {
          provider: "deepseek",
          api_key: "",
          base_url: "https://api.deepseek.com",
          model: "deepseek-chat",
        },
        code_dev: {
          enabled: false,
          cursor_api_key: "",
          model: "composer-2.5",
          max_concurrent: 1,
          cursor_timeout_sec: 2700,
          default_workspace: "",
        },
        code_review: {
          enabled: false,
          max_files: 40,
          max_file_bytes: 120000,
          max_total_bytes: 800000,
          default_workspace: "",
        },
        code_commit: {
          enabled: true,
          default_workspace: "",
          work_branch: "",
          remote_name: "origin",
          default_push: true,
          use_skill_review: true,
          allow_blocked: false,
          max_files: 80,
        },
        code_deploy: {
          enabled: false,
          provider: "local_ssh",
          unified_product: true,
          default_workspace: "",
          default_ref: "HEAD",
          default_env: "staging",
          env_whitelist: ["staging"],
          allow_production: false,
          ssh_host: "",
          ssh_user: "",
          ssh_port: 22,
          ssh_key_path: "",
          ssh_app_path: "",
          entry_url: "",
          health_url: "",
          health_timeout_sec: 8,
        },
      };
    }

    function patchDraft(setDraft, path, value) {
      setDraft(function (prev) {
        var next = Object.assign({}, prev);
        var cur = next;
        for (var i = 0; i < path.length - 1; i++) {
          var k = path[i];
          cur[k] = Object.assign({}, cur[k] || {});
          cur = cur[k];
        }
        cur[path[path.length - 1]] = value;
        return next;
      });
    }

    function WorkBuddySettingsSection() {
      ensureCss();
      var draftState = useState(emptyDraft);
      var draft = draftState[0];
      var setDraft = draftState[1];
      var busyState = useState(false);
      var busy = busyState[0];
      var setBusy = busyState[1];
      var msgState = useState("");
      var msg = msgState[0];
      var setMsg = msgState[1];
      var msgOkState = useState(false);
      var msgOk = msgOkState[0];
      var setMsgOk = msgOkState[1];
      var engHostState = useState(engineHost());
      var engHost = engHostState[0];
      var setEngHost = engHostState[1];
      var engPortState = useState(enginePort());
      var engPort = engPortState[0];
      var setEngPort = engPortState[1];
      var testState = useState({});
      var tests = testState[0];
      var setTests = testState[1];

      function applyEngineEndpoint() {
        try {
          localStorage.setItem("dsh-mes-engine-host", String(engHost || "127.0.0.1").trim());
          localStorage.setItem("dsh-mes-engine-port", String(engPort || "8000").trim());
        } catch (e) {}
      }

      function loadConfig() {
        setBusy(true);
        setMsg("加载中…");
        setMsgOk(false);
        applyEngineEndpoint();
        fetch(engineBase() + "/api/config")
          .then(function (r) {
            return r.json().then(function (d) {
              return { ok: r.ok, d: d };
            });
          })
          .then(function (x) {
            if (!x.ok || !x.d || !x.d.ok || !x.d.config) {
              throw new Error((x.d && (x.d.detail || x.d.message)) || "引擎未响应");
            }
            var c = x.d.config;
            var base = emptyDraft();
            setDraft({
              mes: Object.assign({}, base.mes, c.mes || {}),
              deepseek: Object.assign({}, base.deepseek, c.deepseek || {}),
              code_dev: Object.assign({}, base.code_dev, c.code_dev || {}),
              code_review: Object.assign({}, base.code_review, c.code_review || {}),
              code_commit: Object.assign({}, base.code_commit, c.code_commit || {}),
              code_deploy: Object.assign({}, base.code_deploy, c.code_deploy || {}),
            });
            setMsg("已从引擎加载");
            setMsgOk(true);
          })
          .catch(function (e) {
            setMsg("加载失败：" + (e && e.message ? e.message : String(e)) + "（请先 scripts/engine.sh zr-workbuddy ensure）");
            setMsgOk(false);
          })
          .finally(function () {
            setBusy(false);
          });
      }

      useEffect(function () {
        loadConfig();
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);

      function saveConfig() {
        setBusy(true);
        setMsg("保存中…");
        setMsgOk(false);
        applyEngineEndpoint();
        var payload = {
          mes: Object.assign({}, draft.mes, {
            timeout: Math.max(5, Number(draft.mes.timeout) || 30),
          }),
          deepseek: Object.assign({}, draft.deepseek),
          code_dev: Object.assign({}, draft.code_dev, {
            model: (draft.code_dev.model || "").trim() || "composer-2.5",
            max_concurrent: Math.max(1, Number(draft.code_dev.max_concurrent) || 1),
            cursor_timeout_sec: Math.max(60, Number(draft.code_dev.cursor_timeout_sec) || 2700),
            default_workspace: (draft.code_dev.default_workspace || "").trim(),
          }),
          code_review: Object.assign({}, draft.code_review, {
            max_files: Math.max(1, Number(draft.code_review.max_files) || 40),
            max_file_bytes: Math.max(1024, Number(draft.code_review.max_file_bytes) || 120000),
            max_total_bytes: Math.max(4096, Number(draft.code_review.max_total_bytes) || 800000),
            default_workspace: (draft.code_review.default_workspace || "").trim(),
          }),
          code_commit: Object.assign({}, draft.code_commit, {
            default_workspace: (draft.code_commit.default_workspace || "").trim(),
            work_branch: (draft.code_commit.work_branch || "").trim(),
            remote_name: (draft.code_commit.remote_name || "").trim() || "origin",
            max_files: Math.max(1, Number(draft.code_commit.max_files) || 80),
            use_skill_review: draft.code_commit.use_skill_review !== false,
            allow_blocked: !!draft.code_commit.allow_blocked,
          }),
          code_deploy: Object.assign({}, draft.code_deploy, {
            provider: "local_ssh",
            unified_product: draft.code_deploy.unified_product !== false,
            default_workspace: (draft.code_deploy.default_workspace || "").trim(),
            default_ref: (draft.code_deploy.default_ref || "").trim() || "HEAD",
            default_env: "staging",
            env_whitelist: ["staging"],
            allow_production: false,
            ssh_host: (draft.code_deploy.ssh_host || "").trim(),
            ssh_user: (draft.code_deploy.ssh_user || "").trim(),
            ssh_port: Math.max(1, Number(draft.code_deploy.ssh_port) || 22),
            ssh_key_path: (draft.code_deploy.ssh_key_path || "").trim(),
            ssh_app_path: (draft.code_deploy.ssh_app_path || "").trim(),
            entry_url: (draft.code_deploy.entry_url || draft.code_deploy.health_url || "").trim(),
            health_url: (draft.code_deploy.entry_url || draft.code_deploy.health_url || "").trim(),
            health_timeout_sec: 8,
          }),
        };
        fetch(engineBase() + "/api/config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: payload }),
        })
          .then(function (r) {
            return r.json().then(function (d) {
              return { ok: r.ok, d: d };
            });
          })
          .then(function (x) {
            if (!x.ok || !x.d || !x.d.ok) {
              throw new Error((x.d && (x.d.detail || x.d.message)) || "保存失败");
            }
            var c = x.d.config || {};
            var base = emptyDraft();
            setDraft({
              mes: Object.assign({}, base.mes, c.mes || {}),
              deepseek: Object.assign({}, base.deepseek, c.deepseek || {}),
              code_dev: Object.assign({}, base.code_dev, c.code_dev || {}),
              code_review: Object.assign({}, base.code_review, c.code_review || {}),
              code_commit: Object.assign({}, base.code_commit, c.code_commit || {}),
              code_deploy: Object.assign({}, base.code_deploy, c.code_deploy || {}),
            });
            setMsg("已保存到引擎 config.yaml");
            setMsgOk(true);
          })
          .catch(function (e) {
            setMsg("保存失败：" + (e && e.message ? e.message : String(e)));
            setMsgOk(false);
          })
          .finally(function () {
            setBusy(false);
          });
      }

      function runTest(key, path, body) {
        applyEngineEndpoint();
        setTests(function (prev) {
          var n = Object.assign({}, prev);
          n[key] = "测试中…";
          return n;
        });
        var opts = body
          ? {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }
          : undefined;
        fetch(engineBase() + path, opts)
          .then(function (r) {
            return r.json().then(function (d) {
              return { ok: r.ok, d: d };
            });
          })
          .then(function (x) {
            var d = x.d || {};
            var text =
              d.detail ||
              d.message ||
              d.summary ||
              (d.ok === false ? "未就绪" : d.ok ? "OK" : JSON.stringify(d).slice(0, 240));
            setTests(function (prev) {
              var n = Object.assign({}, prev);
              n[key] = (x.ok && d.ok !== false ? "✅ " : "❌ ") + text;
              return n;
            });
          })
          .catch(function (e) {
            setTests(function (prev) {
              var n = Object.assign({}, prev);
              n[key] = "❌ " + (e && e.message ? e.message : String(e));
              return n;
            });
          });
      }

      var mes = draft.mes;
      var llm = draft.deepseek;
      var cd = draft.code_dev;
      var cr = draft.code_review;
      var cc = draft.code_commit;
      var cdp = draft.code_deploy;

      return h(
        "div",
        { className: "wb-set" },
        h(
          "p",
          { className: "wb-set-lead" },
          "与宿主「设置」同级的 WorkBuddy 配置中心。保存写入引擎 config.yaml；不必再打开 :8000。",
        ),
        h(
          "div",
          { className: "wb-set-eng" },
          h("label", null, "引擎 host"),
          h("input", {
            value: engHost,
            onChange: function (e) {
              setEngHost(e.target.value);
            },
          }),
          h("label", null, "port"),
          h("input", {
            value: engPort,
            onChange: function (e) {
              setEngPort(e.target.value);
            },
          }),
          h(
            "button",
            {
              type: "button",
              className: "wb-set-btn",
              disabled: busy,
              onClick: function () {
                applyEngineEndpoint();
                loadConfig();
              },
            },
            "连接并加载",
          ),
        ),
        h(
          "div",
          { className: "wb-set-card" },
          h("h3", null, "1 · MES 连接"),
          h(
            "div",
            { className: "body" },
            h("div", { className: "wb-set-grid" },
              field(
                "Base URL",
                {
                  value: mes.base_url || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["mes", "base_url"], e.target.value);
                  },
                },
                true,
              ),
              h(
                "div",
                { className: "wb-set-field full" },
                h("label", null, "认证方式"),
                h(
                  "div",
                  { className: "wb-set-radios" },
                  ["password", "token", "apikey", "none"].map(function (v) {
                    return h(
                      "label",
                      { key: v },
                      h("input", {
                        type: "radio",
                        name: "wb-mes-auth",
                        checked: (mes.auth_type || "password") === v,
                        onChange: function () {
                          patchDraft(setDraft, ["mes", "auth_type"], v);
                        },
                      }),
                      " ",
                      v,
                    );
                  }),
                ),
              ),
              field("账号", {
                value: mes.username || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["mes", "username"], e.target.value);
                },
              }),
              field("密码（脱敏回显）", {
                type: "password",
                autoComplete: "new-password",
                value: mes.password || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["mes", "password"], e.target.value);
                },
              }),
              field(
                "企业编码",
                {
                  value: mes.enterprise_code || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["mes", "enterprise_code"], e.target.value);
                  },
                },
                true,
              ),
              field(
                "Token / API Key",
                {
                  type: "password",
                  autoComplete: "new-password",
                  value: mes.token || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["mes", "token"], e.target.value);
                  },
                },
                true,
              ),
              field(
                "附加请求头 JSON",
                {
                  value: mes.extra_headers || "{}",
                  onChange: function (e) {
                    patchDraft(setDraft, ["mes", "extra_headers"], e.target.value);
                  },
                },
                true,
              ),
              field("超时（秒）", {
                type: "number",
                min: 5,
                max: 120,
                value: mes.timeout != null ? mes.timeout : 30,
                onChange: function (e) {
                  patchDraft(setDraft, ["mes", "timeout"], e.target.value);
                },
              }),
              h(
                "div",
                { className: "wb-set-check" },
                h("input", {
                  type: "checkbox",
                  checked: mes.verify_ssl !== false,
                  onChange: function (e) {
                    patchDraft(setDraft, ["mes", "verify_ssl"], e.target.checked);
                  },
                }),
                h("span", null, "校验 HTTPS 证书"),
              ),
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-set-btn",
                disabled: busy,
                onClick: function () {
                  runTest("mes", "/api/config/test/mes", { config: { mes: draft.mes } });
                },
              },
              "测试 MES",
            ),
            tests.mes ? h("div", { className: "wb-set-test" }, tests.mes) : null,
          ),
        ),
        h(
          "div",
          { className: "wb-set-card" },
          h("h3", null, "2 · LLM 意图引擎"),
          h(
            "div",
            { className: "body" },
            h("p", { className: "wb-set-hint" }, "审码依赖此处 LLM；DeepSeek / Ollama / 关闭任选。"),
            h(
              "div",
              { className: "wb-set-radios" },
              [
                ["deepseek", "DeepSeek API"],
                ["ollama", "Ollama 本地"],
                ["none", "不使用 LLM"],
              ].map(function (pair) {
                return h(
                  "label",
                  { key: pair[0] },
                  h("input", {
                    type: "radio",
                    name: "wb-llm",
                    checked: (llm.provider || "deepseek") === pair[0],
                    onChange: function () {
                      patchDraft(setDraft, ["deepseek", "provider"], pair[0]);
                    },
                  }),
                  " ",
                  pair[1],
                );
              }),
            ),
            h(
              "div",
              { className: "wb-set-grid" },
              field(
                "API Key（脱敏回显）",
                {
                  type: "password",
                  autoComplete: "new-password",
                  value: llm.api_key || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["deepseek", "api_key"], e.target.value);
                  },
                },
                true,
              ),
              field("Base URL", {
                value: llm.base_url || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["deepseek", "base_url"], e.target.value);
                },
              }),
              field("模型", {
                value: llm.model || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["deepseek", "model"], e.target.value);
                },
              }),
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-set-btn",
                disabled: busy,
                onClick: function () {
                  runTest("llm", "/api/config/test/deepseek", {
                    config: { deepseek: draft.deepseek },
                  });
                },
              },
              "测试 LLM",
            ),
            tests.llm ? h("div", { className: "wb-set-test" }, tests.llm) : null,
          ),
        ),
        h(
          "div",
          { className: "wb-set-card" },
          h("h3", null, "3 · 写码车道"),
          h(
            "div",
            { className: "body" },
            h(
              "div",
              { className: "wb-set-check" },
              h("input", {
                type: "checkbox",
                checked: !!cd.enabled,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_dev", "enabled"], e.target.checked);
                },
              }),
              h("span", null, "开启本机写码（code_dev.enabled）"),
            ),
            h(
              "div",
              { className: "wb-set-grid" },
              field(
                "Cursor API Key",
                {
                  type: "password",
                  autoComplete: "new-password",
                  value: cd.cursor_api_key || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_dev", "cursor_api_key"], e.target.value);
                  },
                },
                true,
              ),
              field("本机模型", {
                value: cd.model || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["code_dev", "model"], e.target.value);
                },
              }),
              field("最大并发", {
                type: "number",
                min: 1,
                max: 4,
                value: cd.max_concurrent != null ? cd.max_concurrent : 1,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_dev", "max_concurrent"], e.target.value);
                },
              }),
              field("超时（秒）", {
                type: "number",
                min: 60,
                max: 7200,
                value: cd.cursor_timeout_sec != null ? cd.cursor_timeout_sec : 2700,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_dev", "cursor_timeout_sec"], e.target.value);
                },
              }),
              field(
                "常用工程路径（备忘）",
                {
                  value: cd.default_workspace || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_dev", "default_workspace"], e.target.value);
                  },
                },
                true,
              ),
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-set-btn",
                disabled: busy,
                onClick: function () {
                  runTest("cd", "/api/status");
                },
              },
              "探测引擎状态",
            ),
            tests.cd ? h("div", { className: "wb-set-test" }, tests.cd) : null,
          ),
        ),
        h(
          "div",
          { className: "wb-set-card" },
          h("h3", null, "4 · 审码车道"),
          h(
            "div",
            { className: "body" },
            h(
              "div",
              { className: "wb-set-check" },
              h("input", {
                type: "checkbox",
                checked: !!cr.enabled,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_review", "enabled"], e.target.checked);
                },
              }),
              h("span", null, "开启本机审码（code_review.enabled）"),
            ),
            h(
              "div",
              { className: "wb-set-grid" },
              field("单次最多文件", {
                type: "number",
                min: 1,
                max: 200,
                value: cr.max_files != null ? cr.max_files : 40,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_review", "max_files"], e.target.value);
                },
              }),
              field("单文件最大字节", {
                type: "number",
                value: cr.max_file_bytes != null ? cr.max_file_bytes : 120000,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_review", "max_file_bytes"], e.target.value);
                },
              }),
              field("总读取上限", {
                type: "number",
                value: cr.max_total_bytes != null ? cr.max_total_bytes : 800000,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_review", "max_total_bytes"], e.target.value);
                },
              }),
              field(
                "常用工程路径",
                {
                  value: cr.default_workspace || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_review", "default_workspace"], e.target.value);
                  },
                },
                true,
              ),
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-set-btn",
                disabled: busy,
                onClick: function () {
                  runTest("cr", "/api/code-review/status");
                },
              },
              "测试审码就绪",
            ),
            tests.cr ? h("div", { className: "wb-set-test" }, tests.cr) : null,
          ),
        ),
        h(
          "div",
          { className: "wb-set-card" },
          h("h3", null, "5 · 提交车道"),
          h(
            "div",
            { className: "body" },
            h(
              "div",
              { className: "wb-set-check" },
              h("input", {
                type: "checkbox",
                checked: !!cc.enabled,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_commit", "enabled"], e.target.checked);
                },
              }),
              h("span", null, "开启人触发提交（code_commit.enabled）"),
            ),
            h(
              "div",
              { className: "wb-set-grid" },
              field(
                "常用工程路径",
                {
                  value: cc.default_workspace || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_commit", "default_workspace"], e.target.value);
                  },
                },
                true,
              ),
              field("工作分支（空=当前；勿填 main/master）", {
                value: cc.work_branch || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["code_commit", "work_branch"], e.target.value);
                },
              }),
              field("远程名", {
                value: cc.remote_name || "origin",
                onChange: function (e) {
                  patchDraft(setDraft, ["code_commit", "remote_name"], e.target.value);
                },
              }),
              h(
                "div",
                { className: "wb-set-check full" },
                h("input", {
                  type: "checkbox",
                  checked: cc.default_push !== false,
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_commit", "default_push"], e.target.checked);
                  },
                }),
                h("span", null, "确认卡默认勾选推送远程"),
              ),
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-set-btn",
                disabled: busy,
                onClick: function () {
                  runTest("cc", "/api/code-commit/status");
                },
              },
              "测试提交就绪",
            ),
            tests.cc ? h("div", { className: "wb-set-test" }, tests.cc) : null,
          ),
        ),
        h(
          "div",
          { className: "wb-set-card" },
          h("h3", null, "6 · 自动化部署"),
          h(
            "div",
            { className: "body" },
            h(
              "p",
              { className: "wb-set-hint" },
              "开启后：确认一次即同步到远端。Vite+后端项目会本机构建 frontend/dist、同步 backend，并自动重启远端 API。不自动 git commit。一体部署才会拉远端 WorkBuddy 引擎。"
            ),
            h(
              "div",
              { className: "wb-set-check" },
              h("input", {
                type: "checkbox",
                checked: !!cdp.enabled,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_deploy", "enabled"], e.target.checked);
                },
              }),
              h("span", null, "开启自动化部署"),
            ),
            h(
              "div",
              { className: "wb-set-check" },
              h("input", {
                type: "checkbox",
                checked: cdp.unified_product !== false,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_deploy", "unified_product"], e.target.checked);
                },
              }),
              h("span", null, "一体部署（推荐）"),
            ),
            h(
              "div",
              { className: "wb-set-grid" },
              field("默认分支 / tag", {
                value: cdp.default_ref || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["code_deploy", "default_ref"], e.target.value);
                },
              }),
              field(
                "浏览器一体入口",
                {
                  value: cdp.entry_url || cdp.health_url || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_deploy", "entry_url"], e.target.value);
                    patchDraft(setDraft, ["code_deploy", "health_url"], e.target.value);
                  },
                },
                true,
              ),
              field(
                "本地项目路径",
                {
                  value: cdp.default_workspace || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_deploy", "default_workspace"], e.target.value);
                  },
                },
                true,
              ),
              field("SSH 主机", {
                value: cdp.ssh_host || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["code_deploy", "ssh_host"], e.target.value);
                },
              }),
              field("SSH 用户", {
                value: cdp.ssh_user || "",
                onChange: function (e) {
                  patchDraft(setDraft, ["code_deploy", "ssh_user"], e.target.value);
                },
              }),
              field(
                "私钥路径",
                {
                  value: cdp.ssh_key_path || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_deploy", "ssh_key_path"], e.target.value);
                  },
                },
                true,
              ),
              field(
                "远端目录",
                {
                  value: cdp.ssh_app_path || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_deploy", "ssh_app_path"], e.target.value);
                  },
                },
                true,
              ),
              field("SSH 端口", {
                value: cdp.ssh_port != null ? cdp.ssh_port : 22,
                onChange: function (e) {
                  patchDraft(setDraft, ["code_deploy", "ssh_port"], e.target.value);
                },
              }),
              field(
                "远端重启命令（可选；不填则自动重启该目录的 API 服务）",
                {
                  value: cdp.remote_restart_cmd || "",
                  onChange: function (e) {
                    patchDraft(setDraft, ["code_deploy", "remote_restart_cmd"], e.target.value);
                  },
                },
                true,
              ),
            ),
            h(
              "button",
              {
                type: "button",
                className: "wb-set-btn",
                disabled: busy,
                onClick: function () {
                  runTest("cdp", "/api/code-deploy/status");
                },
              },
              "测试部署就绪",
            ),
            tests.cdp ? h("div", { className: "wb-set-test" }, tests.cdp) : null,
          ),
        ),
        h(
          "div",
          { className: "wb-set-bar" },
          h(
            "button",
            {
              type: "button",
              className: "wb-set-btn primary",
              disabled: busy,
              onClick: saveConfig,
            },
            busy ? "处理中…" : "保存全部配置",
          ),
          h(
            "button",
            {
              type: "button",
              className: "wb-set-btn",
              disabled: busy,
              onClick: loadConfig,
            },
            "重新加载",
          ),
          msg
            ? h("span", { className: "wb-set-msg" + (msgOk ? " ok" : " err") }, msg)
            : null,
        ),
      );
    }

    function apply(ctx) {
      discoverEngine();
      if (!ctx || !ctx.slots || typeof ctx.slots.inject !== "function") {
        console.error("[dsh-mes-bridge] 无 slots 服务：无法注册 WorkBuddy 客户端能力");
        return;
      }
      ctx.slots.inject("settings.section", function () {
        return ctx.slots.register(
          {
            name: "settings.section",
            id: "workbuddy",
            order: 5,
            label: "WorkBuddy",
          },
          WorkBuddySettingsSection,
        );
      });
      ctx.slots.inject("tool.call.toolview", function () {
        return ctx.slots.register(
          { name: "tool.call.toolview", key: "mes_code_review_begin" },
          CodeReviewBeginCard,
        );
      });
      ctx.slots.inject("tool.call.toolview", function () {
        return ctx.slots.register(
          { name: "tool.call.toolview", key: "mes_code_commit_begin" },
          CodeCommitBeginCard,
        );
      });
      ctx.slots.inject("tool.call.toolview", function () {
        return ctx.slots.register(
          { name: "tool.call.toolview", key: "mes_code_dev_begin" },
          CodeDevBeginCard,
        );
      });
      ctx.slots.inject("tool.call.toolview", function () {
        return ctx.slots.register(
          { name: "tool.call.toolview", key: "mes_code_deploy_begin" },
          CodeDeployConfirmCard,
        );
      });
      ctx.slots.inject("tool.call.toolview", function () {
        return ctx.slots.register(
          { name: "tool.call.toolview", key: "mes_code_deploy_prepare" },
          CodeDeployConfirmCard,
        );
      });
      ctx.slots.inject("tool.call.toolview", function () {
        return ctx.slots.register(
          { name: "tool.call.toolview", key: "mes_code_deploy_confirm" },
          CodeDeployConfirmCard,
        );
      });
      console.log(
        "[dsh-mes-bridge] settings.section=WorkBuddy + toolview review/commit/code_dev/deploy",
      );
      try {
        if (document && document.title && document.title.indexOf("WorkBuddy") < 0) {
          document.title = "WorkBuddy · " + document.title;
        }
      } catch (_eTitle) {}
    }

    module.exports = { inject: ["slots"], apply: apply };
    return module.exports;
  },
});

/**
 * ZR-WorkBuddy 聊天面板（业务插件）
 * 引擎地址：下方 RUNTIME 块由 plugin.sh/start-engine.sh 从 engine/config/runtime.yaml 同步。
 */
/*RUNTIME_BEGIN*/
window.__APP_ENGINE__ = { host: "127.0.0.1", port: 8000 };
/*RUNTIME_END*/
window.__ModuleLoader__.load({
  id: "@dsh-external/dsh-mes-bridge",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;

    function engineHost() {
      try {
        var h = localStorage.getItem("dsh-mes-engine-host");
        if (h) return h;
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
    function ENGINE_URL() { return engineBase() + "/api/chat"; }
    function STATUS_URL() { return engineBase() + "/api/status"; }
    function RUNTIME_URL() { return engineBase() + "/api/runtime"; }
    /** 启动时探测 /api/runtime，校正本机地址（优先于仅靠 RUNTIME 同步块） */
    function discoverEngine(done) {
      fetch(RUNTIME_URL(), { method: "GET" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.ok && d.port) {
            try {
              if (d.host) localStorage.setItem("dsh-mes-engine-host", String(d.host));
              localStorage.setItem("dsh-mes-engine-port", String(d.port));
            } catch (e) {}
          }
          if (done) done(true);
        })
        .catch(function () { if (done) done(false); });
    }
    var LS_KEY = "dsh-mes-panel-convs";
    var SUGGESTIONS = [
      "今天正在生产的工单有多少个",
      "PCB有哪些工序",
      "飞针和 AOI 在短路检测上怎么分工？",
      "最近7天各产线产量对比",
      "分析8月30号良率过低的原因",
    ];

    var CSS =
      "#dshMesPanelRoot{position:fixed;right:20px;bottom:20px;z-index:2147483000;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif}" +
      "#dshMesToggle{width:52px;height:52px;border-radius:50%;border:none;background:linear-gradient(135deg,#4d6bfe,#7c5cfc);color:#fff;font-size:22px;cursor:pointer;box-shadow:0 6px 20px rgba(77,107,254,.35);display:flex;align-items:center;justify-content:center}" +
      "#dshMesPanel{display:none;position:absolute;right:0;bottom:64px;width:420px;max-width:calc(100vw - 40px);height:min(680px,calc(100vh - 120px));background:#fff;border:1px solid #e8e8ea;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.18);flex-direction:column;overflow:hidden}" +
      "#dshMesPanel.open{display:flex}" +
      "#dshMesHead{padding:12px 16px;border-bottom:1px solid #eef0f3;display:flex;align-items:center;gap:8px;font-weight:600;font-size:14px}" +
      "#dshMesHead .dot{width:8px;height:8px;border-radius:50%;background:#9ca3af}" +
      "#dshMesHead .dot.ok{background:#22c55e}" +
      "#dshMesHead .close{margin-left:auto;border:none;background:none;font-size:16px;cursor:pointer;color:#6b7280}" +
      "#dshMesMsgs{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:12px;font-size:13px;line-height:1.65}" +
      "#dshMesMsgs .user{align-self:flex-end;background:#f2f2f3;border-radius:12px 12px 4px 12px;padding:8px 12px;max-width:85%;white-space:pre-wrap;word-break:break-word}" +
      "#dshMesMsgs .assist{align-self:flex-start;max-width:100%}" +
      "#dshMesMsgs .assist .reply{white-space:normal;word-break:break-word;line-height:1.55}" +
      "#dshMesMsgs .assist .reply strong{font-weight:600}" +
      "#dshMesMsgs .assist .reply h1,#dshMesMsgs .assist .reply h2,#dshMesMsgs .assist .reply h3,#dshMesMsgs .assist .reply h4{margin:0.45em 0 0.2em;font-weight:650;line-height:1.35}" +
      "#dshMesMsgs .assist .reply h1{font-size:1.15em}" +
      "#dshMesMsgs .assist .reply h2{font-size:1.08em}" +
      "#dshMesMsgs .assist .reply h3{font-size:1.02em}" +
      "#dshMesMsgs .assist .reply h4{font-size:1em}" +
      "#dshMesMsgs .assist .reply .md-inline{font-family:ui-monospace,Menlo,monospace;font-size:0.92em;padding:1px 5px;border-radius:4px;background:#0f172a0d}" +
      "#dshMesMsgs .assist .reply .md-code{display:block;margin:6px 0 8px;padding:8px 10px;border-radius:8px;background:#0f172a0d;border:1px solid #e5e7eb;font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre;overflow-x:auto;line-height:1.45}" +
      "#dshMesMsgs .assist .reply .md-code code{font-family:inherit;font-size:inherit;background:none;padding:0}" +
      "#dshMesMsgs .assist .reply .md-hr{border:none;border-top:1px solid #e5e7eb;margin:8px 0}" +
      "#dshMesMsgs .assist img{max-width:100%;border-radius:10px;border:1px solid #e8e8ea;margin-top:8px;display:block}" +
      "#dshMesMsgs .assist table{border-collapse:collapse;margin-top:8px;font-size:12px}" +
      "#dshMesMsgs .assist table td,#dshMesMsgs .assist table th{border:1px solid #e5e7eb;padding:4px 10px}" +
      "#dshMesMsgs .meta{font-size:11px;color:#9ca3af;margin-top:6px}" +
      "#dshMesMsgs .think{margin-bottom:10px;border:1px solid #e8ecf4;border-radius:10px;background:#f7f8fc;overflow:hidden}" +
      "#dshMesMsgs .think summary{cursor:pointer;list-style:none;padding:8px 12px;font-size:12px;color:#5b6475;user-select:none;display:flex;align-items:center;gap:6px}" +
      "#dshMesMsgs .think summary::-webkit-details-marker{display:none}" +
      "#dshMesMsgs .think summary:before{content:'▸';font-size:10px;color:#9aa3b2}" +
      "#dshMesMsgs .think[open] summary:before{content:'▾'}" +
      "#dshMesMsgs .think .think-body{padding:0 12px 10px;font-size:12px;color:#6b7280;white-space:pre-wrap;word-break:break-word;line-height:1.55;border-top:1px dashed #e5e9f0}" +
      "#dshMesMsgs .status-line{color:#9ca3af;font-size:12px;font-style:italic}" +
      "#dshMesMsgs .cd-card{margin-top:10px;border:1px solid #e8ecf4;border-radius:12px;background:#fff;overflow:hidden}" +
      "#dshMesMsgs .cd-card.done{opacity:.88}" +
      "#dshMesMsgs .cd-head{padding:10px 12px 6px}" +
      "#dshMesMsgs .cd-title-row{display:flex;align-items:center;gap:8px;margin-bottom:4px}" +
      "#dshMesMsgs .cd-badge{font-size:11px;font-weight:600;color:#4d6bfe;background:rgba(77,107,254,.1);padding:2px 8px;border-radius:999px}" +
      "#dshMesMsgs .cd-hint{font-size:11px;color:#9ca3af}" +
      "#dshMesMsgs .cd-summary{font-size:13px;font-weight:600;margin:0 0 2px}" +
      "#dshMesMsgs .cd-desc{font-size:12px;color:#6b7280;margin:0}" +
      "#dshMesMsgs .cd-group{padding:8px 12px;border-top:1px solid #eef0f3}" +
      "#dshMesMsgs .cd-group-label{font-size:12px;color:#6b7280;margin-bottom:6px;display:flex;gap:6px;align-items:center}" +
      "#dshMesMsgs .cd-req{color:#b45309;font-size:11px}" +
      "#dshMesMsgs .cd-mode{font-size:11px;color:#9ca3af}" +
      "#dshMesMsgs .cd-opts{display:flex;flex-wrap:wrap;gap:6px}" +
      "#dshMesMsgs .cd-opt{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border:1px solid #e5e7eb;border-radius:8px;font-size:12px;cursor:pointer;background:#f7f8fc}" +
      "#dshMesMsgs .cd-opt.on{border-color:#4d6bfe;background:rgba(77,107,254,.08)}" +
      "#dshMesMsgs .cd-field{display:block;padding:8px 12px;border-top:1px solid #eef0f3}" +
      "#dshMesMsgs .cd-label{display:block;font-size:11px;color:#6b7280;margin-bottom:4px}" +
      "#dshMesMsgs .cd-input{width:100%;box-sizing:border-box;border:1px solid #e5e7eb;border-radius:8px;padding:7px 9px;font-size:12px;font-family:inherit}" +
      "#dshMesMsgs .cd-textarea{resize:vertical;min-height:56px}" +
      "#dshMesMsgs .cd-error{color:#b91c1c;font-size:12px;padding:0 12px 6px;margin:0}" +
      "#dshMesMsgs .cd-actions{display:flex;gap:8px;justify-content:flex-end;padding:8px 12px 10px;border-top:1px solid #eef0f3}" +
      "#dshMesMsgs .cd-btn{border:1px solid #e5e7eb;border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer;background:#fff}" +
      "#dshMesMsgs .cd-btn.confirm{background:#4d6bfe;color:#fff;border-color:#4d6bfe}" +
      "#dshMesMsgs .cd-btn:disabled{opacity:.45;cursor:not-allowed}" +
      "#dshMesMsgs .cd-chosen{padding:6px 12px 10px;font-size:12px}" +
      "#dshMesMsgs .cd-chosen-row{display:flex;gap:8px;margin:3px 0}" +
      "#dshMesMsgs .cd-k{color:#9ca3af;min-width:56px;flex:none}" +
      "#dshMesMsgs .cdp-card .cd-k{min-width:72px}" +
      "#dshMesMsgs .cc-ok-files{margin:0;padding:0 12px 10px 28px;max-height:200px;overflow:auto;font-size:11px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#374151}" +
      "#dshMesMsgs .cc-ok-files li{margin:2px 0;word-break:break-all}" +
      "#dshMesMsgs .cd-path-row{display:flex;gap:8px;align-items:stretch}" +
      "#dshMesMsgs .cd-path-row .cd-input{flex:1;min-width:0}" +
      "#dshMesMsgs .cd-btn.browse{flex:none;white-space:nowrap}" +
      "#dshMesMsgs .cd-suggest{padding:0 12px 8px;margin:0;font-size:12px;color:#6b7280;display:flex;flex-wrap:wrap;gap:6px;align-items:center}" +
      "#dshMesMsgs .cd-chip{border:1px solid #e5e7eb;border-radius:999px;padding:4px 10px;font-size:11px;cursor:pointer;background:#f7f8fc;color:#374151;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
      "#dshMesMsgs .cd-chip:hover{border-color:#4d6bfe;color:#4d6bfe}" +
      "#dshMesMsgs .coding-plan{margin:10px 0 4px;padding:10px 12px;border:1px solid #e8eef5;border-radius:10px;background:#f8fafc;max-width:100%}" +
      "#dshMesMsgs .coding-plan.is-running{border-color:#bfdbfe;background:#f0f7ff}" +
      "#dshMesMsgs .coding-plan.is-done{border-color:#bbf7d0;background:#f0fdf4}" +
      "#dshMesMsgs .cp-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}" +
      "#dshMesMsgs .cp-badge{font-size:12px;font-weight:700;color:#1e3a5f;flex-shrink:0}" +
      "#dshMesMsgs .cp-summary{flex:1;font-size:12px;color:#64748b;min-width:100px}" +
      "#dshMesMsgs .cp-duration{font-size:11px;color:#94a3b8;font-variant-numeric:tabular-nums}" +
      "#dshMesMsgs .cp-list{margin:8px 0 0;padding:0;list-style:none}" +
      "#dshMesMsgs .cp-item{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-top:1px solid #eef2f7}" +
      "#dshMesMsgs .cp-item:first-child{border-top:none;padding-top:2px}" +
      "#dshMesMsgs .cp-icon{width:22px;height:22px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center}" +
      "#dshMesMsgs .cp-pending{width:20px;height:20px;border-radius:50%;background:#e2e8f0;color:#64748b;font-size:11px;font-weight:700;display:inline-flex;align-items:center;justify-content:center}" +
      "#dshMesMsgs .cp-check{width:20px;height:20px;border-radius:50%;background:#dcfce7;color:#15803d;font-size:12px;font-weight:700;display:inline-flex;align-items:center;justify-content:center}" +
      "#dshMesMsgs .cp-fail{width:20px;height:20px;border-radius:50%;background:#fee2e2;color:#be123c;font-size:12px;font-weight:700;display:inline-flex;align-items:center;justify-content:center}" +
      "#dshMesMsgs .cp-spinner{width:16px;height:16px;border:2px solid #bfdbfe;border-top-color:#2563eb;border-radius:50%;animation:cp-spin 0.7s linear infinite}" +
      "@keyframes cp-spin{to{transform:rotate(360deg)}}" +
      "#dshMesMsgs .cp-body{display:flex;flex-direction:column;gap:2px;min-width:0}" +
      "#dshMesMsgs .cp-title{font-size:13px;font-weight:600;color:#1f2937;line-height:1.45}" +
      "#dshMesMsgs .cp-state{font-size:11px;color:#94a3b8;font-weight:500}" +
      "#dshMesMsgs .cp-item.is-running .cp-title,#dshMesMsgs .cp-item.is-running .cp-state{color:#2563eb}" +
      "#dshMesMsgs .cd-done-banner{display:flex;align-items:flex-start;gap:10px;margin-top:10px;padding:12px 14px;border-radius:10px;font-size:13px;line-height:1.5}" +
      "#dshMesMsgs .cd-done-banner.ok{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46}" +
      "#dshMesMsgs .cd-done-banner.err{background:#fef2f2;border:1px solid #fecaca;color:#991b1b}" +
      "#dshMesMsgs .cd-done-icon{font-size:18px;font-weight:700;flex:none}" +
      "#dshMesMsgs .cd-synced{margin-top:6px;font-size:12px;color:#047857;word-break:break-all}" +
      "#dshMesMsgs .cd-result-details{margin-top:10px;border:1px solid #e8ecf4;border-radius:10px;background:#f7f8fc;overflow:hidden}" +
      "#dshMesMsgs .cd-result-details summary{cursor:pointer;padding:8px 12px;font-size:12px;font-weight:600;color:#64748b;list-style:none}" +
      "#dshMesMsgs .cd-result-details summary::-webkit-details-marker{display:none}" +
      "#dshMesMsgs .cd-result-body{padding:0 12px 12px;font-size:13px;max-height:480px;overflow-y:auto;white-space:pre-wrap;word-break:break-word;line-height:1.55}" +
      "#dshMesMsgs .cd-result-body h2,#dshMesMsgs .cd-result-body h3,#dshMesMsgs .cd-result-body h4{margin:0.7em 0 0.3em;font-weight:650;line-height:1.35}" +
      "#dshMesMsgs .cd-result-body .md-code{display:block;margin:6px 0 10px;padding:10px 12px;border-radius:8px;background:#0f172a0d;border:1px solid #e5e7eb;font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre;overflow-x:auto;line-height:1.45}" +
      "#dshMesMsgs .cd-goal-banner{margin:0 12px 8px;padding:10px 12px;border-radius:8px;background:#eff6ff;border:1px solid #bfdbfe;font-size:12px;line-height:1.55}" +
      "#dshMesMsgs .cd-goal-banner strong{color:#1e40af;display:block;margin-bottom:4px;font-size:11px;text-transform:uppercase;letter-spacing:.04em}" +
      "#dshMesMsgs .cd-target-row{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}" +
      "#dshMesMsgs .cd-target-chip{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:999px;background:#f0fdf4;border:1px solid #bbf7d0;font-size:11px;color:#166534;font-weight:600}" +
      "#dshMesMsgs .cd-path-list{margin:0 12px 8px;padding:8px 10px;border-radius:8px;background:#f8fafc;border:1px solid #e2e8f0;font-size:11px;color:#64748b;line-height:1.5}" +
      "#dshMesMsgs .cd-path-list code{font-size:10px;color:#475569;background:transparent;padding:0}" +
      "#dshMesMsgs .cd-warn-box{margin:0 12px 8px;padding:8px 10px;border-radius:8px;background:#fffbeb;border:1px solid #fde68a;font-size:12px;color:#92400e;line-height:1.45}" +
      "#dshMesMsgs .cd-err-box{margin:0 12px 8px;padding:8px 10px;border-radius:8px;background:#fef2f2;border:1px solid #fecaca;font-size:12px;color:#991b1b;line-height:1.45}" +
      "#dshMesMsgs .cd-checklist{margin:0 12px 8px;padding:8px 10px;border-radius:8px;background:#fafafa;border:1px solid #e5e7eb;font-size:12px}" +
      "#dshMesMsgs .cd-checklist label{display:flex;align-items:flex-start;gap:8px;cursor:pointer;line-height:1.45}" +
      "#dshMesMsgs .cd-notes-required .cd-label::after{content:' *';color:#dc2626}" +
      "#dshMesChips{padding:0 16px 8px;display:flex;gap:6px;flex-wrap:wrap}" +
      "#dshMesChips button{font-size:11px;padding:4px 10px;border-radius:999px;border:1px solid #e5e7eb;background:#fff;color:#374151;cursor:pointer}" +
      "#dshMesChips button:hover{border-color:#4d6bfe;color:#4d6bfe}" +
      "#dshMesInput{display:flex;gap:8px;padding:10px 14px 14px;border-top:1px solid #eef0f3}" +
      "#dshMesInput input{flex:1;padding:9px 14px;border:1px solid #e5e7eb;border-radius:999px;font-size:13px;outline:none}" +
      "#dshMesInput input:focus{border-color:#4d6bfe}" +
      "#dshMesInput button{border:none;border-radius:999px;background:#4d6bfe;color:#fff;padding:9px 18px;font-size:13px;cursor:pointer}" +
      "#dshMesInput button:disabled{opacity:.5}";

    function esc(s) {
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
    function md(s) {
      var t = esc(s);
      var blocks = [];
      t = t.replace(/```([^\n`]*)\n?([\s\S]*?)```/g, function (_, _lang, code) {
        var i = blocks.length;
        blocks.push('<pre class="md-code"><code>' + String(code).replace(/\s+$/, "") + "</code></pre>");
        return "\u0000MDCODE" + i + "\u0000";
      });
      t = t.replace(/`([^`\n]+)`/g, '<code class="md-inline">$1</code>');
      t = t.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
      t = t.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
      t = t.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
      t = t.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");
      t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      t = t.replace(/^---\s*$/gm, '<hr class="md-hr">');
      t = t.replace(/\n/g, "<br>");
      t = t.replace(/(?:<br>)*(<(?:h[1-4]|pre|hr)\b[^>]*>)/gi, "$1");
      t = t.replace(/(<\/(?:h[1-4]|pre)>)(?:<br>)*/gi, "$1");
      t = t.replace(/(?:<br>)*(\u0000MDCODE\d+\u0000)/g, "$1");
      t = t.replace(/(\u0000MDCODE\d+\u0000)(?:<br>)*/g, "$1");
      t = t.replace(/(?:<br>){2,}/g, "<br>");
      t = t.replace(/\u0000MDCODE(\d+)\u0000/g, function (_, i) { return blocks[Number(i)] || ""; });
      return t;
    }
    /** 协议标记不得展示给用户（含流式未写完的 <<<… 碎片） */
    function stripMarks(s) {
      return String(s || "")
        .replace(/<<<\s*思考\s*>>>/g, "")
        .replace(/<<<\s*回答\s*>>>/g, "")
        .replace(/<<<[^>]*$/g, "");
    }
    /** 取事件正文：优先绝对 text，否则追加 delta（兼容 MES 一次性推送） */
    function eventText(ev, prev) {
      if (ev && ev.text != null) return stripMarks(ev.text);
      return stripMarks((prev || "") + (ev && ev.delta || ""));
    }
    function dataSourceLabel(ds) {
      if (ds === "mes") return "MES 实时";
      if (ds === "assistant") return "助手";
      if (ds === "pcb_expert") return "PCB 专家";
      if (ds === "code_dev") return "本机写码";
      if (ds === "code_review") return "本机审码";
      if (ds === "code_commit") return "人触发提交";
      return "演示数据";
    }
    function srcLabel(ev) {
      if (ev && ev.source === "llm") return "LLM";
      if (ev && ev.source === "offline") return "离线提示";
      if (ev && ev.source === "code_dev") return "写码顾问";
      if (ev && ev.source === "code_review") return "审码顾问";
      if (ev && ev.source === "code_commit") return "提交顾问";
      if (ev && ev.source === "disabled") return "已停用";
      return "规则引擎";
    }
    function formatChatMeta(ev) {
      var srcTxt = srcLabel(ev);
      var ds = dataSourceLabel(ev && ev.data_source);
      var metricMap = { options: "需求选项", propose: "写码确认", code_dev: "本机写码", code_review: "本机审码", code_commit: "人触发提交", need_path: "待填路径", pick: "选目录确认", confirm: "确认提交", done: "审码完成", run: "本机审码", disabled: "已停用" };
      var it = (ev && ev.intent) || {};
      var intentTxt = it.type === "code_review" ? "本机审码" : it.type === "code_commit" ? "人触发提交" : "本机写码";
      if (it.type === "code_dev" && it.metric) intentTxt = metricMap[it.metric] || String(it.metric);
      else if (it.type === "code_review" && it.metric) intentTxt = metricMap[it.metric] || "本机审码";
      else if (it.type === "code_commit" && it.metric) intentTxt = metricMap[it.metric] || "人触发提交";
      else if (it.type) intentTxt = metricMap[it.type] || String(it.type);
      return "来源：" + srcTxt + " · 数据源：" + ds + " · 意图：" + intentTxt;
    }
    var CODE_DEV_PIPELINE = [
      { id: "boot", title: "任务已排队" },
      { id: "sandbox-prep", title: "沙箱就绪" },
      { id: "dev", title: "Cursor 改码" },
      { id: "sync", title: "同步到本机" },
    ];
    var CODE_DEV_STEP_MAP = { "agent-loop": "dev", "cursor-local": "dev" };
    function initCodingSteps() {
      return CODE_DEV_PIPELINE.map(function (p) {
        return { id: p.id, title: p.title, state: p.id === "boot" ? "done" : "pending" };
      });
    }
    function pipelineIndex(id) {
      for (var i = 0; i < CODE_DEV_PIPELINE.length; i++) {
        if (CODE_DEV_PIPELINE[i].id === id) return i;
      }
      return CODE_DEV_PIPELINE.length + 99;
    }
    function normalizeCodeDevStepId(id) {
      return CODE_DEV_STEP_MAP[id] || id;
    }
    function markPriorStepsDone(list, id) {
      var pIdx = pipelineIndex(id);
      return list.map(function (s) {
        if (pipelineIndex(s.id) < pIdx && s.state !== "done" && s.state !== "error") {
          return Object.assign({}, s, { state: "done" });
        }
        return s;
      });
    }
    function sealCodingSteps(steps, asError) {
      return (steps || []).filter(function (s) {
        return s.id !== "status" && s.id !== "cursor-heartbeat";
      }).map(function (s) {
        if (asError) {
          if (s.state === "running" || s.state === "waiting") return Object.assign({}, s, { state: "error" });
          return s;
        }
        if (s.state !== "error") return Object.assign({}, s, { state: "done" });
        return s;
      });
    }
    function applyCodingStep(steps, event) {
      var rawId = event && event.id;
      if (!rawId || rawId === "status" || rawId === "cursor-heartbeat") return steps;
      var id = normalizeCodeDevStepId(rawId);
      var title = String(event.title || "").trim();
      var nextState = event.state || "running";
      var list = (steps && steps.length) ? steps.slice() : initCodingSteps();
      var idx = -1;
      for (var i = 0; i < list.length; i++) { if (list[i].id === id) { idx = i; break; } }
      if (idx < 0) return list;
      var cur = list[idx];
      var merged = Object.assign({}, cur, { state: nextState });
      if (title) merged.title = title;
      if (id === "dev") {
        if (rawId === "cursor-local" && nextState === "done") {
          merged.state = "running";
        } else if (rawId === "agent-loop" && nextState === "done") {
          merged.state = "done";
        } else if (nextState === "running") {
          merged.state = "running";
        }
      }
      list[idx] = merged;
      if (nextState === "running" || (id === "dev" && rawId === "agent-loop" && nextState === "done") || nextState === "done") {
        list = markPriorStepsDone(list, id);
      }
      if (id === "sync" && nextState === "running") {
        list = list.map(function (s) {
          return s.id === "dev" && s.state === "running" ? Object.assign({}, s, { state: "done" }) : s;
        });
      }
      return list;
    }
    function codingPlanSummary(steps) {
      var list = (steps || []).filter(function (s) { return s.state !== "pending"; });
      if (!list.length) return "准备中…";
      var total = list.length;
      var done = list.filter(function (s) { return s.state === "done"; }).length;
      if (list.some(function (s) { return s.state === "running"; })) return "正在进行 " + done + "/" + total;
      var err = list.filter(function (s) { return s.state === "error"; }).length;
      if (err) return "完成 " + done + "/" + total + "（" + err + " 步失败）";
      if (done === total) return "已全部完成（" + total + " 步）";
      return "共 " + total + " 步";
    }
    function renderCodingPlanHtml(steps, opts) {
      opts = opts || {};
      var visible = (steps || []).filter(function (s) { return s.state !== "pending"; });
      if (!visible.length) visible = [{ id: "boot", title: "任务已排队", state: "running" }];
      var summary = opts.summary || codingPlanSummary(visible);
      var running = visible.some(function (s) { return s.state === "running"; });
      var allDone = visible.length && visible.every(function (s) { return s.state === "done" || s.state === "error"; });
      var html = '<div class="coding-plan' + (running ? " is-running" : "") + (allDone && !running ? " is-done" : "") + '">';
      html += '<div class="cp-head"><span class="cp-badge">' + esc(opts.heading || "本轮进度") + "</span>";
      html += '<span class="cp-summary">' + esc(summary) + "</span>";
      if (opts.duration) html += '<span class="cp-duration">' + esc(opts.duration) + "</span>";
      html += '</div><ol class="cp-list">';
      visible.forEach(function (s, i) {
        var st = s.state || "pending";
        var icon = '<span class="cp-pending">' + (i + 1) + "</span>";
        if (st === "running") icon = '<span class="cp-spinner"></span>';
        else if (st === "done") icon = '<span class="cp-check">✓</span>';
        else if (st === "error") icon = '<span class="cp-fail">!</span>';
        var hint = st === "running" ? "进行中" : st === "done" ? "已完成" : st === "error" ? "失败" : "等待中";
        html += '<li class="cp-item is-' + st + '"><span class="cp-icon">' + icon + '</span><div class="cp-body"><span class="cp-title">' + esc(s.title) + '</span><span class="cp-state">' + hint + "</span></div></li>";
      });
      html += "</ol></div>";
      return html;
    }
    function extractCodeDevResultBody(reply) {
      var raw = String(reply || "").trim();
      if (!raw) return "";
      var m = raw.match(/(?:^|\n)(?:##\s*)?(?:改动说明|验收步骤|【同步】)/m);
      if (m && m.index >= 0) return raw.slice(m.index).replace(/^[\n\r]+/, "").trim();
      return raw.split("\n").filter(function (l) {
        return !/^任务\s+ldj-/.test(l.trim()) && !/^已同步\s+\d+/.test(l.trim());
      }).join("\n").trim() || raw;
    }
    function formatDuration(sec) {
      sec = Math.max(1, Math.round(sec || 0));
      return sec >= 60 ? Math.floor(sec / 60) + "m " + (sec % 60) + "s" : sec + "s";
    }
    function mountCodeDevUi(hostEl, ui, beforeMetaEl, hooks) {
      if (!hostEl || !ui || !ui.kind) return;
      var old = hostEl.querySelector(".cd-card:not(.cr-pick)");
      if (old) old.remove();
      var card = document.createElement("div");
      card.className = "cd-card";
      hooks = hooks || {};
      if (ui.kind === "options") renderCdOptions(card, ui, hooks.send);
      else if (ui.kind === "propose") renderCdPropose(card, ui, hooks);
      else return;
      if (beforeMetaEl) hostEl.insertBefore(card, beforeMetaEl);
      else hostEl.appendChild(card);
    }
    function mountCodeReviewUi(hostEl, ui, beforeMetaEl, hooks) {
      if (!hostEl || !ui || !ui.kind) return;
      var old = hostEl.querySelector(".cd-card.cr-pick");
      if (old) old.remove();
      var card = document.createElement("div");
      card.className = "cd-card cr-pick";
      hooks = hooks || {};
      if (ui.kind === "pick") renderCrPick(card, ui, hooks);
      else return;
      if (beforeMetaEl) hostEl.insertBefore(card, beforeMetaEl);
      else hostEl.appendChild(card);
    }
    function mountCodeCommitUi(hostEl, ui, beforeMetaEl, hooks) {
      if (!hostEl || !ui || !ui.kind) return;
      var old = hostEl.querySelector(".cd-card.cc-card");
      if (old) old.remove();
      var card = document.createElement("div");
      card.className = "cd-card cc-card";
      hooks = hooks || {};
      if (ui.kind === "pick") renderCcPick(card, ui, hooks);
      else if (ui.kind === "confirm") renderCcConfirm(card, ui, hooks);
      else if (ui.kind === "blocked") renderCcBlocked(card, ui, hooks);
      else return;
      if (beforeMetaEl) hostEl.insertBefore(card, beforeMetaEl);
      else hostEl.appendChild(card);
    }
    function mountCodeDeployUi(hostEl, ui, beforeMetaEl) {
      if (!hostEl || !ui || !ui.kind) return;
      var old = hostEl.querySelector(".cd-card.cdp-card");
      if (old) old.remove();
      var card = document.createElement("div");
      card.className = "cd-card cdp-card";
      if (ui.kind === "confirm") renderCdDeployConfirm(card, ui);
      else return;
      if (beforeMetaEl) hostEl.insertBefore(card, beforeMetaEl);
      else hostEl.appendChild(card);
    }
    function renderCdDeployConfirm(card, ui) {
      var fullUnits = Array.isArray(ui.units_full) ? ui.units_full : [];
      var incrUnits = Array.isArray(ui.units_incremental)
        ? ui.units_incremental
        : Array.isArray(ui.units)
          ? ui.units
          : [];
      var policy = ui.policy && typeof ui.policy === "object" ? ui.policy : {};
      // 多信号锁定：强制全量时绝不展示可改增量
      var forceFull = !!(
        ui.force_full ||
        policy.force_full ||
        ui.locked_mode === "full" ||
        (String(ui.summary || "").indexOf("强制全量") === 0)
      );
      var allowUpgrade =
        !forceFull &&
        (ui.allow_upgrade_to_full === true || ui.allow_mode_override === true);
      var mode = forceFull ? "full" : ui.mode === "full" ? "full" : "incremental";
      var reasons = Array.isArray(ui.reasons)
        ? ui.reasons
        : Array.isArray(policy.reasons)
          ? policy.reasons
          : [];
      var warnings = Array.isArray(ui.warnings)
        ? ui.warnings
        : Array.isArray(policy.warnings)
          ? policy.warnings
          : [];
      var changed = Array.isArray(ui.changed_paths) ? ui.changed_paths : [];

      function unitsFor(m) {
        return m === "full" ? fullUnits : incrUnits;
      }
      function paint() {
        if (forceFull) mode = "full";
        var units = unitsFor(mode);
        var badge = forceFull
          ? "强制全量"
          : mode === "full"
            ? "全量部署"
            : "增量部署";
        var goLabel = mode === "full" ? "确认全量部署" : "确认增量部署";
        var html =
          '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">' +
          badge +
          '</span><span class="cd-hint">' +
          esc(ui.hint || "二元判定：全量或增量；人只确认") +
          '</span></div><p class="cd-summary">' +
          esc(ui.summary || "") +
          '</p><p class="cd-desc">' +
          esc(ui.desc || "") +
          "</p></div>";
        if (reasons.length) {
          html +=
            '<div class="cd-label" style="padding:0 14px 4px">判定原因</div><ul style="margin:0 14px 8px;padding-left:18px;font-size:12px;color:#374151">';
          reasons.slice(0, 6).forEach(function (r) {
            html += "<li>" + esc(r) + "</li>";
          });
          html += "</ul>";
        }
        if (warnings.length) {
          html +=
            '<p class="cd-desc" style="padding:0 14px 8px;color:#b45309">' +
            esc(warnings.slice(0, 3).join("；")) +
            "</p>";
        }
        html += '<div class="cd-label" style="padding:0 14px 4px">部署方式</div>';
        if (forceFull) {
          html +=
            '<p class="cd-desc" style="padding:0 14px 8px"><strong>全量部署（已锁定）</strong>' +
            " — 触发全量条件，确认后同步全部单元，不可改增量。</p>";
        } else if (!allowUpgrade) {
          html +=
            '<p class="cd-desc" style="padding:0 14px 8px"><strong>' +
            (mode === "full" ? "全量部署" : "增量部署") +
            "</strong></p>";
        } else {
          html +=
            '<div style="padding:0 14px 8px;display:flex;gap:16px;flex-wrap:wrap">' +
            '<label style="font-size:13px"><input type="radio" name="cdp-mode-' +
            esc(ui.job_id || "x") +
            '" value="incremental"' +
            (mode === "incremental" ? " checked" : "") +
            "> 增量部署（默认）</label>" +
            '<label style="font-size:13px"><input type="radio" name="cdp-mode-' +
            esc(ui.job_id || "x") +
            '" value="full"' +
            (mode === "full" ? " checked" : "") +
            "> 升级为全量</label></div>" +
            '<p class="cd-desc" style="padding:0 14px 8px">增量只同步命中单元；升级全量将同步目录全部单元。</p>';
        }
        html +=
          '<div class="cd-chosen">' +
          '<div class="cd-chosen-row"><span class="cd-k">环境</span><span class="cd-v">' +
          esc(ui.env || "") +
          "</span></div>" +
          '<div class="cd-chosen-row"><span class="cd-k">主机</span><span class="cd-v">' +
          esc(ui.ssh_host || "") +
          "</span></div>" +
          '<div class="cd-chosen-row"><span class="cd-k">远端</span><span class="cd-v">' +
          esc(ui.ssh_app_path || "") +
          "</span></div>" +
          '<div class="cd-chosen-row"><span class="cd-k">对比</span><span class="cd-v">' +
          esc(
            (ui.last_deploy_sha ? String(ui.last_deploy_sha).slice(0, 10) : ui.base_ref || "?") +
              " → " +
              (ui.head_ref || "HEAD")
          ) +
          "</span></div></div>";
        if (changed.length && mode === "incremental") {
          html +=
            '<div class="cd-label" style="padding:0 14px">变更文件（节选）</div><div style="padding:4px 14px 8px;max-height:100px;overflow:auto;font-size:11px;color:#6b7280">';
          changed.slice(0, 20).forEach(function (p) {
            html += "<div>" + esc(p) + "</div>";
          });
          if (changed.length > 20) html += "<div>…共 " + changed.length + " 个</div>";
          html += "</div>";
        }
        if (mode === "full") {
          html +=
            '<div class="cd-label" style="padding:0 14px">将同步全部单元（' +
            units.length +
            "）</div>";
          html +=
            '<div class="cdp-units" style="padding:4px 14px 8px;max-height:160px;overflow:auto">';
          units.forEach(function (u) {
            html +=
              '<div style="font-size:12px;margin:3px 0"><b>' +
              esc(u.id || "") +
              "</b> · " +
              esc(u.label || "") +
              "</div>";
          });
          html += "</div>";
        } else {
          html += '<div class="cd-label" style="padding:0 14px">自动选中的增量单元</div>';
          if (!units.length) {
            html +=
              '<p class="cd-desc" style="padding:0 14px">无增量单元；确认不会 rsync</p>';
          } else {
            html += '<div class="cdp-units" style="padding:4px 14px 8px">';
            units.forEach(function (u) {
              html +=
                '<div style="font-size:12px;margin:4px 0"><b>' +
                esc(u.id || "") +
                "</b> · " +
                esc(u.label || "") +
                "<br><span class=\"cd-hint\">" +
                esc(u.action_hint || u.action || "") +
                "</span></div>";
            });
            html += "</div>";
          }
        }
        var canGo =
          ui.can_deploy !== false &&
          (mode === "full" ? fullUnits.length > 0 : units.length > 0);
        html +=
          '<p class="cd-error" style="display:none"></p><div class="cd-actions">' +
          '<button type="button" class="cd-btn cd-cancel">取消</button>' +
          '<button type="button" class="cd-btn confirm cd-go"' +
          (canGo ? "" : " disabled") +
          ">" +
          goLabel +
          "</button></div>";
        card.innerHTML = html;
        bind();
      }
      function bind() {
        var errEl = card.querySelector(".cd-error");
        var goBtn = card.querySelector(".cd-go");
        var radioName = "cdp-mode-" + (ui.job_id || "x");
        Array.prototype.forEach.call(
          card.querySelectorAll('input[name="' + radioName + '"]'),
          function (el) {
            el.onchange = function () {
              if (el.checked && allowUpgrade && !forceFull) {
                mode = el.value === "full" ? "full" : "incremental";
                paint();
              }
            };
          }
        );
        card.querySelector(".cd-cancel").onclick = async function () {
          try {
            await fetch(engineBase() + "/api/code-deploy/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ job_id: ui.job_id, decision: "reject" }),
            });
          } catch (_) {}
          card.className = "cd-card cdp-card done";
          card.innerHTML =
            '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">部署</span></div>' +
            '<p class="cd-summary">已取消，未执行同步</p></div>';
        };
        goBtn.onclick = async function () {
          var sendMode = forceFull ? "full" : mode;
          var ids =
            sendMode === "full"
              ? fullUnits.map(function (u) { return u.id; }).filter(Boolean)
              : incrUnits.map(function (u) { return u.id; }).filter(Boolean);
          if (!ids.length) {
            errEl.style.display = "";
            errEl.textContent =
              sendMode === "full" ? "全量目录为空" : "无增量单元可部署";
            return;
          }
          goBtn.disabled = true;
          goBtn.textContent = "部署中…";
          errEl.style.display = "none";
          try {
            var r = await fetch(engineBase() + "/api/code-deploy/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                job_id: ui.job_id,
                decision: "approve",
                mode: sendMode,
                unit_ids: ids,
              }),
            });
            var d = await r.json();
            var host = card.closest(".assist") || card.parentElement;
            var replyEl = host && host.querySelector(".reply");
            card.className = "cd-card cdp-card done";
            if (!d.ok) {
              card.innerHTML =
                '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">部署失败</span></div>' +
                '<p class="cd-summary">' +
                esc(d.detail || d.reply || "失败") +
                "</p></div>";
              if (replyEl) replyEl.innerHTML = md(d.reply || d.detail || "部署失败");
              return;
            }
            var doneMode = d.mode === "full" || sendMode === "full" ? "全量" : "增量";
            var succ = d.deploy_success || {};
            var unitList = Array.isArray(d.units)
              ? d.units
              : Array.isArray(succ.units)
                ? succ.units
                : ids;
            card.innerHTML = cdpSuccessCardHtml({
              title: succ.title || doneMode + "部署完成",
              mode: d.mode || sendMode,
              mode_label: succ.mode_label || doneMode,
              env: succ.env || d.env || ui.env || "",
              ssh_host: succ.ssh_host || d.ssh_host || ui.ssh_host || "",
              ssh_app_path: succ.ssh_app_path || d.ssh_app_path || ui.ssh_app_path || "",
              remote: succ.remote || "",
              access_url:
                succ.access_url ||
                d.access_url ||
                d.health_url ||
                ui.access_url ||
                ui.health_url ||
                "",
              units: unitList,
              engine_restart: !!(succ.engine_restart != null
                ? succ.engine_restart
                : (d.deploy_result && d.deploy_result.engine_restart)),
              bridge_restart: !!(succ.bridge_restart != null
                ? succ.bridge_restart
                : (d.deploy_result && d.deploy_result.bridge_restart)),
              remote_engine_port:
                succ.remote_engine_port ||
                (d.deploy_result && d.deploy_result.remote_engine_port) ||
                "",
              head_sha: succ.head_sha || d.head_sha || ui.head_sha || "",
              actions: succ.actions || [],
              health: succ.health || (d.deploy_result && d.deploy_result.health) || null,
              remote_receipt_path:
                succ.remote_receipt_path ||
                (d.deploy_result && d.deploy_result.remote_receipt_path) ||
                "",
              synced_rels: succ.synced_rels || [],
            });
            if (replyEl) {
              var unitTxt =
                unitList.slice(0, 4).join("、") + (unitList.length > 4 ? "…" : "");
              var healthObj =
                succ.health || (d.deploy_result && d.deploy_result.health) || null;
              var healthBit =
                healthObj && healthObj.ok
                  ? "探活通过"
                  : healthObj && healthObj.ok === false
                    ? "探活未通过"
                    : "探活未配置";
              var remoteTxt =
                succ.remote ||
                ((succ.ssh_host || d.ssh_host || ui.ssh_host || "") +
                  (succ.ssh_app_path || d.ssh_app_path || ui.ssh_app_path
                    ? ":" + (succ.ssh_app_path || d.ssh_app_path || ui.ssh_app_path)
                    : ""));
              replyEl.innerHTML = md(
                "**" +
                  (succ.title || doneMode + "部署完成") +
                  "** · `" +
                  (unitTxt || "—") +
                  "`\n- 环境：`" +
                  (succ.env || d.env || ui.env || "—") +
                  "` · " +
                  healthBit +
                  "\n- 远端：`" +
                  (remoteTxt || "—") +
                  "`"
              );
            }
          } catch (e) {
            errEl.style.display = "";
            errEl.textContent = "请求失败：" + e.message;
            goBtn.disabled = false;
            goBtn.textContent = sendMode === "full" ? "确认全量部署" : "确认增量部署";
          }
        };
      }
      paint();
    }
    function ccFindingsHtml(findings, limit) {
      var list = Array.isArray(findings) ? findings : [];
      if (!list.length) return '<p class="cd-desc">无 findings</p>';
      var html = '<ul class="cd-findings" style="margin:8px 0;padding-left:18px;font-size:13px;">';
      list.slice(0, limit || 12).forEach(function (f) {
        html +=
          "<li><b>[" +
          esc(f.severity || "?") +
          "]</b> " +
          esc(f.path || "") +
          " — " +
          esc(f.message || "") +
          "</li>";
      });
      html += "</ul>";
      return html;
    }
    function renderCcBlocked(card, ui, hooks) {
      hooks = hooks || {};
      var files = Array.isArray(ui.files) ? ui.files : [];
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">提交阻断</span><span class="cd-hint">请先修复</span></div>' +
        '<p class="cd-summary">' + esc(ui.summary || "门禁未通过，禁止提交") + "</p></div>";
      html += '<div class="cd-chosen"><div class="cd-chosen-row"><span class="cd-k">路径</span><span class="cd-v">' + esc(ui.workspace || "") + "</span></div>";
      if (ui.work_branch) {
        html += '<div class="cd-chosen-row"><span class="cd-k">分支</span><span class="cd-v">' + esc(ui.work_branch) + "</span></div>";
      }
      html += '<div class="cd-chosen-row"><span class="cd-k">阻断</span><span class="cd-v">' + esc(String(ui.blocking_count || 0)) + " 条</span></div></div>";
      if (files.length) {
        html += '<p class="cd-desc" style="padding:0 12px;">待提交文件 ' + files.length + " 个</p>";
      }
      html += '<div style="padding:0 12px 12px">' + ccFindingsHtml(ui.findings, 15) + "</div>";
      html +=
        '<div class="cd-done-banner err" style="margin:0 12px 8px"><span class="cd-done-icon">!</span><div><strong>不可提交</strong> · 可点下方用写码修复，或在输入框说「修复这些问题」</div></div>';
      html +=
        '<div class="cd-actions" style="padding:0 12px 12px">' +
        '<button type="button" class="cd-btn confirm cd-fix">用写码修复这些问题</button></div>';
      card.className = "cd-card cc-card done";
      card.innerHTML = html;
      var fixBtn = card.querySelector(".cd-fix");
      if (fixBtn) {
        fixBtn.onclick = function () {
          var msg = "【门禁阻断修复】请按提交门禁结果修复问题代码";
          if (ui.job_id) msg += " job_id=" + ui.job_id;
          if (ui.workspace) msg += "\n工程：" + ui.workspace;
          if (typeof hooks.send === "function") {
            hooks.send(msg);
            return;
          }
          fixBtn.disabled = true;
          fixBtn.textContent = "准备修复卡…";
          fetch(engineBase() + "/api/code-commit/prepare-fix", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ workspace: ui.workspace || "", job_id: ui.job_id || "" }),
          })
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (!d.ok || !d.code_dev_ui) {
                fixBtn.disabled = false;
                fixBtn.textContent = "用写码修复这些问题";
                alert(d.detail || d.reply || "无法生成修复确认卡");
                return;
              }
              renderCdPropose(card, d.code_dev_ui, hooks);
              var host = card.closest(".assist") || card.parentElement;
              var replyEl = host ? host.querySelector(".reply") : null;
              if (replyEl) replyEl.innerHTML = md(d.reply || "请确认后写码修复");
            })
            .catch(function (e) {
              fixBtn.disabled = false;
              fixBtn.textContent = "用写码修复这些问题";
              alert("请求失败：" + e.message);
            });
        };
      }
    }
    function renderCcPushRetryCard(card, d, hooks) {
      hooks = hooks || {};
      var cr = d.commit_result || {};
      var push = cr.push || {};
      var jobId = d.job_id || "";
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">推送失败</span>' +
        '<span class="cd-hint" style="color:#b91c1c">本地已提交，可重试推送</span></div>' +
        '<p class="cd-summary">' + esc(d.reply || d.detail || "本地已提交，但推送失败") + "</p></div>";
      html +=
        '<div class="cd-chosen">' +
        '<div class="cd-chosen-row"><span class="cd-k">分支</span><span class="cd-v">' + esc(cr.branch || "") + "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">本地 commit</span><span class="cd-v">' + esc(cr.commit || "") + "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">待推送</span><span class="cd-v">仅 push（不重新 commit）</span></div></div>';
      if (push.error || push.raw_error) {
        html +=
          '<p class="cd-desc" style="padding:0 12px;color:#991b1b"><code>' +
          esc(String(push.error || push.raw_error || "").slice(0, 280)) +
          "</code></p>";
      }
      html +=
        '<p class="cd-error" style="display:none"></p>' +
        '<div class="cd-actions" style="padding:0 12px 12px">' +
        '<button type="button" class="cd-btn confirm cd-push-retry">重试推送</button></div>';
      card.className = "cd-card cc-card";
      card.innerHTML = html;
      var errEl = card.querySelector(".cd-error");
      var btn = card.querySelector(".cd-push-retry");
      btn.onclick = function () {
        btn.disabled = true;
        btn.textContent = "推送中…";
        errEl.style.display = "none";
        fetch(engineBase() + "/api/code-commit/push-retry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jobId }),
        })
          .then(function (r) { return r.json(); })
          .then(function (out) {
            var host = card.closest(".assist") || card.parentElement;
            var replyEl = host ? host.querySelector(".reply") : null;
            if (!out.ok) {
              errEl.style.display = "";
              errEl.textContent = out.detail || out.reply || "重试推送失败";
              btn.disabled = false;
              btn.textContent = "重试推送";
              if (replyEl) replyEl.innerHTML = md(out.reply || out.detail || "重试推送失败");
              return;
            }
            var cr2 = out.commit_result || cr || {};
            var fileList =
              Array.isArray(cr2.files) && cr2.files.length
                ? cr2.files
                : Array.isArray(out.files)
                  ? out.files
                  : Array.isArray(d.files)
                    ? d.files
                    : [];
            var title = "已提交并推送";
            card.className = "cd-card cc-card done";
            card.innerHTML = ccSuccessCardHtml({
              title: title,
              workspace: out.workspace || d.workspace || "",
              branch: cr2.branch || cr.branch || "",
              commit: cr2.commit || cr.commit || "",
              remote: "已推送",
              files: fileList,
              message: out.message || cr2.message || d.message || "",
            });
            if (replyEl) {
              var proj =
                String(out.workspace || d.workspace || "")
                  .replace(/\\/g, "/")
                  .split("/")
                  .filter(Boolean)
                  .pop() || "—";
              replyEl.innerHTML = md(
                "**" +
                  title +
                  "** · `" +
                  (cr2.branch || cr.branch || "") +
                  "`\n- 项目：`" +
                  proj +
                  "`\n- 文件：" +
                  fileList.length +
                  " 个 · 已推送"
              );
            }
            if (typeof hooks.onCommitted === "function") hooks.onCommitted(out);
          })
          .catch(function (e) {
            errEl.style.display = "";
            errEl.textContent = "请求失败：" + e.message;
            btn.disabled = false;
            btn.textContent = "重试推送";
          });
      };
    }
    function ccSuccessCardHtml(info) {
      info = info || {};
      var ws = info.workspace || "";
      var proj = String(ws).replace(/\\/g, "/").replace(/\/+$/, "");
      var slash = proj.lastIndexOf("/");
      proj = slash >= 0 ? proj.slice(slash + 1) : proj || "—";
      var files = Array.isArray(info.files) ? info.files : [];
      var title = info.title || "已提交";
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">提交完成</span></div>' +
        '<p class="cd-summary">' +
        esc(title) +
        "</p></div>" +
        '<div class="cd-done-banner ok" style="margin:0 12px 8px"><span class="cd-done-icon">✓</span><div><strong>' +
        esc(title) +
        "</strong></div></div>" +
        '<div class="cd-chosen">' +
        '<div class="cd-chosen-row"><span class="cd-k">项目</span><span class="cd-v">' +
        esc(proj) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">路径</span><span class="cd-v">' +
        esc(ws) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">分支</span><span class="cd-v">' +
        esc(info.branch || "—") +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">Commit</span><span class="cd-v">' +
        esc(info.commit || "—") +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">远程</span><span class="cd-v">' +
        esc(info.remote || "—") +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">文件</span><span class="cd-v">' +
        files.length +
        " 个</span></div>";
      if (info.message) {
        html +=
          '<div class="cd-chosen-row"><span class="cd-k">说明</span><span class="cd-v">' +
          esc(info.message) +
          "</span></div>";
      }
      html += "</div>";
      if (files.length) {
        html += '<div class="cd-label" style="padding:0 12px 4px">本批文件</div><ul class="cc-ok-files">';
        for (var i = 0; i < Math.min(files.length, 30); i++) {
          html += "<li>" + esc(String(files[i])) + "</li>";
        }
        if (files.length > 30) html += "<li>…另有 " + (files.length - 30) + " 个</li>";
        html += "</ul>";
      }
      return html;
    }
    function cdpAccessLinkHtml(url) {
      var u = String(url || "").trim();
      if (!u) return esc("（未配置访问地址）");
      if (/^https?:\/\//i.test(u)) {
        return (
          '<a href="' +
          esc(u) +
          '" target="_blank" rel="noopener noreferrer" style="color:#047857;text-decoration:underline;word-break:break-all">' +
          esc(u) +
          "</a>"
        );
      }
      return esc(u);
    }
    function cdpSuccessCardHtml(info) {
      info = info || {};
      var units = Array.isArray(info.units) ? info.units : [];
      var rels = Array.isArray(info.synced_rels) ? info.synced_rels : [];
      var title = info.title || ((info.mode_label || "部署") + "完成");
      var modeLabel =
        info.mode_label || (info.mode === "full" ? "全量" : info.mode === "incremental" ? "增量" : "—");
      var remote =
        info.remote ||
        ((info.ssh_host || "") + (info.ssh_app_path ? ":" + info.ssh_app_path : ""));
      var access = info.access_url || info.health_url || "";
      var appName = String(info.ssh_app_path || remote || "")
        .replace(/\\/g, "/")
        .replace(/\/+$/, "");
      var slash = appName.lastIndexOf("/");
      appName = slash >= 0 ? appName.slice(slash + 1) : appName || "—";
      var actions = Array.isArray(info.actions) ? info.actions.slice() : [];
      if (!actions.length) {
        if (info.engine_restart) {
          actions.push(
            "已重启引擎" +
              (info.remote_engine_port ? "（:" + info.remote_engine_port + "）" : "")
          );
        }
        if (info.bridge_restart) actions.push("已重装 bridge");
        if (!actions.length) actions.push("仅同步文件（未重启 DSH）");
      }
      var health = info.health || null;
      var healthTxt = "—";
      if (health && health.ok != null) {
        healthTxt =
          (health.ok ? "通过" : "未通过") +
          (health.status != null ? "（" + health.status + "）" : "");
      }
      var unitShort = units.slice(0, 4).join("、") + (units.length > 4 ? "…" : "");
      var banner = title + (unitShort ? " · " + unitShort : "");
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">部署完成</span></div>' +
        '<p class="cd-summary">' +
        esc(title) +
        "</p></div>" +
        '<div class="cd-done-banner ok" style="margin:0 12px 8px"><span class="cd-done-icon">✓</span><div><strong>' +
        esc(banner) +
        "</strong></div></div>" +
        '<div class="cd-chosen">' +
        '<div class="cd-chosen-row"><span class="cd-k">项目</span><span class="cd-v">' +
        esc(appName) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">远端</span><span class="cd-v">' +
        esc(remote || "—") +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">环境</span><span class="cd-v">' +
        esc(info.env || "—") +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">方式</span><span class="cd-v">' +
        esc(modeLabel) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">访问</span><span class="cd-v">' +
        cdpAccessLinkHtml(access) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">探活</span><span class="cd-v">' +
        esc(healthTxt) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">动作</span><span class="cd-v">' +
        esc(actions.join("；")) +
        "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">单元</span><span class="cd-v">' +
        units.length +
        " 个</span></div>";
      if (info.head_sha) {
        html +=
          '<div class="cd-chosen-row"><span class="cd-k">基线</span><span class="cd-v">' +
          esc(String(info.head_sha).slice(0, 12)) +
          "</span></div>";
      }
      if (info.remote_receipt_path) {
        html +=
          '<div class="cd-chosen-row"><span class="cd-k">回执</span><span class="cd-v" style="word-break:break-all">' +
          esc(info.remote_receipt_path) +
          "</span></div>";
      }
      html += "</div>";
      if (units.length) {
        html +=
          '<div class="cd-label" style="padding:0 12px 4px">本批单元</div><ul class="cc-ok-files">';
        for (var i = 0; i < Math.min(units.length, 40); i++) {
          html += "<li>" + esc(String(units[i])) + "</li>";
        }
        if (units.length > 40) html += "<li>…另有 " + (units.length - 40) + " 个</li>";
        html += "</ul>";
      }
      if (rels.length) {
        html +=
          '<div class="cd-label" style="padding:0 12px 4px">同步路径</div><ul class="cc-ok-files">';
        for (var j = 0; j < Math.min(rels.length, 40); j++) {
          html += "<li>" + esc(String(rels[j])) + "</li>";
        }
        if (rels.length > 40) html += "<li>…另有 " + (rels.length - 40) + " 个</li>";
        html += "</ul>";
      }
      return html;
    }
    function renderCcConfirm(card, ui, hooks) {
      hooks = hooks || {};
      var files = Array.isArray(ui.files) ? ui.files : [];
      var pushOn = ui.push !== false;
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">确认提交</span><span class="cd-hint">' +
        esc(ui.hint || "确认后才会 git commit / push") +
        '</span></div><p class="cd-summary">' +
        esc(ui.summary || "门禁已通过") +
        '</p><p class="cd-desc">' +
        esc(ui.desc || "填写中文提交说明；默认推送到远程。") +
        "</p></div>";
      html +=
        '<div class="cd-chosen">' +
        '<div class="cd-chosen-row"><span class="cd-k">路径</span><span class="cd-v">' + esc(ui.workspace || "") + "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">分支</span><span class="cd-v">' + esc(ui.work_branch || "") + "</span></div>" +
        '<div class="cd-chosen-row"><span class="cd-k">文件</span><span class="cd-v">' + files.length + " 个</span></div></div>";
      if (files.length) {
        html += '<p class="cd-desc" style="padding:0 12px;"><code>' + esc(files.slice(0, 12).join(", ")) + (files.length > 12 ? "…" : "") + "</code></p>";
      }
      if ((ui.findings || []).length) {
        html += '<div style="padding:0 12px">' + ccFindingsHtml(ui.findings, 8) + "</div>";
      }
      html +=
        '<label class="cd-field"><span class="cd-label">中文提交说明</span>' +
        '<input class="cd-input cd-msg" value="' + esc(ui.message || "") + '" placeholder="概括本次修改"></label>';
      html +=
        '<label class="cd-field" style="flex-direction:row;align-items:center;gap:8px;">' +
        '<input type="checkbox" class="cd-push"' + (pushOn ? " checked" : "") + ">" +
        "<span>推送到远程</span></label>";
      html +=
        '<p class="cd-error" style="display:none"></p><div class="cd-actions">' +
        '<button type="button" class="cd-btn cd-cancel">取消</button>' +
        '<button type="button" class="cd-btn confirm cd-go">确认提交并推送</button></div>';
      card.innerHTML = html;
      var errEl = card.querySelector(".cd-error");
      var goBtn = card.querySelector(".cd-go");
      function syncGoLabel() {
        var push = card.querySelector(".cd-push").checked;
        goBtn.textContent = push ? "确认提交并推送" : "确认仅本地提交";
      }
      card.querySelector(".cd-push").onchange = syncGoLabel;
      syncGoLabel();
      card.querySelector(".cd-cancel").onclick = function () {
        fetch(engineBase() + "/api/code-commit/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: ui.job_id, decision: "reject" }),
        }).catch(function () {});
        card.className = "cd-card cc-card done";
        card.innerHTML =
          '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">提交代码</span></div>' +
          '<p class="cd-summary">已取消，未执行 commit</p></div>';
      };
      goBtn.onclick = function () {
        var message = (card.querySelector(".cd-msg").value || "").trim();
        var push = card.querySelector(".cd-push").checked;
        if (!message) {
          errEl.style.display = "";
          errEl.textContent = "请填写中文提交说明";
          return;
        }
        goBtn.disabled = true;
        goBtn.textContent = "提交中…";
        errEl.style.display = "none";
        fetch(engineBase() + "/api/code-commit/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: ui.job_id, message: message, push: push, decision: "approve" }),
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var host = card.closest(".assist") || card.parentElement;
            var replyEl = host ? host.querySelector(".reply") : null;
            if (d.push_retry_needed || (d.commit_result && d.commit_result.commit && d.commit_result.push && !d.commit_result.push.ok)) {
              renderCcPushRetryCard(card, d, hooks);
              if (replyEl) replyEl.innerHTML = md(d.reply || d.detail || "本地已提交，推送失败");
              return;
            }
            card.className = "cd-card cc-card done";
            if (!d.ok) {
              card.innerHTML =
                '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">提交失败</span></div>' +
                '<p class="cd-summary">' + esc(d.detail || d.reply || "失败") + "</p></div>";
              if (replyEl) replyEl.innerHTML = md(d.reply || d.detail || "提交失败");
              return;
            }
            var cr = d.commit_result || {};
            var remoteLabel = !push
              ? "仅本地提交"
              : cr.push && cr.push.ok
                ? "已推送"
                : "未推送";
            var title = push && cr.push && cr.push.ok ? "已提交并推送" : "已提交";
            card.innerHTML = ccSuccessCardHtml({
              title: title,
              workspace: ui.workspace || "",
              branch: cr.branch || ui.work_branch || "",
              commit: cr.commit || "",
              remote: remoteLabel,
              files: Array.isArray(cr.files) && cr.files.length ? cr.files : files,
              message: message,
            });
            if (replyEl) {
              replyEl.innerHTML = md(
                "**" +
                  title +
                  "** · `" +
                  (cr.branch || ui.work_branch || "") +
                  "`\n- 项目：`" +
                  String(ui.workspace || "")
                    .replace(/\\/g, "/")
                    .split("/")
                    .filter(Boolean)
                    .pop() +
                  "`\n- 文件：" +
                  (Array.isArray(cr.files) && cr.files.length ? cr.files.length : files.length) +
                  " 个 · " +
                  remoteLabel
              );
            }
            if (typeof hooks.onCommitted === "function") hooks.onCommitted(d);
          })
          .catch(function (e) {
            errEl.style.display = "";
            errEl.textContent = "请求失败：" + e.message;
            goBtn.disabled = false;
            syncGoLabel();
          });
      };
    }
    function renderCcPick(card, ui, hooks) {
      hooks = hooks || {};
      var ws0 = ui.workspace || "";
      var br0 = ui.work_branch || "";
      var brHint0 = ui.branch_hint || "";
      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">提交代码</span><span class="cd-hint">' +
        esc(ui.hint || "选择目录 · 开始门禁审核") +
        '</span></div><p class="cd-summary">' +
        esc(ui.summary || "请确认要提交的本机 Git 工程") +
        '</p><p class="cd-desc">' +
        esc(ui.desc || "") +
        "</p></div>";
      html +=
        '<label class="cd-field"><span class="cd-label">本机 Git 工程目录</span><div class="cd-path-row">' +
        '<input class="cd-input cd-ws" value="' + esc(ws0) + '" placeholder="/Users/你/项目" autocomplete="off">' +
        '<button type="button" class="cd-btn browse cd-browse">浏览…</button></div></label>';
      html +=
        '<label class="cd-field"><span class="cd-label">提交分支</span>' +
        '<input class="cd-input cd-branch" value="' + esc(br0) + '" placeholder="如 feature/xxx（当前分支 → 配置中心 → 手填）" autocomplete="off">' +
        '<p class="cd-desc cd-branch-hint" style="margin:4px 0 0;padding:0;">' + esc(brHint0) + "</p></label>";
      if (suggestions.length) {
        html += '<p class="cd-suggest">常用：';
        suggestions.forEach(function (s) {
          var p = typeof s === "string" ? s : (s && s.path) || "";
          var lab = (typeof s === "object" && s.label) ? s.label + " · " : "";
          if (!p) return;
          html += '<button type="button" class="cd-chip" data-path="' + esc(p) + '" title="' + esc(p) + '">' + esc(lab + p) + "</button>";
        });
        html += "</p>";
      }
      html +=
        '<p class="cd-error" style="display:none"></p><div class="cd-actions">' +
        '<button type="button" class="cd-btn cd-cancel">取消</button>' +
        '<button type="button" class="cd-btn confirm cd-go">开始门禁审核</button></div>';
      card.innerHTML = html;
      var errEl = card.querySelector(".cd-error");
      var wsEl = card.querySelector(".cd-ws");
      var brEl = card.querySelector(".cd-branch");
      var hintEl = card.querySelector(".cd-branch-hint");
      var refreshTimer = null;
      function applyBranchInfo(d) {
        if (!d) return;
        brEl.value = d.work_branch || "";
        hintEl.textContent = d.branch_hint || (d.need_user_branch ? "请填写要提交的分支" : "") || "";
      }
      function refreshBranch() {
        var workspace = (wsEl.value || "").trim();
        if (!workspace) {
          brEl.value = "";
          hintEl.textContent = "请先选择工程目录；分支将自动填入当前分支或配置中心分支。";
          return;
        }
        hintEl.textContent = "正在识别分支…";
        fetch(engineBase() + "/api/code-commit/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace: workspace }),
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d.ok) {
              brEl.value = "";
              hintEl.textContent = d.detail || d.reply || "路径不可用，无法识别分支";
              return;
            }
            applyBranchInfo(d);
          })
          .catch(function () {
            hintEl.textContent = "分支识别失败，请手动填写";
          });
      }
      function scheduleRefreshBranch() {
        if (refreshTimer) clearTimeout(refreshTimer);
        refreshTimer = setTimeout(refreshBranch, 350);
      }
      Array.prototype.forEach.call(card.querySelectorAll(".cd-chip"), function (btn) {
        btn.onclick = function () {
          wsEl.value = btn.getAttribute("data-path") || "";
          refreshBranch();
        };
      });
      wsEl.addEventListener("change", refreshBranch);
      wsEl.addEventListener("blur", refreshBranch);
      wsEl.addEventListener("input", scheduleRefreshBranch);
      card.querySelector(".cd-browse").onclick = function () {
        var browseBtn = card.querySelector(".cd-browse");
        browseBtn.disabled = true;
        browseBtn.textContent = "选择中…";
        errEl.style.display = "";
        errEl.textContent = "请在弹出的系统对话框中选择目录（若看不到，请看 Dock / 其它窗口后面）";
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = setTimeout(function () {
          try {
            if (ctrl) ctrl.abort();
          } catch (e0) {}
        }, 120000);
        fetch(engineBase() + "/api/pick-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: "选择要提交的 Git 工程目录" }),
          signal: ctrl ? ctrl.signal : undefined,
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            errEl.style.display = "none";
            if (d.ok && d.path) {
              wsEl.value = d.path;
              refreshBranch();
            } else if (d.error && d.error !== "已取消选择") {
              errEl.style.display = "";
              errEl.textContent = d.error || "选文件夹失败";
            } else {
              errEl.style.display = "none";
            }
          })
          .catch(function (e) {
            errEl.style.display = "";
            errEl.textContent =
              e && e.name === "AbortError"
                ? "选择超时：请点击「常用」路径或手动粘贴目录，也可再点「浏览…」"
                : "浏览失败：" + e.message;
          })
          .finally(function () {
            clearTimeout(timer);
            browseBtn.disabled = false;
            browseBtn.textContent = "浏览…";
          });
      };
      card.querySelector(".cd-cancel").onclick = function () {
        card.className = "cd-card cc-card done";
        card.innerHTML =
          '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">提交代码</span></div>' +
          '<p class="cd-summary">已取消，未开始门禁</p></div>';
      };
      card.querySelector(".cd-go").onclick = function () {
        var workspace = (wsEl.value || "").trim();
        var work_branch = (brEl.value || "").trim();
        if (!workspace) {
          errEl.style.display = "";
          errEl.textContent = "请填写或浏览选择本机 Git 工程目录";
          return;
        }
        if (!work_branch) {
          errEl.style.display = "";
          errEl.textContent = "请填写要提交的分支（当前分支与配置中心均不可用时须手填）";
          return;
        }
        var goBtn = card.querySelector(".cd-go");
        goBtn.disabled = true;
        goBtn.textContent = "门禁审核中…";
        errEl.style.display = "none";
        fetch(engineBase() + "/api/code-commit/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace: workspace, work_branch: work_branch }),
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d.ok && !d.job_id) {
              errEl.style.display = "";
              errEl.textContent = d.detail || d.reply || "门禁失败";
              goBtn.disabled = false;
              goBtn.textContent = "开始门禁审核";
              if (d.need_user_branch) {
                hintEl.textContent = d.branch_hint || d.detail || "请填写要提交的分支";
              }
              return;
            }
            var host = card.closest(".assist") || card.parentElement;
            var replyEl = host ? host.querySelector(".reply") : null;
            if (!d.can_commit) {
              var blockN = d.blocking_count || 0;
              var warnN = d.warning_count || 0;
              var blockedSummary =
                blockN > 0
                  ? ("提交批审：" + blockN + " 条阻断、" + warnN + " 条警告 —— 禁止提交")
                  : (d.summary || d.reply || "门禁未通过，禁止提交");
              renderCcBlocked(card, {
                kind: "blocked",
                workspace: workspace,
                job_id: d.job_id,
                files: d.files || [],
                findings: d.findings || [],
                summary: blockedSummary,
                blocking_count: blockN,
                work_branch: d.work_branch || work_branch,
              }, hooks);
              if (replyEl) replyEl.innerHTML = md(d.reply || blockedSummary);
              return;
            }
            var confirmUi = d.code_commit_ui || {
              kind: "confirm",
              job_id: d.job_id,
              workspace: workspace,
              files: d.files || [],
              work_branch: d.work_branch || work_branch,
              message: d.draft_message || "",
              push: d.default_push !== false,
              findings: d.findings || [],
              summary: d.summary || "",
            };
            renderCcConfirm(card, confirmUi, hooks);
            if (replyEl) replyEl.innerHTML = md(d.reply || "门禁通过，请确认后提交。");
          })
          .catch(function (e) {
            errEl.style.display = "";
            errEl.textContent = "请求失败：" + e.message;
            goBtn.disabled = false;
            goBtn.textContent = "开始门禁审核";
          });
      };
    }
    function renderCrPick(card, ui, hooks) {
      hooks = hooks || {};
      var ws0 = ui.workspace || "";
      var scope0 = ui.scope || "";
      var focus0 = ui.focus || "";
      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">代码审核</span><span class="cd-hint">' +
        esc(ui.hint || "选择目录 · 确认后开始") +
        '</span></div><p class="cd-summary">' +
        esc(ui.summary || "请确认要审核的本机工程") +
        '</p><p class="cd-desc">' +
        esc(ui.desc || "直读本机磁盘源码（不走 Git / VS Code Bridge），确认后开始审查。") +
        "</p></div>";
      html +=
        '<label class="cd-field"><span class="cd-label">本机工程目录</span><div class="cd-path-row">' +
        '<input class="cd-input cd-ws" value="' + esc(ws0) + '" placeholder="/Users/你/项目" autocomplete="off">' +
        '<button type="button" class="cd-btn browse cd-browse">浏览…</button></div></label>';
      if (suggestions.length) {
        html += '<p class="cd-suggest">常用：';
        suggestions.forEach(function (s) {
          var p = typeof s === "string" ? s : (s && s.path) || "";
          var lab = (typeof s === "object" && s.label) ? s.label + " · " : "";
          if (!p) return;
          html += '<button type="button" class="cd-chip" data-path="' + esc(p) + '" title="' + esc(p) + '">' + esc(lab + p) + "</button>";
        });
        html += "</p>";
      }
      html +=
        '<label class="cd-field"><span class="cd-label">范围（可选，相对子路径）</span>' +
        '<input class="cd-input cd-scope" value="' + esc(scope0) + '" placeholder="如 frontend/src"></label>';
      html +=
        '<label class="cd-field"><span class="cd-label">审查重点（可选）</span>' +
        '<input class="cd-input cd-focus" value="' + esc(focus0) + '" placeholder="如 SQL 注入、权限校验"></label>';
      html +=
        '<p class="cd-error" style="display:none"></p><div class="cd-actions">' +
        '<button type="button" class="cd-btn cd-cancel">取消</button>' +
        '<button type="button" class="cd-btn confirm cd-go">开始审核</button></div>';
      card.innerHTML = html;
      var errEl = card.querySelector(".cd-error");
      var wsEl = card.querySelector(".cd-ws");
      var goBtn = card.querySelector(".cd-go");
      Array.prototype.forEach.call(card.querySelectorAll(".cd-chip"), function (btn) {
        btn.onclick = function () { wsEl.value = btn.getAttribute("data-path") || ""; };
      });
      card.querySelector(".cd-browse").onclick = function () {
        var browseBtn = card.querySelector(".cd-browse");
        browseBtn.disabled = true;
        browseBtn.textContent = "选择中…";
        errEl.style.display = "";
        errEl.textContent = "请在弹出的系统对话框中选择目录（若看不到，请看 Dock / 其它窗口后面）";
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = setTimeout(function () {
          try {
            if (ctrl) ctrl.abort();
          } catch (e0) {}
        }, 120000);
        fetch(engineBase() + "/api/pick-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: "选择要审核的工程目录" }),
          signal: ctrl ? ctrl.signal : undefined,
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            errEl.style.display = "none";
            if (d.ok && d.path) wsEl.value = d.path;
            else if (d.error && d.error !== "已取消选择") {
              errEl.style.display = "";
              errEl.textContent = d.error || "选文件夹失败";
            } else {
              errEl.style.display = "none";
            }
          })
          .catch(function (e) {
            errEl.style.display = "";
            errEl.textContent =
              e && e.name === "AbortError"
                ? "选择超时：请点击「常用」路径或手动粘贴目录，也可再点「浏览…」"
                : "浏览失败：" + e.message;
          })
          .finally(function () {
            clearTimeout(timer);
            browseBtn.disabled = false;
            browseBtn.textContent = "浏览…";
          });
      };
      card.querySelector(".cd-cancel").onclick = function () {
        card.className = "cd-card cr-pick done";
        card.innerHTML =
          '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">代码审核</span></div>' +
          '<p class="cd-summary">已取消，未开始审核</p></div>';
      };
      goBtn.onclick = function () {
        var local_path = (wsEl.value || "").trim();
        var scope = (card.querySelector(".cd-scope").value || "").trim();
        var focus = (card.querySelector(".cd-focus").value || "").trim();
        if (!local_path) {
          errEl.style.display = "";
          errEl.textContent = "请填写或浏览选择本机工程目录";
          return;
        }
        var parts = local_path.split(/[/\\]/).filter(Boolean);
        var name = parts.length ? parts[parts.length - 1] : local_path;
        card.className = "cd-card cr-pick done";
        card.innerHTML =
          '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">代码审核</span><span class="cd-hint">进行中</span></div>' +
          '<p class="cd-summary">已确认本机工程，正在审核</p></div>' +
          '<div class="cd-chosen">' +
          '<div class="cd-chosen-row"><span class="cd-k">来源</span><span class="cd-v">本机目录直读</span></div>' +
          '<div class="cd-chosen-row"><span class="cd-k">项目</span><span class="cd-v">' + esc(name) + "</span></div>" +
          '<div class="cd-chosen-row"><span class="cd-k">路径</span><span class="cd-v">' + esc(local_path) + "</span></div></div>" +
          '<div class="cd-plan-host" style="padding:0 12px 8px"></div>' +
          '<div class="cd-done-banner" style="display:none;margin:0 12px 10px"></div>';
        var host = card.closest(".assist") || card.parentElement;
        if (host) {
          var replyEl = host.querySelector(".reply");
          if (replyEl && replyEl.nextElementSibling === card) host.insertBefore(card, replyEl);
          if (replyEl) replyEl.innerHTML = md("正在审核本机工程 `" + local_path + "` …");
          var metaEl0 = host.querySelector(".meta");
          if (metaEl0) metaEl0.textContent = "来源：审码顾问 · 数据源：本机审码 · 意图：审码进行中";
        }
        startCodeReviewWatch(local_path, scope, focus, {
          planHost: card.querySelector(".cd-plan-host"),
          bannerEl: card.querySelector(".cd-done-banner"),
          metaEl: host ? host.querySelector(".meta") : null,
          replyEl: host ? host.querySelector(".reply") : null,
        });
      };
    }
    var CR_PIPELINE = [
      { id: "validate", title: "校验工程路径" },
      { id: "list", title: "筛选功能源码" },
      { id: "read", title: "读取源码" },
      { id: "llm", title: "Viprasol Skill 审查" },
      { id: "report", title: "汇总审核报告" },
    ];
    function initCrSteps() {
      return CR_PIPELINE.map(function (p) { return { id: p.id, title: p.title, state: "pending" }; });
    }
    function applyCrStep(steps, event) {
      var id = event && event.id;
      if (!id) return steps;
      var list = (steps && steps.length) ? steps.slice() : initCrSteps();
      var idx = -1;
      for (var i = 0; i < list.length; i++) { if (list[i].id === id) { idx = i; break; } }
      if (idx < 0) return list;
      var nextState = event.state || "running";
      var title = String(event.title || "").trim();
      var merged = Object.assign({}, list[idx], { state: nextState });
      if (title) merged.title = title;
      list[idx] = merged;
      if (nextState === "running" || nextState === "done") {
        for (var j = 0; j < idx; j++) {
          if (list[j].state !== "done" && list[j].state !== "error") {
            list[j] = Object.assign({}, list[j], { state: "done" });
          }
        }
      }
      return list;
    }
    function startCodeReviewWatch(local_path, scope, focus, hosts) {
      hosts = hosts || {};
      var planHost = hosts.planHost;
      var bannerEl = hosts.bannerEl;
      var metaEl = hosts.metaEl;
      var replyEl = hosts.replyEl;
      var msgs = document.getElementById("dshMesMsgs");
      if (!planHost || !replyEl) {
        if (!msgs) return;
        var wrap = document.createElement("div");
        wrap.className = "assist cr-job-msg";
        wrap.innerHTML =
          '<div class="reply"></div>' +
          '<div class="cd-job-shell">' +
          '  <div class="cd-plan-host"></div>' +
          '  <div class="cd-done-banner" style="display:none"></div>' +
          "</div>" +
          '<div class="meta">来源：审码顾问 · 数据源：本机审码 · 意图：审码进行中</div>';
        msgs.appendChild(wrap);
        if (!planHost) planHost = wrap.querySelector(".cd-plan-host");
        if (!bannerEl) bannerEl = wrap.querySelector(".cd-done-banner");
        if (!replyEl) replyEl = wrap.querySelector(".reply");
        if (!metaEl) metaEl = wrap.querySelector(".meta");
      }
      var startedAt = Date.now();
      var steps = initCrSteps();
      steps[0] = Object.assign({}, steps[0], { state: "running" });
      var finished = false;
      var durationText = "0s";
      var streamedText = "";
      var tokenQueue = [];
      var tokenDraining = false;
      var pendingDoneEv = null;
      function paintPlan() {
        planHost.innerHTML = renderCodingPlanHtml(steps, { heading: "审码进度", duration: durationText, summary: "进行中…" });
      }
      function paintReport(text) {
        if (!replyEl) return;
        replyEl.innerHTML = md(stripMarks(text || ""));
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
      }
      function sleepMs(ms) {
        return new Promise(function (r) { setTimeout(r, ms); });
      }
      function finish(ev) {
        if (finished) return;
        if (tokenQueue.length || tokenDraining) {
          pendingDoneEv = ev;
          drainTokens();
          return;
        }
        finished = true;
        clearInterval(durTimer);
        durationText = formatDuration((Date.now() - startedAt) / 1000);
        var ok = !!(ev && ev.ok);
        steps = (steps || []).map(function (s) {
          if (s.state === "running" || s.state === "waiting") return Object.assign({}, s, { state: ok ? "done" : "error" });
          if (ok && s.state !== "error") return Object.assign({}, s, { state: "done" });
          return s;
        });
        paintPlan();
        var reply = (ev && ev.reply) || streamedText || (ok ? "审查完成。" : ((ev && ev.detail) || "审核失败"));
        streamedText = reply;
        if (bannerEl) {
          bannerEl.style.display = "";
          bannerEl.className = "cd-done-banner " + (ok ? "ok" : "err");
          var n = (ev && ev.file_count) || ((ev && ev.files_reviewed) || []).length || 0;
          bannerEl.innerHTML =
            '<span class="cd-done-icon">' + (ok ? "✓" : "!") + "</span>" +
            "<div><strong>" + (ok ? "审核报告已生成" : "审核未完成") + "</strong> · 用时 " + esc(durationText) +
            (ok ? " · 已审 " + n + " 个文件" : " · " + esc((ev && ev.detail) || "")) +
            (ev && ev.report_id ? '<div class="cd-synced">报告 ID：' + esc(ev.report_id) + "</div>" : "") +
            "</div>";
        }
        paintReport(reply);
        if (metaEl) metaEl.textContent = "来源：审码顾问 · 数据源：本机审码 · 意图：审码完成" + (ev && ev.report_id ? " · " + ev.report_id : "");
      }
      function drainTokens() {
        if (tokenDraining) return;
        tokenDraining = true;
        (async function () {
          while (tokenQueue.length) {
            var ev = tokenQueue.shift();
            var text = ev && ev.text != null ? ev.text : (streamedText + ((ev && ev.delta) || ""));
            streamedText = text;
            paintReport(text);
            await sleepMs(28);
          }
          tokenDraining = false;
          if (pendingDoneEv && !finished) {
            var doneEv = pendingDoneEv;
            pendingDoneEv = null;
            finish(doneEv);
          }
        })();
      }
      paintPlan();
      var durTimer = setInterval(function () {
        if (finished) { clearInterval(durTimer); return; }
        durationText = formatDuration((Date.now() - startedAt) / 1000);
        paintPlan();
      }, 1000);
      fetch(engineBase() + "/api/code-review/run/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ local_path: local_path, scope: scope || "", focus: focus || "" }),
      })
        .then(function (r) {
          if (!r.ok) {
            return r.json().catch(function () { return {}; }).then(function (j) {
              finish({ ok: false, detail: (j && (j.detail || j.reply)) || ("HTTP " + r.status), reply: (j && j.reply) || "" });
            });
          }
          var reader = r.body.getReader();
          var decoder = new TextDecoder();
          var pending = "";
          function pump() {
            return reader.read().then(function (res) {
              if (res.done) {
                if (!finished) {
                  if (pendingDoneEv) drainTokens();
                  else finish({ ok: false, detail: "流式结束但未收到完成事件", reply: "审码流中断，请重试" });
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
                  var ev;
                  try { ev = JSON.parse(raw); } catch (e) { return; }
                  if (ev.type === "step") {
                    steps = applyCrStep(steps, ev);
                    paintPlan();
                  } else if (ev.type === "status" && ev.detail) {
                    for (var i = 0; i < steps.length; i++) {
                      if (steps[i].state === "running") {
                        steps[i] = Object.assign({}, steps[i], { title: ev.detail });
                        break;
                      }
                    }
                    paintPlan();
                    if (!streamedText || streamedText.indexOf("代码审核汇总报告") !== 0) {
                      paintReport(
                        "⏳ **审码进行中**（尚未生成正式报告）\n\n" + ev.detail
                      );
                    }
                  } else if (ev.type === "token") {
                    tokenQueue.push(ev);
                    drainTokens();
                  } else if (ev.type === "done") {
                    pendingDoneEv = ev;
                    drainTokens();
                  }
                });
              });
              return pump();
            });
          }
          return pump();
        })
        .catch(function (e) {
          finish({ ok: false, detail: e.message, reply: "请求失败：" + e.message });
        });
    }
    function parseCodeDevUiFromText(text, fallbackWs) {
      var s = String(text || "");
      function tryJson(body) {
        try {
          var o = JSON.parse(body);
          return o && typeof o === "object" ? o : null;
        } catch (e) {
          var a = body.indexOf("{"), b = body.lastIndexOf("}");
          if (a >= 0 && b > a) {
            try { return JSON.parse(body.slice(a, b + 1)); } catch (e2) { return null; }
          }
          return null;
        }
      }
      var mOpt = s.match(/:::cursor_dev_options\b([\s\S]*?)(?:\n[ \t]*:::|$)/i);
      if (mOpt) {
        var options = tryJson(mOpt[1].trim());
        if (options) return { kind: "options", workspace: fallbackWs || "", options: options };
      }
      var mProp = s.match(/:::cursor_dev_propose\b([\s\S]*?)(?:\n[ \t]*:::|$)/i);
      if (mProp) {
        var prop = tryJson(mProp[1].trim()) || {};
        return {
          kind: "propose",
          workspace: String(prop.workspace || fallbackWs || "").trim(),
          requirement: String(prop.requirement || "").trim(),
          target: String(prop.target || "local"),
          propose: prop,
        };
      }
      return null;
    }
    function renderCdOptions(card, ui, sendFn) {
      var opts = ui.options || {};
      var groups = Array.isArray(opts.groups) ? opts.groups : [];
      var selected = {};
      groups.forEach(function (g) { selected[g.id] = []; });
      var html = '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">需求选项</span><span class="cd-hint">勾选即可 · 少打字</span></div>';
      html += '<p class="cd-summary">' + esc(opts.title || "请确认以下关键项") + "</p>";
      if (opts.summary) html += '<p class="cd-desc">' + esc(opts.summary) + "</p>";
      if (ui.original_goal || (ui.brief && ui.brief.original_goal)) {
        html += '<div class="cd-goal-banner"><strong>原始诉求</strong>' + esc(ui.original_goal || ui.brief.original_goal) + "</div>";
      }
      html += "</div>";
      groups.forEach(function (g) {
        html += '<div class="cd-group" data-gid="' + esc(g.id) + '"><div class="cd-group-label">' + esc(g.label || g.id);
        if (g.required !== false) html += '<span class="cd-req">必选</span>';
        html += '<span class="cd-mode">' + (g.multi ? "可多选" : "单选") + '</span></div><div class="cd-opts">';
        (g.options || []).forEach(function (o) {
          var typ = g.multi ? "checkbox" : "radio";
          html += '<label class="cd-opt"><input type="' + typ + '" name="cd-' + esc(g.id) + '" value="' + esc(o.id) + '"><span>' + esc(o.label || o.id) + "</span></label>";
        });
        html += "</div></div>";
      });
      html += '<label class="cd-field' + (opts.notes_required ? " cd-notes-required" : "") + '"><span class="cd-label">备注' +
        (opts.notes_required ? "（必填）" : "（可选）") + '</span><textarea class="cd-input cd-textarea cd-notes" rows="3" placeholder="' +
        esc(opts.notes_placeholder || "补充约束、验收点…") + '"></textarea></label>';
      html += '<p class="cd-error" style="display:none"></p>';
      html += '<div class="cd-actions"><button type="button" class="cd-btn cd-skip">跳过本卡</button><button type="button" class="cd-btn confirm cd-ok">确认选项</button></div>';
      card.innerHTML = html;
      Array.prototype.forEach.call(card.querySelectorAll(".cd-opt input"), function (inp) {
        inp.addEventListener("change", function () {
          var gEl = inp.closest(".cd-group");
          var gid = gEl.getAttribute("data-gid");
          var g = groups.find(function (x) { return x.id === gid; });
          if (!g) return;
          if (g.multi) {
            selected[gid] = Array.prototype.map.call(gEl.querySelectorAll("input:checked"), function (x) { return x.value; });
          } else {
            selected[gid] = inp.checked ? [inp.value] : [];
          }
          Array.prototype.forEach.call(gEl.querySelectorAll(".cd-opt"), function (lab) {
            lab.classList.toggle("on", !!lab.querySelector("input:checked"));
          });
        });
      });
      var errEl = card.querySelector(".cd-error");
      card.querySelector(".cd-skip").onclick = function () {
        card.className = "cd-card done";
        card.innerHTML = '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">需求选项</span></div><p class="cd-summary">已跳过本卡，可继续文字补充</p></div>';
      };
      card.querySelector(".cd-ok").onclick = function () {
        for (var i = 0; i < groups.length; i++) {
          var g = groups[i];
          if (g.required === false) continue;
          if (!(selected[g.id] || []).length) {
            errEl.style.display = "";
            errEl.textContent = "请先选择：「" + (g.label || g.id) + "」";
            return;
          }
        }
        errEl.style.display = "none";
        var notes = (card.querySelector(".cd-notes").value || "").trim();
        if (opts.notes_required && !notes) {
          errEl.style.display = "";
          errEl.textContent = "请填写备注：业务模块、页面名称、接口路径等（必填）";
          return;
        }
        var lines = ["【写码需求选项已确认】"];
        if (ui.workspace) lines.push("工程路径：" + ui.workspace);
        groups.forEach(function (g) {
          var ids = selected[g.id] || [];
          var labels = (g.options || []).filter(function (o) { return ids.indexOf(o.id) >= 0; }).map(function (o) { return o.label || o.id; });
          if (labels.length) lines.push((g.label || g.id) + "：" + labels.join("、"));
        });
        if (notes) lines.push("备注：" + notes);
        card.className = "cd-card done";
        Array.prototype.forEach.call(card.querySelectorAll("input,textarea,button"), function (el) { el.disabled = true; });
        if (sendFn) sendFn(lines.join("\n"));
      };
    }
    function renderCdPropose(card, ui, hooks) {
      hooks = hooks || {};
      var ws0 = ui.workspace || "";
      var req0 = ui.requirement || (ui.propose && ui.propose.requirement) || "";
      var goal = ui.original_goal || (ui.brief && ui.brief.original_goal) || (ui.propose && ui.propose.original_goal) || "";
      var mod = (ui.target_hints && ui.target_hints.module) || (ui.propose && ui.propose.target_module) || "";
      var paths = (ui.target_hints && ui.target_hints.expected_paths) || (ui.propose && ui.propose.expected_paths) || [];
      var val = ui.validation || {};
      var html =
        '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">写码确认</span><span class="cd-hint">核对后再开工</span></div>' +
        '<p class="cd-summary">请确认原始诉求、目标模块与需求摘要</p></div>';
      if (goal) {
        html += '<div class="cd-goal-banner"><strong>原始诉求</strong>' + esc(goal) + "</div>";
      }
      if (mod) {
        html += '<div class="cd-target-row"><span class="cd-target-chip">🎯 目标模块：' + esc(mod) + "</span></div>";
      }
      if (paths && paths.length) {
        html += '<div class="cd-path-list"><div>预期改动区域：</div>' +
          paths.slice(0, 6).map(function (p) { return "<code>" + esc(p) + "</code>"; }).join(" · ") + "</div>";
      }
      if (val.errors && val.errors.length) {
        html += '<div class="cd-err-box">' + val.errors.map(esc).join("<br>") + "</div>";
      } else if (val.warnings && val.warnings.length) {
        html += '<div class="cd-warn-box">' + val.warnings.map(esc).join("<br>") + "</div>";
      }
      html +=
        '<label class="cd-field"><span class="cd-label">本机工程绝对路径</span><input class="cd-input cd-ws" value="' + esc(ws0) + '"></label>' +
        '<label class="cd-field"><span class="cd-label">需求摘要（可编辑，须含原始业务名称）</span><textarea class="cd-input cd-textarea cd-req" rows="8">' + esc(req0) + "</textarea></label>";
      if (val.warnings && val.warnings.length && !(val.errors && val.errors.length)) {
        html += '<div class="cd-checklist"><label><input type="checkbox" class="cd-ack"><span>我已核对原始诉求与目标模块，确认摘要不偏离业务目标</span></label></div>';
      }
      html += '<p class="cd-error" style="display:none"></p>' +
        '<div class="cd-actions"><button type="button" class="cd-btn cd-cancel">取消</button>' +
        '<button type="button" class="cd-btn confirm cd-go">确认并用 Cursor 写入本机</button></div>';
      card.innerHTML = html;
      var errEl = card.querySelector(".cd-error");
      var ackEl = card.querySelector(".cd-ack");
      var goBtn = card.querySelector(".cd-go");
      if (val.errors && val.errors.length) goBtn.disabled = true;
      card.querySelector(".cd-cancel").onclick = function () {
        card.className = "cd-card done";
        card.innerHTML = '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">写码确认</span></div><p class="cd-summary">已取消，未启动写码</p></div>';
      };
      goBtn.onclick = function () {
        var workspace = (card.querySelector(".cd-ws").value || "").trim();
        var requirement = (card.querySelector(".cd-req").value || "").trim();
        if (!workspace || !requirement) {
          errEl.style.display = "";
          errEl.textContent = "请填写工程路径与需求摘要";
          return;
        }
        if (ackEl && !ackEl.checked) {
          errEl.style.display = "";
          errEl.textContent = "请先勾选确认：摘要与原始诉求一致";
          return;
        }
        var btn = goBtn;
        btn.disabled = true;
        btn.textContent = "启动中…";
        errEl.style.display = "none";
        var briefPayload = (typeof hooks.getBrief === "function" ? hooks.getBrief() : null) || ui.brief || null;
        var payload = {
          workspace: workspace,
          requirement: requirement,
          code_dev_brief: briefPayload,
        };
        if (ui.write_scope && ui.write_scope.length) payload.write_scope = ui.write_scope;
        if (ui.source_gate_job_id) payload.source_gate_job_id = ui.source_gate_job_id;
        fetch(engineBase() + "/api/code-dev/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d.ok) {
              errEl.style.display = "";
              errEl.textContent = d.detail || d.reply || "启动失败";
              btn.disabled = false;
              btn.textContent = "确认并用 Cursor 写入本机";
              return;
            }
            card.className = "cd-card done";
            card.innerHTML =
              '<div class="cd-head"><div class="cd-title-row"><span class="cd-badge">写码确认</span></div><p class="cd-summary">已启动</p></div>' +
              '<div class="cd-chosen"><div class="cd-chosen-row"><span class="cd-k">任务</span><span class="cd-v">' + esc(d.job_id || "") +
              '</span></div><div class="cd-chosen-row"><span class="cd-k">工程</span><span class="cd-v">' + esc(workspace) + "</span></div></div>";
            if (typeof hooks.onStarted === "function") hooks.onStarted(d);
            else startCodeDevJobWatch(d.job_id, d.reply || ("已启动 " + (d.job_id || "")), {
              workspace: workspace,
              resumeCommit: !!(d.resume_commit || d.from_gate_fix || ui.source_gate_job_id || (ui.write_scope && ui.write_scope.length)),
            });
          })
          .catch(function (e) {
            errEl.style.display = "";
            errEl.textContent = "请求失败：" + e.message;
            btn.disabled = false;
            btn.textContent = "确认并用 Cursor 写入本机";
          });
      };
    }

    function buildPanel() {
      var root = document.createElement("div");
      root.id = "dshMesPanelRoot";
      root.innerHTML =
        '<button id="dshMesToggle" title="ZR-WorkBuddy">📊</button>' +
        '<div id="dshMesPanel">' +
        '  <div id="dshMesHead"><span class="dot" id="dshMesDot"></span>ZR-WorkBuddy' +
        '    <button class="close" id="dshMesClose">×</button></div>' +
        '  <div id="dshMesMsgs"></div>' +
        '  <div id="dshMesChips"></div>' +
        '  <div id="dshMesInput"><input id="dshMesQ" placeholder="问点什么…（查数或 PCB 工艺）" />' +
        '    <button id="dshMesSend">发送</button></div>' +
        "</div>";
      document.body.appendChild(root);

      var style = document.createElement("style");
      style.id = "dsh-mes-panel-css";
      style.textContent = CSS;
      document.head.appendChild(style);

      var panel = document.getElementById("dshMesPanel");
      var msgs = document.getElementById("dshMesMsgs");
      var input = document.getElementById("dshMesQ");
      var sendBtn = document.getElementById("dshMesSend");

      document.getElementById("dshMesToggle").onclick = function () {
        panel.classList.toggle("open");
      };
      document.getElementById("dshMesClose").onclick = function () {
        panel.classList.remove("open");
      };

      var convs = [];
      try { convs = JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch (e) { convs = []; }
      var cur = null;

      function save() {
        try { localStorage.setItem(LS_KEY, JSON.stringify(convs.slice(-50))); } catch (e) {}
      }
      function newConv() {
        cur = { id: Date.now(), msgs: [], codeDevBrief: null };
        convs.push(cur);
        save();
      }
      function touchCodeDevBrief(text, isCodeDevFlow) {
        if (!cur) return null;
        if (!cur.codeDevBrief) {
          cur.codeDevBrief = { original_goal: "", workspace: "", selections: [], notes: [], option_rounds: 0 };
        }
        var b = cur.codeDevBrief;
        var raw = String(text || "").trim();
        if (raw.indexOf("【写码需求选项已确认】") === 0) {
          b.option_rounds = (b.option_rounds || 0) + 1;
          var lines = raw.replace(/^【写码需求选项已确认】\n?/, "").split("\n").filter(function (x) { return x.trim(); });
          b.selections = b.selections || [];
          b.selections.push({ round: b.option_rounds, lines: lines });
          lines.forEach(function (ln) {
            if (ln.indexOf("工程路径：") === 0) b.workspace = ln.slice(5).trim();
            if (ln.indexOf("备注：") === 0) {
              b.notes = b.notes || [];
              var n = ln.slice(3).trim();
              if (n && b.notes.indexOf(n) < 0) b.notes.push(n);
            }
          });
        } else if (isCodeDevFlow && raw.indexOf("【写码确认】") !== 0) {
          if ((!b.original_goal || raw.length > b.original_goal.length) && raw.length >= 6) {
            b.original_goal = raw;
          }
        }
        return b;
      }
      function getCodeDevBrief() {
        return (cur && cur.codeDevBrief) ? cur.codeDevBrief : null;
      }
      function renderMsg(role, text, chart, table, meta, persist, thinking) {
        var div = document.createElement("div");
        div.className = role === "user" ? "user" : "assist";
        if (role === "user") {
          div.textContent = text;
        } else {
          var html = "";
          if (thinking) {
            html += '<details class="think"><summary>已完成思考（点击展开）</summary><div class="think-body">' +
              md(stripMarks(thinking)) + "</div></details>";
          }
          html += '<div class="reply">' + md(stripMarks(text || "")) + "</div>";
          if (chart) html += '<img src="' + chart + '" alt="图表" />';
          if (table && table.length) {
            html += "<table><tr><th>项目</th><th>数值</th></tr>" +
              table.map(function (r) { return "<tr><td>" + esc(r.label) + "</td><td>" + esc(r.value) + "</td></tr>"; }).join("") +
              "</table>";
          }
          if (meta) html += '<div class="meta">' + esc(meta) + "</div>";
          div.innerHTML = html;
        }
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
        if (persist && cur) {
          cur.msgs.push({
            role: role, text: text, chart: chart || null, table: table || null,
            meta: meta || null, thinking: thinking || null,
          });
          save();
        }
        return div;
      }

      function startCodeDevJobWatch(jobId, startReply, opts) {
        opts = opts || {};
        // 兼容旧调用：第三参为 workspace 字符串
        if (typeof opts === "string") opts = { workspace: opts };
        var workspaceHint = opts.workspace || "";
        var resumeCommit = !!opts.resumeCommit;
        if (!jobId) {
          renderMsg("assistant", startReply || "已启动", null, null,
            "来源：写码顾问 · 数据源：本机写码 · 意图：本机写码", true, "");
          return;
        }
        if (!cur) newConv();
        var wrap = document.createElement("div");
        wrap.className = "assist cd-job-msg";
        wrap.innerHTML =
          '<div class="cd-job-shell">' +
          '  <div class="cd-plan-host"></div>' +
          '  <div class="cd-done-banner" style="display:none"></div>' +
          '  <details class="cd-result-details" style="display:none"><summary>改动说明与验收步骤</summary><div class="cd-result-body"></div></details>' +
          "</div>" +
          '<div class="meta">来源：写码顾问 · 数据源：本机写码 · 意图：本机写码 · ' + esc(jobId) + "</div>";
        msgs.appendChild(wrap);
        msgs.scrollTop = msgs.scrollHeight;
        var planHost = wrap.querySelector(".cd-plan-host");
        var bannerEl = wrap.querySelector(".cd-done-banner");
        var detailsEl = wrap.querySelector(".cd-result-details");
        var resultBody = wrap.querySelector(".cd-result-body");
        var startedAt = Date.now();
        var steps = initCodingSteps();
        var finished = false;
        var durationText = "0s";
        function paintPlan() {
          planHost.innerHTML = renderCodingPlanHtml(steps, { heading: "写码进度 · " + jobId, duration: durationText });
        }
        paintPlan();
        var durTimer = setInterval(function () {
          if (finished) { clearInterval(durTimer); return; }
          durationText = formatDuration((Date.now() - startedAt) / 1000);
          paintPlan();
        }, 1000);
        function openCommitPick(ws) {
          var workspace = (ws || workspaceHint || "").trim();
          fetch(engineBase() + "/api/code-commit/pick-ui", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ workspace: workspace }),
          })
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (!d.ok || !d.code_commit_ui) return;
              var host = document.createElement("div");
              host.className = "assist";
              host.innerHTML =
                '<div class="reply">' +
                md("修复已同步到本机。请确认下方**提交目录与分支**，开始门禁；通过后再点确认才会 commit/push。") +
                "</div>" +
                '<div class="meta">来源：提交顾问 · 数据源：人触发提交 · 意图：修复后继续提交</div>';
              msgs.appendChild(host);
              mountCodeCommitUi(host, d.code_commit_ui, host.querySelector(".meta"), {
                send: send,
                getBrief: getCodeDevBrief,
              });
              msgs.scrollTop = msgs.scrollHeight;
            })
            .catch(function () {});
        }
        function finish(ev) {
          if (finished) return;
          finished = true;
          clearInterval(durTimer);
          durationText = formatDuration((Date.now() - startedAt) / 1000);
          var ok = !!(ev && ev.ok);
          var mismatch = (ev && ev.job && ev.job.sync_mismatch) || "";
          if (ok && mismatch) ok = false;
          steps = sealCodingSteps(steps, !ok);
          paintPlan();
          var synced = (ev && ev.synced_files) || (ev && ev.job && ev.job.synced_files) || [];
          var n = synced.length;
          var job = (ev && ev.job) || {};
          var shouldResume =
            resumeCommit ||
            !!job.resume_commit ||
            !!job.source_gate_job_id ||
            !!(job.write_scope && job.write_scope.length);
          var wsDone = workspaceHint || job.workspace || "";
          bannerEl.style.display = "";
          bannerEl.className = "cd-done-banner " + (ok ? "ok" : "err");
          bannerEl.innerHTML =
            '<span class="cd-done-icon">' + (ok ? "✓" : "!") + "</span>" +
            "<div><strong>" + (ok ? "写码完成" : (mismatch ? "写码完成但模块可能不对" : "写码结束")) + "</strong> · 用时 " + esc(durationText) +
            (ok ? " · 已同步 " + n + " 个文件到本机（未自动 commit）" : " · " + esc(mismatch || (ev && ev.error) || "失败")) +
            (n && ok ? '<div class="cd-synced">' + esc(synced.slice(0, 8).join("、")) + (n > 8 ? " …" : "") + "</div>" : "") +
            (mismatch ? '<div class="cd-warn-box" style="margin-top:8px">' + esc(mismatch) + "</div>" : "") +
            (ok ? '<div class="cd-desc" style="margin-top:8px">' +
              (shouldResume
                ? "下一步：正在打开提交确认卡（须您确认后才会 commit/push）。"
                : "下一步：可点「继续提交代码」对本工程重新门禁并确认提交。") +
              "</div>" : "") +
            "</div>";
          if (ok) {
            var nextRow = document.createElement("div");
            nextRow.className = "cd-actions";
            nextRow.style.cssText = "margin-top:8px;padding:0;";
            nextRow.innerHTML = '<button type="button" class="cd-btn confirm cd-resubmit">继续提交代码</button>';
            bannerEl.appendChild(nextRow);
            var rs = nextRow.querySelector(".cd-resubmit");
            if (rs) {
              rs.onclick = function () { openCommitPick(wsDone); };
            }
            if (shouldResume) openCommitPick(wsDone);
          }
          var body = extractCodeDevResultBody((ev && ev.reply) || "");
          if (body) {
            detailsEl.style.display = "";
            resultBody.innerHTML = md(stripMarks(body));
          }
          var summaryText = (ok ? "✅ 写码完成" : "❌ 写码结束") + "（" + jobId + "，" + durationText + (n ? "，同步 " + n + " 个文件" : "") + "）";
          var meta = "来源：写码顾问 · 数据源：本机写码 · 意图：本机写码 · " + jobId;
          if (cur) {
            cur.msgs.push({
              role: "assistant", text: summaryText + (body ? "\n\n" + body : ""),
              thinking: null, chart: null, table: null, meta: meta,
            });
            save();
          }
          msgs.scrollTop = msgs.scrollHeight;
        }
        function onStreamEvent(ev) {
          if (!ev || !ev.type) return;
          if (ev.type === "step") {
            steps = applyCodingStep(steps, ev);
            paintPlan();
          } else if (ev.type === "done") {
            finish(ev);
          } else if (ev.type === "error") {
            finish({ ok: false, status: "failed", error: ev.message || ev.detail, reply: ev.message || ev.detail });
          }
        }
        fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jobId) + "/stream", {
          method: "GET",
          headers: { Accept: "text/event-stream" },
        })
          .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            if (!r.body || !r.body.getReader) throw new Error("不支持流式");
            var reader = r.body.getReader();
            var decoder = new TextDecoder();
            var pending = "";
            var terminal = false;
            function pump() {
              return reader.read().then(function (res) {
                if (res.done) {
                  if (!finished) {
                    return fetch(engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jobId))
                      .then(function (jr) { return jr.json(); })
                      .then(function (jd) {
                        if (jd && jd.job && ["succeeded", "failed", "cancelled"].indexOf(jd.job.status) >= 0) {
                          finish({
                            ok: jd.job.status === "succeeded", status: jd.job.status,
                            reply: jd.reply, error: jd.job.error,
                            synced_files: jd.job.synced_files, job: jd.job,
                          });
                        }
                      })
                      .catch(function () {});
                  }
                  return;
                }
                pending += decoder.decode(res.value, { stream: true });
                var parts = pending.split("\n\n");
                pending = parts.pop() || "";
                parts.forEach(function (chunk) {
                  var line = chunk.split("\n").filter(function (l) { return l.indexOf("data:") === 0; }).map(function (l) { return l.slice(5).trim(); }).join("");
                  if (!line) return;
                  try {
                    var ev = JSON.parse(line);
                    if (ev.type === "done" || ev.type === "error") terminal = true;
                    onStreamEvent(ev);
                  } catch (e1) {}
                });
                if (!terminal) return pump();
              });
            }
            return pump();
          })
          .catch(function (e) {
            finish({ ok: false, reply: "进度订阅失败：" + e.message, error: e.message });
          });
      }

      function createStreamBubble() {
        var div = document.createElement("div");
        div.className = "assist";
        div.innerHTML =
          '<div class="status-line">正在连接…</div>' +
          '<details class="think" style="display:none" open><summary class="think-sum">思考中…</summary><div class="think-body"></div></details>' +
          '<div class="reply"></div>' +
          '<div class="meta" style="display:none"></div>';
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
        return {
          el: div,
          status: div.querySelector(".status-line"),
          thinkWrap: div.querySelector(".think"),
          thinkSum: div.querySelector(".think-sum"),
          thinkBody: div.querySelector(".think-body"),
          reply: div.querySelector(".reply"),
          meta: div.querySelector(".meta"),
          thinkingText: "",
          replyText: "",
          replyStarted: false,
        };
      }

      function send(pre) {
        var text = String(pre || input.value || "").trim();
        if (!text) return;
        input.value = "";
        if (!cur) newConv();
        var isOpt = text.indexOf("【写码需求选项已确认】") === 0;
        var isCodeDevFlow = isOpt || /写码|改界面|改代码|报表中心|消息中心|开发|菜单|页面|接口|工时/.test(text);
        touchCodeDevBrief(text, isCodeDevFlow);
        var payload = { message: text };
        if (cur && cur.codeDevBrief && isCodeDevFlow) payload.code_dev_brief = cur.codeDevBrief;
        renderMsg("user", text, null, null, null, true);
        sendBtn.disabled = true;
        var bubble = createStreamBubble();

        fetch(engineBase() + "/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify(payload),
        })
          .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            if (!r.body || !r.body.getReader) throw new Error("浏览器不支持流式读取");
            var reader = r.body.getReader();
            var decoder = new TextDecoder();
            var pending = "";
            function pump() {
              return reader.read().then(function (res) {
                if (res.done) {
                  finish();
                  return;
                }
                pending += decoder.decode(res.value, { stream: true });
                var parts = pending.split("\n\n");
                pending = parts.pop() || "";
                parts.forEach(function (block) {
                  var lines = block.split("\n");
                  for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line.indexOf("data:") !== 0) continue;
                    var raw = line.slice(5).trim();
                    if (!raw) continue;
                    var ev;
                    try { ev = JSON.parse(raw); } catch (e) { continue; }
                    onEvent(ev);
                  }
                });
                return pump();
              });
            }
            var finished = false;
            function onEvent(ev) {
              if (!ev || !ev.type) return;
              if (ev.type === "status") {
                bubble.status.style.display = "";
                bubble.status.textContent = ev.detail || "处理中…";
              } else if (ev.type === "thinking") {
                // 正文开始后不再改写思考区，避免双通道切换导致「一会思考一会正文」
                if (bubble.replyStarted) return;
                bubble.status.style.display = "none";
                bubble.thinkingText = eventText(ev, bubble.thinkingText);
                if (bubble.thinkingText) {
                  bubble.thinkWrap.style.display = "";
                  bubble.thinkWrap.open = true;
                  if (bubble.thinkSum) bubble.thinkSum.textContent = "思考中…";
                  bubble.thinkBody.innerHTML = md(bubble.thinkingText);
                }
                msgs.scrollTop = msgs.scrollHeight;
              } else if (ev.type === "reply") {
                bubble.status.style.display = "none";
                // 正式回复开始：折叠思考，用户可再点开
                if (!bubble.replyStarted) {
                  bubble.replyStarted = true;
                  if (bubble.thinkingText) {
                    bubble.thinkWrap.style.display = "";
                    bubble.thinkWrap.open = false;
                    if (bubble.thinkSum) bubble.thinkSum.textContent = "已完成思考（点击展开）";
                  }
                }
                bubble.replyText = eventText(ev, bubble.replyText);
                bubble.reply.innerHTML = md(bubble.replyText);
                msgs.scrollTop = msgs.scrollHeight;
              } else if (ev.type === "error") {
                bubble.status.style.display = "none";
                bubble.reply.innerHTML = md("出错了：" + (ev.detail || "未知错误"));
                finished = true;
              } else if (ev.type === "done") {
                finished = true;
                bubble.status.style.display = "none";
                // done 以服务端拆好的全文为准，避免流式中间态残留标记
                if (ev.reply != null) bubble.replyText = stripMarks(ev.reply || "");
                else bubble.replyText = stripMarks(bubble.replyText);
                bubble.reply.innerHTML = md(bubble.replyText);
                if (ev.thinking != null) bubble.thinkingText = stripMarks(ev.thinking || "");
                else bubble.thinkingText = stripMarks(bubble.thinkingText);
                if (bubble.thinkingText) {
                  bubble.thinkWrap.style.display = "";
                  bubble.thinkWrap.open = false;
                  if (bubble.thinkSum) bubble.thinkSum.textContent = "已完成思考（点击展开）";
                  bubble.thinkBody.innerHTML = md(bubble.thinkingText);
                } else {
                  bubble.thinkWrap.style.display = "none";
                }
                if (ev.chart) {
                  var img = document.createElement("img");
                  img.src = ev.chart;
                  img.alt = "图表";
                  bubble.el.insertBefore(img, bubble.meta);
                }
                if (ev.table && ev.table.length) {
                  var tbl = document.createElement("table");
                  tbl.innerHTML = "<tr><th>项目</th><th>数值</th></tr>" +
                    ev.table.map(function (row) {
                      return "<tr><td>" + esc(row.label) + "</td><td>" + esc(row.value) + "</td></tr>";
                    }).join("");
                  bubble.el.insertBefore(tbl, bubble.meta);
                }
                var meta = formatChatMeta(ev);
                bubble.meta.style.display = "";
                bubble.meta.textContent = meta;
                if (ev.code_dev_ui) {
                  mountCodeDevUi(bubble.el, ev.code_dev_ui, bubble.meta, {
                    send: send,
                    getBrief: getCodeDevBrief,
                    onStarted: function (d) {
                      startCodeDevJobWatch(d.job_id, d.reply || ("已启动 " + (d.job_id || "")), {
                        workspace: (d.workspace || (d.job && d.job.workspace) || "") || undefined,
                        resumeCommit: !!(d.resume_commit || d.from_gate_fix || (d.job && d.job.resume_commit)),
                      });
                    },
                  });
                } else {
                  var fbUi = parseCodeDevUiFromText(bubble.replyText, "");
                  if (fbUi) {
                    mountCodeDevUi(bubble.el, fbUi, bubble.meta, {
                      send: send,
                      getBrief: getCodeDevBrief,
                      onStarted: function (d) {
                        startCodeDevJobWatch(d.job_id, d.reply || ("已启动 " + (d.job_id || "")), {
                          workspace: (d.workspace || (d.job && d.job.workspace) || "") || undefined,
                          resumeCommit: !!(d.resume_commit || d.from_gate_fix || (d.job && d.job.resume_commit)),
                        });
                      },
                    });
                  }
                }
                if (ev.code_review_ui) {
                  mountCodeReviewUi(bubble.el, ev.code_review_ui, bubble.meta, {
                    renderMsg: renderMsg,
                  });
                }
                if (ev.code_commit_ui) {
                  mountCodeCommitUi(bubble.el, ev.code_commit_ui, bubble.meta, {
                    renderMsg: renderMsg,
                    send: send,
                    getBrief: getCodeDevBrief,
                    onStarted: function (d) {
                      startCodeDevJobWatch(d.job_id, d.reply || ("已启动 " + (d.job_id || "")), {
                        workspace: (d.workspace || (d.job && d.job.workspace) || "") || undefined,
                        resumeCommit: !!(d.resume_commit || d.from_gate_fix || (d.job && d.job.resume_commit)),
                      });
                    },
                  });
                }
                if (ev.code_deploy_ui) {
                  mountCodeDeployUi(bubble.el, ev.code_deploy_ui, bubble.meta);
                }
                if (ev.code_dev_brief && cur) {
                  cur.codeDevBrief = ev.code_dev_brief;
                }
                if (cur) {
                  cur.msgs.push({
                    role: "assistant",
                    text: bubble.replyText,
                    thinking: bubble.thinkingText || null,
                    chart: ev.chart || null,
                    table: ev.table || null,
                    meta: meta,
                  });
                  save();
                }
              }
            }
            function finish() {
              if (!finished && !bubble.replyText) {
                bubble.status.style.display = "none";
                bubble.reply.textContent = "（流式结束，未收到完整回复）";
              }
              sendBtn.disabled = false;
              input.focus();
            }
            return pump().catch(function (e) {
              bubble.status.style.display = "none";
              bubble.reply.textContent = "流式读取失败：" + e.message;
              sendBtn.disabled = false;
            });
          })
          .catch(function (e) {
            bubble.status.style.display = "none";
            bubble.reply.textContent =
              "引擎未连接（" + engineBase() + "）：" + e.message +
              "\n请确认引擎已启动：scripts/engine.sh zr-workbuddy ensure";
            sendBtn.disabled = false;
            input.focus();
          });
      }

      var chips = document.getElementById("dshMesChips");
      SUGGESTIONS.forEach(function (s) {
        var b = document.createElement("button");
        b.textContent = s;
        b.onclick = function () { send(s); };
        chips.appendChild(b);
      });
      sendBtn.onclick = function () { send(); };
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });

      renderMsg("assistant",
        "你好！我是 ZR-WorkBuddy。\n" +
        "• 查数出图：例如 **今天正在生产的工单有多少个**\n" +
        "• PCB 工艺：例如 **飞针和 AOI 怎么分工**（会展示思考过程，并流式输出）",
        null, null, null, false);

      discoverEngine(function () {
        fetch(STATUS_URL()).then(function (r) { return r.json(); }).then(function (s) {
          document.getElementById("dshMesDot").className = "dot " + (s.ok ? "ok" : "");
        }).catch(function () {});
      });
    }

    function apply() {
      if (typeof document === "undefined") return;
      try {
        buildPanel();
        console.log("[dsh-mes-bridge] 聊天面板已挂载");
      } catch (err) {
        console.error("[dsh-mes-bridge] 面板挂载失败:", err);
      }
    }

    var inject = [];
    module.exports = { inject: inject, apply: apply };
    return module.exports;
  },
});

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
      "#dshMesMsgs .assist .reply{white-space:pre-wrap;word-break:break-word}" +
      "#dshMesMsgs .assist .reply strong{font-weight:600}" +
      "#dshMesMsgs .assist .reply h1,#dshMesMsgs .assist .reply h2,#dshMesMsgs .assist .reply h3{margin:0.6em 0 0.25em;font-weight:650;line-height:1.35}" +
      "#dshMesMsgs .assist .reply h1{font-size:1.15em}" +
      "#dshMesMsgs .assist .reply h2{font-size:1.08em}" +
      "#dshMesMsgs .assist .reply h3{font-size:1.02em}" +
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
      t = t.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
      t = t.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
      t = t.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");
      return t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
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
      return "演示数据";
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
        cur = { id: Date.now(), msgs: [] };
        convs.push(cur);
        save();
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
        renderMsg("user", text, null, null, null, true);
        sendBtn.disabled = true;
        var bubble = createStreamBubble();

        fetch(engineBase() + "/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ message: text }),
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
                var srcTxt = ev.source === "llm" ? "LLM" : ev.source === "offline" ? "离线提示" : "规则引擎";
                var meta =
                  "来源：" + srcTxt + " · 数据源：" + dataSourceLabel(ev.data_source) +
                  (ev.intent && ev.intent.type ? " · " + ev.intent.type : "") +
                  (ev.note ? " · " + ev.note : "");
                bubble.meta.style.display = "";
                bubble.meta.textContent = meta;
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

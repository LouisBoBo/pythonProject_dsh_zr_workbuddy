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
      if (cssInjected || typeof document === "undefined") return;
      cssInjected = true;
      var s = document.createElement("style");
      s.dataset.plugin = "@dsh-external/dsh-mes-bridge";
      s.textContent =
        ".wb-cr{font:13px/1.5 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#111827;border:1px solid #e5e7eb;border-radius:12px;background:#fff;overflow:hidden;margin:4px 0 8px}" +
        ".wb-cr-head{padding:10px 12px;border-bottom:1px solid #eef0f3;display:flex;align-items:center;gap:8px}" +
        ".wb-cr-badge{font-size:11px;font-weight:700;color:#0f766e;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:999px;padding:2px 8px}" +
        ".wb-cr-hint{font-size:11px;color:#64748b}" +
        ".wb-cr-body{padding:12px}" +
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
        ".wb-cd-li.is-running .wb-cd-ico{background:#cffafe;color:#0e7490}" +
        ".wb-cd-li.is-done .wb-cd-ico{background:#d1fae5;color:#047857}" +
        ".wb-cd-li.is-error .wb-cd-ico{background:#fee2e2;color:#b91c1c}" +
        ".wb-cd-title{font-weight:600;color:#111827;display:block}" +
        ".wb-cd-state{color:#64748b;font-size:11px}" +
        ".wb-cd-pulse{display:inline-block;width:8px;height:8px;border-radius:999px;background:#06b6d4;animation:wbCdPulse 1s ease-in-out infinite}" +
        "@keyframes wbCdPulse{0%,100%{opacity:.35;transform:scale(.85)}50%{opacity:1;transform:scale(1)}}" +
        ".wb-cd-stream{font:12px/1.45 ui-monospace,Menlo,monospace;color:#334155;white-space:pre-wrap;max-height:220px;overflow:auto;background:#0f172a;color:#e2e8f0;border-radius:8px;padding:10px;margin-top:8px}" +
        ".wb-cd-alive{font-size:12px;color:#0f766e;margin:0 0 8px}" +
        ".wb-cr-sum{font-size:12px;color:#4b5563;margin:0 0 8px}" +
        ".wb-cr-kv{display:grid;grid-template-columns:4.5em 1fr;gap:4px 10px;margin:0 0 10px;font-size:12px}" +
        ".wb-cr-kv dt{margin:0;color:#94a3b8;font-weight:600}" +
        ".wb-cr-kv dd{margin:0;color:#334155;word-break:break-all}" +
        ".wb-cr-kv a{color:#0f766e;text-decoration:none}" +
        ".wb-cr-kv a:hover{text-decoration:underline}" +
        ".wb-cr-units{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px;max-height:140px;overflow:auto}" +
        ".wb-cr-unit{display:inline-flex;align-items:center;gap:4px;border:1px solid #e2e8f0;background:#f8fafc;border-radius:999px;padding:3px 9px;font-size:11px;color:#334155}" +
        ".wb-cr-unit .k{color:#94a3b8;font-size:10px}" +
        ".wb-cr-note{font-size:11px;color:#64748b;margin:0 0 8px;line-height:1.45}";
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

    function CodeReviewBeginCard(props) {
      ensureCss();
      var block = props.block;
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var dshCwd = resolveDshCwd(props);

      var _phase = useState("dir"); // dir | files | running | done
      var phase = _phase[0];
      var setPhase = _phase[1];
      var _ws = useState(initialWorkspace(props, ui));
      var workspace = _ws[0];
      var setWorkspace = _ws[1];
      var _scope = useState(String(ui.scope || ""));
      var scope = _scope[0];
      var setScope = _scope[1];
      var _focus = useState(String(ui.focus || ""));
      var focus = _focus[0];
      var setFocus = _focus[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _files = useState([]);
      var files = _files[0];
      var setFiles = _files[1];
      var _sample = useState([]);
      var sample = _sample[0];
      var setSample = _sample[1];
      var _selected = useState({});
      var selected = _selected[0];
      var setSelected = _selected[1];
      var _count = useState(0);
      var count = _count[0];
      var setCount = _count[1];
      var _log = useState("");
      var log = _log[0];
      var setLog = _log[1];
      var _report = useState("");
      var report = _report[0];
      var setReport = _report[1];
      var _pathTicket = useState("");
      var pathTicket = _pathTicket[0];
      var setPathTicket = _pathTicket[1];

      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];

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
        fetch(engineBase() + "/api/pick-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: "选择要审核的工程目录" }),
          signal: ctrl ? ctrl.signal : undefined,
        })
          .then(function (r) {
            return r.json();
          })
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
            h("span", { className: "wb-cr-hint" }, phase === "running" ? "进行中（勿重复点击）" : "完成"),
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
                      onClick: function () {
                        setPhase("dir");
                        setErr("");
                        setLog("");
                        setReport("");
                      },
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
          h("span", { className: "wb-cr-hint" }, "选择目录 · 下一步勾选文件"),
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

    function CodeCommitBeginCard(props) {
      ensureCss();
      var block = props.block;
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var dshCwd = resolveDshCwd(props);

      var _phase = useState("dir"); // dir | files | gating | blocked | confirm | done
      var phase = _phase[0];
      var setPhase = _phase[1];
      var _ws = useState(initialWorkspace(props, ui));
      var workspace = _ws[0];
      var setWorkspace = _ws[1];
      var _branch = useState(String(ui.work_branch || ""));
      var branch = _branch[0];
      var setBranch = _branch[1];
      var _branchHint = useState(String(ui.branch_hint || ""));
      var branchHint = _branchHint[0];
      var setBranchHint = _branchHint[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _files = useState([]);
      var files = _files[0];
      var setFiles = _files[1];
      var _selected = useState({});
      var selected = _selected[0];
      var setSelected = _selected[1];
      var _draft = useState("");
      var draft = _draft[0];
      var setDraft = _draft[1];
      var _push = useState(ui.default_push !== false);
      var push = _push[0];
      var setPush = _push[1];
      var _jobId = useState("");
      var jobId = _jobId[0];
      var setJobId = _jobId[1];
      var _findings = useState([]);
      var findings = _findings[0];
      var setFindings = _findings[1];
      var _summary = useState("");
      var summary = _summary[0];
      var setSummary = _summary[1];
      var _result = useState("");
      var result = _result[0];
      var setResult = _result[1];

      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];

      // 目录预填（DSH 工作区 / 上次路径）时自动识别当前分支；须在任何 early return 之前挂 effect。
      useEffect(
        function () {
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
        fetch(engineBase() + "/api/pick-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: "选择要提交的 Git 工程目录" }),
          signal: ctrl ? ctrl.signal : undefined,
        })
          .then(function (r) {
            return r.json();
          })
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
            setPhase("done");
            if (d.ok) {
              setResult(d.reply || "提交成功" + (doPush ? "并已推送" : "（仅本地）"));
              setErr("");
            } else if (d.push_retry_needed) {
              setResult(d.reply || "本地已 commit，推送失败，可稍后重试推送");
              setErr(d.detail || d.reply || "push 失败");
            } else {
              setResult("");
              setErr(d.detail || d.reply || "确认失败");
            }
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

      if (phase === "done") {
        return h(
          "div",
          { className: "wb-cr" },
          head("完成"),
          h(
            "div",
            { className: "wb-cr-body" },
            result ? h("pre", { className: "wb-cr-progress" }, result) : null,
            err ? h("p", { className: "wb-cr-err" }, err) : null,
            h(
              "div",
              { className: "wb-cr-actions" },
              h(
                "button",
                {
                  type: "button",
                  className: "wb-cr-btn",
                  onClick: function () {
                    setPhase("dir");
                    setErr("");
                    setResult("");
                    setSummary("");
                    setFindings([]);
                  },
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
        head("选择目录 · 下一步勾选文件"),
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
      { id: "boot", title: "任务已排队" },
      { id: "sandbox-prep", title: "沙箱就绪" },
      { id: "dev", title: "Cursor 改码" },
      { id: "sync", title: "同步到本机" },
    ];
    var CD_STEP_MAP = { "agent-loop": "dev", "cursor-local": "dev" };

    function cdInitSteps() {
      return CD_PIPELINE.map(function (p) {
        return {
          id: p.id,
          title: p.title,
          state: p.id === "boot" ? "done" : "pending",
        };
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
      if (title) merged.title = title;
      if (id === "dev") {
        if (rawId === "cursor-local" && nextState === "done") merged.state = "running";
        else if (rawId === "agent-loop" && nextState === "done") merged.state = "done";
        else if (nextState === "running") merged.state = "running";
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
      var s = sec % 60;
      return m > 0 ? m + "分" + s + "秒" : s + "秒";
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
                ? h("span", { className: "wb-cd-pulse" })
                : st === "done"
                  ? "✓"
                  : st === "error"
                    ? "!"
                    : String(i + 1);
            var hint =
              st === "running"
                ? "进行中"
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

    function CodeDevBeginCard(props) {
      ensureCss();
      var block = props.block;
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var dshCwd = resolveDshCwd(props);

      // 对齐原 WorkBuddy：form(原始诉求) → options → propose → confirm 开工
      var _phase = useState("form"); // form | options | propose | running | done
      var phase = _phase[0];
      var setPhase = _phase[1];
      var _ws = useState(initialWorkspace(props, ui));
      var workspace = _ws[0];
      var setWorkspace = _ws[1];
      var _req = useState(initialRequirement(props, ui));
      var requirement = _req[0];
      var setRequirement = _req[1];
      var _goal = useState(initialRequirement(props, ui));
      var goal = _goal[0];
      var setGoal = _goal[1];
      var _brief = useState(ui.brief || null);
      var brief = _brief[0];
      var setBrief = _brief[1];
      var _optionsUi = useState(null);
      var optionsUi = _optionsUi[0];
      var setOptionsUi = _optionsUi[1];
      var _proposeUi = useState(null);
      var proposeUi = _proposeUi[0];
      var setProposeUi = _proposeUi[1];
      var _sel = useState({});
      var selectedOpts = _sel[0];
      var setSelectedOpts = _sel[1];
      var _notes = useState("");
      var notes = _notes[0];
      var setNotes = _notes[1];
      var _ack = useState(false);
      var ackWarn = _ack[0];
      var setAckWarn = _ack[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _jobId = useState("");
      var jobId = _jobId[0];
      var setJobId = _jobId[1];
      var _log = useState("");
      var log = _log[0];
      var setLog = _log[1];
      var _result = useState("");
      var result = _result[0];
      var setResult = _result[1];
      var _synced = useState([]);
      var synced = _synced[0];
      var setSynced = _synced[1];
      var _deferred = useState([]);
      var deferred = _deferred[0];
      var setDeferred = _deferred[1];
      var _steps = useState(cdInitSteps());
      var steps = _steps[0];
      var setSteps = _steps[1];
      var _stream = useState("");
      var streamText = _stream[0];
      var setStreamText = _stream[1];
      var _elapsed = useState(0);
      var elapsed = _elapsed[0];
      var setElapsed = _elapsed[1];
      var _alive = useState("准备启动…");
      var aliveHint = _alive[0];
      var setAliveHint = _alive[1];

      var suggestions = Array.isArray(ui.suggestions) ? ui.suggestions : [];

      useEffect(
        function () {
          if (dshCwd && !String(workspace || "").trim()) setWorkspace(dshCwd);
        },
        [dshCwd],
      );

      if (!wb || (wb.t !== "cd-pick" && !(ui && ui.kind === "pick"))) {
        if (!(ui && (ui.kind === "pick" || ui.kind === "propose" || ui.kind === "options"))) {
          var out =
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
            h("div", { className: "wb-cr-body" }, h("pre", { className: "wb-cr-progress", style: { margin: 0 } }, out || "（无详情）")),
          );
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
        fetch(engineBase() + "/api/pick-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: "选择要写码的本机工程目录" }),
          signal: ctrl ? ctrl.signal : undefined,
        })
          .then(function (r) {
            return r.json();
          })
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

      function watchJob(jid) {
        setPhase("running");
        setBusy(true);
        setSteps(cdInitSteps());
        setStreamText("");
        setElapsed(0);
        setAliveHint("任务已启动，正在连接进度流…");
        setLog("");
        setErr("");
        var logAcc = "";
        var streamAcc = "";
        var stepState = cdInitSteps();
        var finished = false;
        var startedAt = Date.now();
        var lastFlush = 0;
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
          if (!force && now - lastFlush < 200) return;
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
          flushStream(true);
          setBusy(false);
          setPhase("done");
          var asError = !!(ev && (ev.ok === false || ev.error));
          setSteps(cdSealSteps(stepState, asError));
          setAliveHint(
            asError
              ? "任务结束（失败）· 共 " + cdFormatDuration(Math.floor((Date.now() - startedAt) / 1000))
              : "任务完成 · 共 " + cdFormatDuration(Math.floor((Date.now() - startedAt) / 1000)),
          );
          if (ev && ev.synced_files) setSynced(ev.synced_files || []);
          if (ev && ev.deferred_files) setDeferred(ev.deferred_files || []);
          if (ev && ev.job) {
            if (ev.job.synced_files) setSynced(ev.job.synced_files || []);
            if (ev.job.deferred_files) setDeferred(ev.job.deferred_files || []);
          }
          var ok = !asError;
          setResult(
            (ev && (ev.reply || ev.error || ev.detail)) ||
              (ok ? "写码任务已结束" : "写码失败"),
          );
          if (!ok) setErr((ev && (ev.error || ev.detail || ev.reply)) || "写码失败");
          else if (ev && (ev.deferred_files || []).length) {
            setErr(
              "有 " +
                ev.deferred_files.length +
                " 个文件因写范围未同步（含路由/菜单时会导致刷新看不到新界面）：" +
                ev.deferred_files.slice(0, 6).join("、"),
            );
          }
        }
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
                // SSE 可能推增量，也可能是 live_text 切片增量
                streamAcc += String(ev.text || "");
                if (streamAcc.length > 16000) streamAcc = streamAcc.slice(-16000);
                flushStream(false);
              } else if (ev.type === "replace_text") {
                streamAcc = String(ev.text || "");
                flushStream(true);
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
                          streamAcc = String(job.live_text);
                          flushStream(true);
                        }
                        finish({
                          ok: st === "succeeded" || st === "done" || !!(jd && jd.ok && st !== "failed"),
                          reply: (jd && jd.reply) || "",
                          job: job,
                          synced_files: job.synced_files || [],
                          deferred_files: job.deferred_files || [],
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
        issueHitl("code-dev.confirm", { workspace: ws })
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
            if (jid) watchJob(jid);
            else {
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

      if (phase === "running" || phase === "done") {
        return h(
          "div",
          { className: "wb-cr" },
          head(phase === "running" ? "Cursor 写码中…" : "完成"),
          h(
            "div",
            { className: "wb-cr-body" },
            h(
              "p",
              { className: "wb-cr-sum" },
              "工程：" + workspace + (jobId ? " · " + jobId : ""),
            ),
            phase === "running"
              ? h(
                  "p",
                  { className: "wb-cd-alive" },
                  h("span", { className: "wb-cd-pulse", style: { marginRight: 8 } }),
                  aliveHint || "进行中…",
                )
              : h("p", { className: "wb-cd-alive" }, aliveHint || "已结束"),
            h(CdPlanView, {
              steps: steps,
              duration: cdFormatDuration(elapsed),
              summary: cdPlanSummary(steps),
            }),
            streamText
              ? h(
                  "div",
                  null,
                  h("div", { className: "wb-cr-label" }, "改码过程输出"),
                  h("pre", { className: "wb-cd-stream" }, streamText),
                )
              : phase === "running"
                ? h(
                    "p",
                    { className: "wb-cr-dsh" },
                    "等待 Cursor 流式输出…（沙箱准备阶段可能暂无正文，计时仍会更新）",
                  )
                : null,
            log
              ? h(
                  "details",
                  { open: phase === "running" && !streamText, style: { marginTop: 8 } },
                  h("summary", { className: "wb-cr-label", style: { cursor: "pointer" } }, "步骤日志"),
                  h("pre", { className: "wb-cr-progress", style: { margin: 0 } }, log),
                )
              : null,
            result ? h("p", { className: "wb-cr-sum", style: { marginTop: 8 } }, result) : null,
            synced && synced.length
              ? h(
                  "div",
                  null,
                  h("div", { className: "wb-cr-label" }, "已同步到工程"),
                  h(
                    "div",
                    { className: "wb-cr-files" },
                    synced.slice(0, 40).map(function (f, i) {
                      return h("div", { key: i, className: "wb-cr-file" }, h("span", null, String(f)));
                    }),
                  ),
                )
              : null,
            deferred && deferred.length
              ? h(
                  "div",
                  { className: "wb-cr-warn", style: { marginTop: 8 } },
                  "未同步 " +
                    deferred.length +
                    " 个文件（路由/菜单/API 若在此列，刷新会看不到新界面）：\n" +
                    deferred.slice(0, 12).join("\n"),
                )
              : null,
            err ? h("p", { className: "wb-cr-err" }, err) : null,
          ),
        );
      }

      if (phase === "options" && optionsUi) {
        var opts = optionsUi.options || {};
        var groups = Array.isArray(opts.groups) ? opts.groups : [];
        var og = optionsUi.original_goal || (optionsUi.brief && optionsUi.brief.original_goal) || goal;
        return h(
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
        );
      }

      if (phase === "propose") {
        var pui = proposeUi || {};
        var val = pui.validation || {};
        var mod = (pui.target_hints && pui.target_hints.module) || "";
        var paths = (pui.target_hints && pui.target_hints.expected_paths) || [];
        var og2 = pui.original_goal || (pui.brief && pui.brief.original_goal) || goal;
        var hasErr = !!(val.errors && val.errors.length);
        var hasWarn = !!(val.warnings && val.warnings.length) && !hasErr;
        return h(
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
        );
      }

      // form：只收集目录 + 原始诉求，再进入讨论（禁止直接 confirm）
      return h(
        "div",
        { className: "wb-cr" },
        head("选择目录 · 填写诉求 · 先梳理需求"),
        h(
          "div",
          { className: "wb-cr-body" },
          h(
            "p",
            { className: "wb-cr-sum" },
            "与原先 WorkBuddy 一致：先选项/确认卡梳理需求，确认后才会启动 Cursor；不会自动 commit。",
          ),
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
      );
    }

    /** 一体部署确认卡：单卡一步确认（精简 meta，避免工具卡丢 units） */
    function CodeDeployConfirmCard(props) {
      ensureCss();
      var block = props.block;
      var wb = useMemo(function () {
        return readMeta(block);
      }, [block]);
      var ui = (wb && wb.ui) || {};
      var kind = String(ui.kind || (wb && String(wb.t || "").replace(/^cdp-/, "")) || "confirm");

      var _busy = useState(false);
      var busy = _busy[0];
      var setBusy = _busy[1];
      var _err = useState("");
      var err = _err[0];
      var setErr = _err[1];
      var _done = useState(kind === "success");
      var done = _done[0];
      var setDone = _done[1];
      var _success = useState(kind === "success" ? ui : null);
      var success = _success[0];
      var setSuccess = _success[1];

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

      // 准备失败时不要画空确认卡（——:— / 0 单元）
      if (kind === "confirm" && !ui.job_id) {
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
            setSuccess({
              title: succ.title || (mode === "full" ? "全量部署完成" : "增量部署完成"),
              entry_url: succ.entry_url || succ.access_url || succ.health_url || entry,
              remote: succ.remote || "",
              env: succ.env || ui.env || "",
              units: succ.units || ids,
              actions: succ.actions || [],
            });
            setDone(true);
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
            h("div", { className: "wb-cr-head" }, h("span", { className: "wb-cr-badge" }, "已取消")),
            h("div", { className: "wb-cr-body" }, h("p", { className: "wb-cr-sum" }, "未执行同步")),
          );
        }
        return h(
          "div",
          { className: "wb-cr" },
          h("div", { className: "wb-cr-head" }, h("span", { className: "wb-cr-badge" }, "部署完成")),
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
          h("span", { className: "wb-cr-hint" }, "点确认后才会同步 · 不动 8092"),
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
              "一体部署、一个入口：确认一次 → 同步改动并拉起引擎+聊天壳。须保持功能插件 code-deploy 开启。",
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
    }

    module.exports = { inject: ["slots"], apply: apply };
    return module.exports;
  },
});

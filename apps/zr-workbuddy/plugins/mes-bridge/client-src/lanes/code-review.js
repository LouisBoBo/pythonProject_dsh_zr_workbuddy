export function installCodeReview(ctx) {
  var React = ctx.React, h = ctx.h, useState = ctx.useState, useEffect = ctx.useEffect,
      useLayoutEffect = ctx.useLayoutEffect, useRef = ctx.useRef, useMemo = ctx.useMemo;
  var engineBase = ctx.engineBase, engineHost = ctx.engineHost, enginePort = ctx.enginePort;
  var AUTH_LS_KEY = ctx.AUTH_LS_KEY, AUTH_ENTERPRISES = ctx.AUTH_ENTERPRISES, AUTH_EVENT = ctx.AUTH_EVENT;
  var readAuthSession = ctx.readAuthSession, writeAuthSession = ctx.writeAuthSession,
      authHeaders = ctx.authHeaders, notifyAuthChanged = ctx.notifyAuthChanged, doAppLogout = ctx.doAppLogout;
  var pickLocalFolder = ctx.pickLocalFolder, issueHitl = ctx.issueHitl, discoverEngine = ctx.discoverEngine,
      ensureCss = ctx.ensureCss;
  var readMeta = ctx.readMeta, expandHomePath = ctx.expandHomePath, pathsEqual = ctx.pathsEqual,
      resolveDshCwd = ctx.resolveDshCwd, initialWorkspace = ctx.initialWorkspace,
      textFromContentBlocks = ctx.textFromContentBlocks, toolArgsMessage = ctx.toolArgsMessage,
      lastUserUtterance = ctx.lastUserUtterance, initialRequirement = ctx.initialRequirement,
      WorkspaceMismatchHint = ctx.WorkspaceMismatchHint;

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
        ui_session_id: crBlockSessionId(block, props.sessionId) || "",
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

  ctx.CodeReviewBeginCard = CodeReviewBeginCard;
}

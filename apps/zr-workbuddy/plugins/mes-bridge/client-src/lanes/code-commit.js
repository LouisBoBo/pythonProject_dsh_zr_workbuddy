export function installCodeCommit(ctx) {
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

  ctx.CodeCommitBeginCard = CodeCommitBeginCard;
}

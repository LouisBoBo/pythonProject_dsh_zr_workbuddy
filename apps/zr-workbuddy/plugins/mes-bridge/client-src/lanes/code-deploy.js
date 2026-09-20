export function installCodeDeploy(ctx) {
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

  ctx.CodeDeployConfirmCard = CodeDeployConfirmCard;
}

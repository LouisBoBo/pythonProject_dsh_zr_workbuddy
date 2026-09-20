/**
 * 写码车道：本地持久化 + pipeline 步骤（纯逻辑，无 React）。
 * 由 code-dev.js 组装；禁止改行为，只搬文件。
 *
 * cdPersistNormalize 依赖正文清洗函数（仍在 code-dev.js）：
 * 须在 code-dev 定义 scrub 后调用 setScrubbers，再渲染 CodeDevBeginCard。
 */
export function createCodeDevPersist() {
  var _scrub = {
    stripBoilerplate: function (s) {
      return String(s || "");
    },
    stripExploration: function (s) {
      return String(s || "");
    },
    dedupeThink: function (s) {
      return String(s || "");
    },
  };
  function setScrubbers(fns) {
    if (!fns || typeof fns !== "object") return;
    if (typeof fns.cdStripBoilerplate === "function") {
      _scrub.stripBoilerplate = fns.cdStripBoilerplate;
    }
    if (typeof fns.cdStripExplorationFromProcess === "function") {
      _scrub.stripExploration = fns.cdStripExplorationFromProcess;
    }
    if (typeof fns.cdDedupeThinkText === "function") {
      _scrub.dedupeThink = fns.cdDedupeThinkText;
    }
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
    o.streamText = _scrub.stripExploration(_scrub.stripBoilerplate(String(o.streamText || "")));
  }
  if (o.thinkingText) o.thinkingText = _scrub.dedupeThink(String(o.thinkingText || ""));
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


  return {
    setScrubbers,
    CD_PIPELINE,
    CD_STEP_MAP,
    CD_PERSIST_VER,
    CD_PERSIST_MIN_VER,
    CD_UI_REV,
    CD_PERSIST_MAX_STREAM,
    CD_PERSIST_MAX_DELIVERY,
    CD_PERSIST_MAX_THINK,
    CD_ICON_COPY,
    CD_ICON_DOWNLOAD,
    cdPersistClip,
    cdPersistMergeBody,
    cdPersistLoadJobSnapshot,
    cdPersistEnrichCardSaved,
    cdFinalizeSteps,
    cdBlockCallId,
    cdBlockSessionId,
    cdPersistKey,
    cdPersistKeyAliases,
    cdPersistBelongsToCall,
    cdPickMustStayHitl,
    cdPersistNormalize,
    cdPersistLoad,
    cdPersistScanByCallId,
    cdPersistLoadForCard,
    cdPersistPrune,
    cdPersistSave,
    cdPersistSaveCard,
    cdPersistClear,
    cdJobStepsFromRecord,
    cdJobElapsed,
    cdJobAliveHint,
    cdInitSteps,
    cdPipelineIndex,
    cdNormalizeStepId,
    cdMarkPriorDone,
    cdSealSteps,
    cdApplyStep,
    cdPlanSummary,
    cdFormatDuration,
  };
}

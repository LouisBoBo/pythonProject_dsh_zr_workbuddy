export function installSharedHelpers(ctx) {
  var React = ctx.React, h = ctx.h, useState = ctx.useState, useEffect = ctx.useEffect,
      useLayoutEffect = ctx.useLayoutEffect, useRef = ctx.useRef, useMemo = ctx.useMemo;
  var engineBase = ctx.engineBase, engineHost = ctx.engineHost, enginePort = ctx.enginePort;
  var ensureCss = ctx.ensureCss;

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

  ctx.readMeta = readMeta;
  ctx.expandHomePath = expandHomePath;
  ctx.pathsEqual = pathsEqual;
  ctx.resolveDshCwd = resolveDshCwd;
  ctx.initialWorkspace = initialWorkspace;
  ctx.textFromContentBlocks = textFromContentBlocks;
  ctx.toolArgsMessage = toolArgsMessage;
  ctx.lastUserUtterance = lastUserUtterance;
  ctx.initialRequirement = initialRequirement;
  ctx.WorkspaceMismatchHint = WorkspaceMismatchHint;
}

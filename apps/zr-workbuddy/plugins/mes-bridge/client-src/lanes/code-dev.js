import { createCodeDevPersist } from './code-dev-persist.js';

export function installCodeDev(ctx) {
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

  var _cdP = createCodeDevPersist();
  var CD_PIPELINE = _cdP.CD_PIPELINE;
  var CD_STEP_MAP = _cdP.CD_STEP_MAP;
  var CD_PERSIST_VER = _cdP.CD_PERSIST_VER;
  var CD_PERSIST_MIN_VER = _cdP.CD_PERSIST_MIN_VER;
  var CD_UI_REV = _cdP.CD_UI_REV;
  var CD_PERSIST_MAX_STREAM = _cdP.CD_PERSIST_MAX_STREAM;
  var CD_PERSIST_MAX_DELIVERY = _cdP.CD_PERSIST_MAX_DELIVERY;
  var CD_PERSIST_MAX_THINK = _cdP.CD_PERSIST_MAX_THINK;
  var CD_ICON_COPY = _cdP.CD_ICON_COPY;
  var CD_ICON_DOWNLOAD = _cdP.CD_ICON_DOWNLOAD;
  var cdPersistClip = _cdP.cdPersistClip;
  var cdPersistMergeBody = _cdP.cdPersistMergeBody;
  var cdPersistLoadJobSnapshot = _cdP.cdPersistLoadJobSnapshot;
  var cdPersistEnrichCardSaved = _cdP.cdPersistEnrichCardSaved;
  var cdFinalizeSteps = _cdP.cdFinalizeSteps;
  var cdBlockCallId = _cdP.cdBlockCallId;
  var cdBlockSessionId = _cdP.cdBlockSessionId;
  var cdPersistKey = _cdP.cdPersistKey;
  var cdPersistKeyAliases = _cdP.cdPersistKeyAliases;
  var cdPersistBelongsToCall = _cdP.cdPersistBelongsToCall;
  var cdPickMustStayHitl = _cdP.cdPickMustStayHitl;
  var cdPersistNormalize = _cdP.cdPersistNormalize;
  var cdPersistLoad = _cdP.cdPersistLoad;
  var cdPersistScanByCallId = _cdP.cdPersistScanByCallId;
  var cdPersistLoadForCard = _cdP.cdPersistLoadForCard;
  var cdPersistPrune = _cdP.cdPersistPrune;
  var cdPersistSave = _cdP.cdPersistSave;
  var cdPersistSaveCard = _cdP.cdPersistSaveCard;
  var cdPersistClear = _cdP.cdPersistClear;
  var cdJobStepsFromRecord = _cdP.cdJobStepsFromRecord;
  var cdJobElapsed = _cdP.cdJobElapsed;
  var cdJobAliveHint = _cdP.cdJobAliveHint;
  var cdInitSteps = _cdP.cdInitSteps;
  var cdPipelineIndex = _cdP.cdPipelineIndex;
  var cdNormalizeStepId = _cdP.cdNormalizeStepId;
  var cdMarkPriorDone = _cdP.cdMarkPriorDone;
  var cdSealSteps = _cdP.cdSealSteps;
  var cdApplyStep = _cdP.cdApplyStep;
  var cdPlanSummary = _cdP.cdPlanSummary;
  var cdFormatDuration = _cdP.cdFormatDuration;

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

  // persist normalize 依赖上文 scrub；必须在 CodeDevBeginCard 渲染前注入
  _cdP.setScrubbers({
    cdStripBoilerplate: cdStripBoilerplate,
    cdStripExplorationFromProcess: cdStripExplorationFromProcess,
    cdDedupeThinkText: cdDedupeThinkText,
  });

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
  var resumeWatchRef = useRef(null);
  var streamTokenRef = useRef("");
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
          streamToken: streamTokenRef.current || undefined,
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
    var streamToken = String(opts.streamToken || streamTokenRef.current || "").trim();
    if (streamToken) streamTokenRef.current = streamToken;
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
    cdSnapshotPersist({
      phase: "running",
      jobId: jid,
      streamToken: streamToken || undefined,
    });
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
      if (job.stream_token) {
        streamToken = String(job.stream_token || "").trim() || streamToken;
        if (streamToken) streamTokenRef.current = streamToken;
      }
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
        if (jd && jd.stream_token) {
          streamToken = String(jd.stream_token || "").trim() || streamToken;
          if (streamToken) streamTokenRef.current = streamToken;
        }
        startStream();
      })
      .catch(function () {
        startStream();
      });
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
    function startStream() {
      var streamUrl =
        engineBase() + "/api/code-dev/jobs/" + encodeURIComponent(jid) + "/stream";
      if (streamToken) {
        streamUrl += "?stream_token=" + encodeURIComponent(streamToken);
      }
      fetch(streamUrl, {
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
      if (saved && saved.streamToken) {
        streamTokenRef.current = String(saved.streamToken || "").trim();
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
              streamToken:
                String((saved && saved.streamToken) || jd.stream_token || "").trim() || undefined,
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
              resumeWatchRef.current = {
                jid: foundId,
                streamToken: String(
                  (saved && saved.streamToken) || jd.stream_token || "",
                ).trim(),
              };
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
      var pack = resumeWatchRef.current;
      resumeWatchRef.current = null;
      var jid = typeof pack === "string" ? pack : pack && pack.jid;
      var stok = typeof pack === "object" && pack ? String(pack.streamToken || "").trim() : "";
      if (!jid) return;
      watchJob(jid, { resume: true, streamToken: stok });
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
        var stok = String(d.stream_token || (d.job && d.job.stream_token) || "").trim();
        if (stok) streamTokenRef.current = stok;
        setJobId(jid);
        setPhase("running");
        setLog((d.reply || "已启动") + "\n");
        setResult("");
        if (jid) {
          cdPersistSaveCard(block, props.sessionId, toolCallId, {
            phase: "running",
            jobId: jid,
            streamToken: stok || undefined,
            callId: toolCallId || "",
            sessionId: props.sessionId || "",
            workspace: ws,
            requirement: req,
            goal: goal || req,
            brief: brief,
          });
          watchJob(jid, { streamToken: stok });
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

  ctx.CodeDevBeginCard = CodeDevBeginCard;
}

export function installUsageHelpers(ctx) {
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

function fmtUsageTokens(n) {
  var x = Number(n) || 0;
  if (x >= 1000000) {
    return (x / 1000000).toFixed(2).replace(/\.?0+$/, "") + "M";
  }
  if (x >= 1000) {
    return (x / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  }
  return String(Math.round(x));
}

function fmtUsageTokensTitle(n) {
  return Math.round(Number(n) || 0).toLocaleString("zh-CN");
}

function qualityLabel(q, source) {
  if (q === "provider") return "供应商回传";
  if (q === "session") return "DSH 会话";
  if (q === "sdk") return source === "llm" ? "DSH 会话" : "Cursor SDK";
  if (q === "estimate") return "估算（非真值）";
  return "未回传";
}

function usageNiceMax(v) {
  v = Number(v) || 0;
  if (v <= 0) return 1;
  if (v <= 10) return 10;
  var exp = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / exp) * exp;
}

function usageMd(date) {
  var s = String(date || "");
  return s.length >= 10 ? s.slice(5).replace("-", "/") : s;
}

function usageMonthLabel(ym) {
  var s = String(ym || "");
  if (s.length >= 7) return s.slice(0, 4) + "年" + String(Number(s.slice(5, 7))) + "月";
  return "";
}

function usageShowDayTick(i, n, label, axis) {
  if (axis === "hour") {
    if (n <= 8) return true;
    return i === 0 || i === 8 || i === 15 || i === n - 1;
  }
  if (n <= 8) return true;
  if (i === 0 || i === n - 1) return true;
  var d = String(label || "");
  var dd = d.length >= 2 ? d.slice(-2) : "";
  return dd === "01" || dd === "08" || dd === "15" || dd === "22";
}

function usageChartWidth(n) {
  return Math.max(340, (n || 1) * 44);
}

function usagePlotBox(n) {
  var L = 40, R = 28, T = 8, B = 26, H = 150;
  var W = usageChartWidth(n);
  return { W: W, H: H, L: L, R: R, T: T, B: B, iw: W - L - R, ih: H - T - B };
}

function usageXTickAnchor(i, n) {
  if (n > 1 && i === 0) return "start";
  if (n > 1 && i === n - 1) return "end";
  return "middle";
}

function usageTipShift(xPct) {
  if (xPct >= 82) return "translateX(-100%)";
  if (xPct <= 18) return "translateX(0)";
  return "translateX(-50%)";
}

function usageChartScroll(n, child) {
  return h(
    "div",
    { className: "wb-usage-chart-scroll" },
    h("div", { className: "wb-usage-chart-inner" }, child),
  );
}

function usageAlignMonthScroll(el, idx, n, align) {
  if (!el || n < 1) return;
  var view = el.clientWidth;
  var total = el.scrollWidth;
  if (view < 8 || total <= view + 1) return;
  var i = Math.max(0, Math.min(n - 1, idx | 0));
  var left = align === "start" ? (i / n) * total : ((i + 1) / n) * total - view;
  if (left < 0) left = 0;
  var max = total - view;
  if (left > max) left = max;
  el.scrollLeft = left;
}

function usageHourScrollIndex(hourly) {
  // 个人/企业按日一致：滚到工作时段。Token 高峰尽量落在视窗中部，但起点不低于 08:00（避开无意义的凌晨空窗）。
  var byH = {};
  (hourly || []).forEach(function (r) {
    byH[Number(r.hour)] = r;
  });
  var peak = -1;
  var peakTok = -1;
  for (var hr = 0; hr < 24; hr++) {
    var row = byH[hr] || {};
    var tok = (Number(row.llm_tokens) || 0) + (Number(row.cursor_tokens) || 0);
    if (tok > peakTok) {
      peakTok = tok;
      peak = hr;
    }
  }
  var workStart = 8;
  if (peak < 0 || peakTok <= 0) return workStart;
  var start = peak - 4;
  if (start < workStart) start = workStart;
  if (start > 16) start = 16;
  return start;
}

function usageScrollToFocus(root, dates, focusYmd) {
  if (!root) return;
  var list = dates || [];
  var n = list.length || 1;
  var idx = n - 1;
  var want = String(focusYmd || "").slice(0, 10);
  if (want) {
    for (var i = 0; i < list.length; i++) {
      if (String(list[i].date || "").slice(0, 10) === want) {
        idx = i;
        break;
      }
    }
  }
  var nodes = root.querySelectorAll(".wb-usage-chart-scroll");
  for (var j = 0; j < nodes.length; j++) {
    usageAlignMonthScroll(nodes[j], idx, n);
  }
}

function usageScrollToHour(root, hourly) {
  if (!root) return;
  var idx = usageHourScrollIndex(hourly);
  function apply() {
    var nodes = root.querySelectorAll(".wb-usage-chart-scroll");
    for (var j = 0; j < nodes.length; j++) {
      usageAlignMonthScroll(nodes[j], idx, 24, "start");
    }
  }
  apply();
  // 图表宽度可能在首帧后才算准，多刷一次保证个人/企业都滚到同一工作窗
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(function () {
      apply();
      requestAnimationFrame(apply);
    });
  } else {
    setTimeout(apply, 0);
  }
}

function usageTodayYmd() {
  try {
    return new Date().toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 10);
  } catch (e) {
    return new Date().toISOString().slice(0, 10);
  }
}

function usageAddDays(ymd, delta) {
  var parts = String(ymd || "").split("-");
  if (parts.length < 3) return usageTodayYmd();
  var d = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]) + Number(delta || 0)));
  return d.toISOString().slice(0, 10);
}

function usageKpiDayLabel(ymd) {
  var day = String(ymd || "").slice(0, 10);
  var md = usageMd(day);
  if (!md) return "今日";
  return day === usageTodayYmd() ? "今日 " + md : md;
}

function usageCatmullPath(pts) {
  if (!pts.length) return "";
  var d = "M " + pts[0].x.toFixed(2) + " " + pts[0].y.toFixed(2);
  if (pts.length === 1) return d;
  if (pts.length === 2) {
    return d + " L " + pts[1].x.toFixed(2) + " " + pts[1].y.toFixed(2);
  }
  for (var i = 0; i < pts.length - 1; i++) {
    var p0 = pts[Math.max(0, i - 1)];
    var p1 = pts[i];
    var p2 = pts[i + 1];
    var p3 = pts[Math.min(pts.length - 1, i + 2)];
    var c1x = p1.x + (p2.x - p0.x) / 6;
    var c1y = p1.y + (p2.y - p0.y) / 6;
    var c2x = p2.x - (p3.x - p1.x) / 6;
    var c2y = p2.y - (p3.y - p1.y) / 6;
    d += " C " + c1x.toFixed(2) + " " + c1y.toFixed(2) + ", " +
      c2x.toFixed(2) + " " + c2y.toFixed(2) + ", " +
      p2.x.toFixed(2) + " " + p2.y.toFixed(2);
  }
  return d;
}

function usageCurveSvg(values, labels, fill, stroke, gid, axis) {
  var n = values.length || 1;
  var box = usagePlotBox(n);
  var W = box.W, H = box.H, L = box.L, R = box.R, T = box.T, iw = box.iw, ih = box.ih;
  var max = usageNiceMax(Math.max.apply(null, [0].concat(values)));
  function xAt(i) { return L + (n <= 1 ? iw / 2 : (i * iw) / (n - 1)); }
  function yAt(v) { return T + ih - (max ? (v / max) * ih : 0); }
  var pts = values.map(function (v, i) { return { x: xAt(i), y: yAt(v) }; });
  var line = usageCatmullPath(pts);
  var baseY = (T + ih).toFixed(2);
  var area = line
    ? line + " L " + xAt(n - 1).toFixed(2) + " " + baseY + " L " + xAt(0).toFixed(2) + " " + baseY + " Z"
    : "";
  var clip = "uc-" + String(gid || "g").replace(/[^a-zA-Z0-9_-]/g, "");
  var grid = [0, 0.5, 1].map(function (f) {
    var yy = yAt(max * f);
    var label = f === 0 ? "0" : String(Math.round(max * f));
    return '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="#e5e7eb"/>' +
      '<text x="' + (L - 6) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="#94a3b8">' + label + "</text>";
  }).join("");
  var xlabs = labels.map(function (lb, i) {
    if (!usageShowDayTick(i, n, lb, axis)) return "";
    return '<text x="' + xAt(i) + '" y="' + (H - 8) + '" text-anchor="' + usageXTickAnchor(i, n) + '" font-size="10" fill="#94a3b8">' + String(lb) + "</text>";
  }).join("");
  return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="150" preserveAspectRatio="none">' +
    "<defs><linearGradient id=\"" + clip + "-fg\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">" +
    '<stop offset="0%" stop-color="' + stroke + '" stop-opacity="0.38"/>' +
    '<stop offset="100%" stop-color="' + stroke + '" stop-opacity="0.04"/>' +
    "</linearGradient>" +
    '<clipPath id="' + clip + '"><rect x="' + L + '" y="' + T + '" width="' + iw + '" height="' + ih + '"/></clipPath></defs>' +
    grid +
    '<g clip-path="url(#' + clip + ')">' +
    '<path d="' + area + '" fill="url(#' + clip + '-fg)"/>' +
    '<path d="' + line + '" fill="none" stroke="' + stroke + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
    "</g>" + xlabs + "</svg>";
}

function UsageCurveChart(props) {
  var hoverState = useState(-1);
  var hover = hoverState[0];
  var setHover = hoverState[1];
  var values = props.values || [];
  var labels = props.labels || [];
  var axis = props.axis === "hour" ? "hour" : "day";
  var n = values.length || 1;
  var box = usagePlotBox(n);
  var W = box.W, H = box.H, L = box.L, T = box.T, iw = box.iw, ih = box.ih;
  var max = usageNiceMax(Math.max.apply(null, [0].concat(values)));
  function xAt(i) { return L + (n <= 1 ? iw / 2 : (i * iw) / (n - 1)); }
  function yAt(v) { return T + ih - (max ? (v / max) * ih : 0); }
  function onMove(ev) {
    var rect = ev.currentTarget.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var scale = rect.width / W;
    var t = n <= 1 ? 0 : (x / scale - L) / Math.max(1, iw);
    var i = Math.round(Math.max(0, Math.min(1, t)) * (n - 1));
    setHover(i);
  }
  var xPct = (xAt(hover) / W) * 100;
  var tip = hover >= 0 && hover < n
    ? {
      label: labels[hover] || "",
      value: values[hover] || 0,
      left: xPct,
      tipShift: usageTipShift(xPct),
      top: (yAt(values[hover] || 0) / H) * 100,
      gTop: (T / H) * 100,
      gH: (ih / H) * 100,
    }
    : null;
  return h(
    "div",
    {
      className: "wb-usage-chart-plot",
      style: { color: props.stroke },
      onMouseMove: onMove,
      onMouseLeave: function () { setHover(-1); },
    },
    h("div", { dangerouslySetInnerHTML: { __html: usageCurveSvg(values, labels, props.fill, props.stroke, props.gid, axis) } }),
    tip
      ? h("div", { className: "wb-usage-guide", style: { left: tip.left + "%", top: tip.gTop + "%", height: tip.gH + "%" } })
      : null,
    tip
      ? h("div", { className: "wb-usage-dot", style: { left: tip.left + "%", top: tip.top + "%" } })
      : null,
    tip
      ? h(
        "div",
        { className: "wb-usage-tip", style: { left: tip.left + "%", transform: tip.tipShift } },
        h("div", { className: "d" }, String(tip.label)),
        "请求 " + String(tip.value),
      )
      : null,
  );
}

function usageStackSvg(rows, colors, hoverIdx, axis) {
  var n = rows.length || 1;
  var box = usagePlotBox(n);
  var W = box.W, H = box.H, L = box.L, R = box.R, T = box.T, iw = box.iw, ih = box.ih;
  var totals = rows.map(function (r) { return r.hit + r.miss + r.out; });
  var max = usageNiceMax(Math.max.apply(null, [0].concat(totals)));
  var slot = iw / n;
  var bw = Math.max(2, slot * 0.58);
  var hi = hoverIdx == null ? -1 : hoverIdx;
  var grid = [0, 0.5, 1].map(function (f) {
    var yy = T + ih - f * ih;
    var label = f === 0 ? "0" : fmtUsageTokens(max * f);
    return '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="#e5e7eb"/>' +
      '<text x="' + (L - 6) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="#94a3b8">' + label + "</text>";
  }).join("");
  var bars = rows.map(function (r, i) {
    var cx = L + (i + 0.5) * slot;
    var x0 = cx - bw / 2;
    var y = T + ih;
    var segs = [
      [r.out, colors.out],
      [r.miss, colors.miss],
      [r.hit, colors.hit],
    ];
    var hiRect = i === hi
      ? '<rect x="' + (L + i * slot).toFixed(1) + '" y="' + T + '" width="' + slot.toFixed(1) +
        '" height="' + ih + '" fill="rgba(15,23,42,0.06)"/>'
      : "";
    var rects = segs.map(function (seg) {
      var v = seg[0], c = seg[1];
      var hh = max ? (v / max) * ih : 0;
      y -= hh;
      if (hh <= 0.4) return "";
      return '<rect x="' + x0.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + hh.toFixed(1) + '" fill="' + c + '"/>';
    }).join("");
    var showLab = usageShowDayTick(i, n, r.label, axis);
    var lab = showLab
      ? '<text x="' + cx + '" y="' + (H - 8) + '" text-anchor="' + usageXTickAnchor(i, n) + '" font-size="10" fill="#94a3b8">' + r.label + "</text>"
      : "";
    return hiRect + rects + lab;
  }).join("");
  return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="150" preserveAspectRatio="none">' +
    grid + bars + "</svg>";
}

function UsageStackChart(props) {
  var hoverState = useState(-1);
  var hover = hoverState[0];
  var setHover = hoverState[1];
  var rows = props.rows || [];
  var axis = props.axis === "hour" ? "hour" : "day";
  var n = rows.length || 1;
  var box = usagePlotBox(n);
  var W = box.W, H = box.H, L = box.L, T = box.T, iw = box.iw, ih = box.ih;
  function onMove(ev) {
    var rect = ev.currentTarget.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var scale = rect.width / W;
    var t = (x / scale - L) / Math.max(1, iw);
    var i = Math.floor(Math.max(0, Math.min(0.999, t)) * n);
    setHover(i);
  }
  var row = hover >= 0 && hover < n ? rows[hover] : null;
  var xPct = ((L + (hover + 0.5) * (iw / n)) / W) * 100;
  var tip = row
    ? {
      left: xPct,
      tipShift: usageTipShift(xPct),
      colL: ((L + hover * (iw / n)) / W) * 100,
      colW: ((iw / n) / W) * 100,
      gTop: (T / H) * 100,
      gH: (ih / H) * 100,
    }
    : null;
  return h(
    "div",
    {
      className: "wb-usage-chart-plot",
      onMouseMove: onMove,
      onMouseLeave: function () { setHover(-1); },
    },
    h("div", { dangerouslySetInnerHTML: { __html: usageStackSvg(rows, props.colors, hover, axis) } }),
    tip
      ? h("div", { className: "wb-usage-colhi", style: { left: tip.colL + "%", width: tip.colW + "%", top: tip.gTop + "%", height: tip.gH + "%" } })
      : null,
    row
      ? h(
        "div",
        { className: "wb-usage-tip", style: { left: tip.left + "%", transform: tip.tipShift } },
        h("div", { className: "d" }, String(row.label || "")),
        h("div", null, "合计 " + fmtUsageTokens((row.hit || 0) + (row.miss || 0) + (row.out || 0))),
        h("div", null, "命中缓存 " + fmtUsageTokens(row.hit)),
        h("div", null, "未命中 " + fmtUsageTokens(row.miss)),
        h("div", null, "输出 " + fmtUsageTokens(row.out)),
      )
      : null,
  );
}

function usageHourRange(h) {
  var a = (h < 10 ? "0" : "") + h + ":00";
  if (h >= 23) return "23:00～24:00";
  var n = h + 1;
  return a + "～" + (n < 10 ? "0" : "") + n + ":00";
}

function usageHourCombinedRows(hourly) {
  var byH = {};
  (hourly || []).forEach(function (r) {
    byH[Number(r.hour)] = r;
  });
  var out = [];
  for (var h = 0; h < 24; h++) {
    var r = byH[h] || {};
    out.push({
      key: h,
      range: usageHourRange(h),
      tick: null,
      llm_tokens: Number(r.llm_tokens) || 0,
      llm_calls: Number(r.llm_calls) || 0,
      cursor_tokens: Number(r.cursor_tokens) || 0,
      cursor_calls: Number(r.cursor_calls) || 0,
    });
  }
  return out;
}

function usageDayCombinedRows(daily) {
  return (daily || []).map(function (r) {
    var date = String(r.date || "").slice(0, 10);
    var md = usageMd(date) || date;
    return {
      key: date,
      range: md,
      tick: md,
      llm_tokens: Number(r.llm_tokens) || 0,
      llm_calls: Number(r.llm_calls) || 0,
      cursor_tokens: Number(r.cursor_tokens) || 0,
      cursor_calls: Number(r.cursor_calls) || 0,
    };
  });
}

var USAGE_HOUR_GEO = { W: 560, H: 200, L: 48, R: 14, T: 16, B: 30 };

function usageDualCombinedSvg(rows, hoverIdx, axis) {
  var g = USAGE_HOUR_GEO;
  var W = g.W, H = g.H, L = g.L, R = g.R, T = g.T, B = g.B;
  var iw = W - L - R, ih = H - T - B;
  var n = Math.max(1, (rows || []).length);
  var llmVals = [];
  var curVals = [];
  for (var i = 0; i < n; i++) {
    llmVals.push((rows[i] && rows[i].llm_tokens) || 0);
    curVals.push((rows[i] && rows[i].cursor_tokens) || 0);
  }
  var max = usageNiceMax(Math.max.apply(null, [0].concat(llmVals, curVals)));
  var slot = iw / n;
  // 同日/同时段双柱贴合无间隙；组间留一点空隙区分相邻日
  var outer = Math.max(1.5, slot * 0.18);
  var pairW = Math.max(4, slot - outer);
  var bw = pairW / 2;
  var hi = hoverIdx == null ? -1 : hoverIdx;
  var cLlm = "#ff5a1f";
  var cCur = "#14b8a6";
  var grid = [0, 0.5, 1].map(function (f) {
    var yy = T + ih - f * ih;
    var label = f === 0 ? "0" : fmtUsageTokens(max * f);
    return '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="#eceef2"/>' +
      '<text x="' + (L - 8) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="#94a3b8">' + label + "</text>";
  }).join("");
  var hourMarks = { 0: "00:00", 8: "08:00", 15: "15:00", 23: "23:00" };
  var bars = "";
  for (var j = 0; j < n; j++) {
    var slotX = L + j * slot;
    var cx = slotX + slot / 2;
    if (j === hi) {
      bars += '<rect x="' + slotX.toFixed(1) + '" y="' + T + '" width="' + slot.toFixed(1) +
        '" height="' + ih + '" fill="rgba(15,23,42,0.04)"/>';
    }
    var xL = cx - pairW / 2;
    var xC = xL + bw;
    var hL = max ? (llmVals[j] / max) * ih : 0;
    var hC = max ? (curVals[j] / max) * ih : 0;
    if (hL > 0.6) {
      bars += '<rect x="' + xL.toFixed(1) + '" y="' + (T + ih - hL).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + hL.toFixed(1) + '" fill="' + cLlm + '"/>';
    }
    if (hC > 0.6) {
      bars += '<rect x="' + xC.toFixed(1) + '" y="' + (T + ih - hC).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + hC.toFixed(1) + '" fill="' + cCur + '"/>';
    }
    var tick = "";
    if (axis === "day") {
      if (usageShowDayTick(j, n, rows[j] && rows[j].tick)) {
        tick = String((rows[j] && rows[j].tick) || "");
      }
    } else if (hourMarks[j]) {
      tick = hourMarks[j];
    }
    if (tick) {
      bars += '<text x="' + cx + '" y="' + (H - 8) + '" text-anchor="middle" font-size="10" fill="#94a3b8">' + tick + "</text>";
    }
  }
  return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="200" preserveAspectRatio="none">' + grid + bars + "</svg>";
}

function UsageDualCombinedChart(props) {
  var hoverState = useState(-1);
  var hover = hoverState[0];
  var setHover = hoverState[1];
  var rows = props.rows || [];
  var axis = props.axis === "day" ? "day" : "hour";
  var n = Math.max(1, rows.length);
  var g = USAGE_HOUR_GEO;
  var W = g.W, H = g.H, L = g.L, R = g.R, T = g.T, B = g.B;
  var iw = W - L - R, ih = H - T - B;
  function onMove(ev) {
    var rect = ev.currentTarget.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var scale = rect.width / W;
    var t = (x / scale - L) / Math.max(1, iw);
    var i = Math.floor(Math.max(0, Math.min(0.999, t)) * n);
    setHover(i);
  }
  var row = hover >= 0 && hover < rows.length ? rows[hover] : null;
  var tip = row
    ? {
      left: Math.max(14, Math.min(86, ((L + (hover + 0.5) * (iw / n)) / W) * 100)),
      gTop: (T / H) * 100,
      gH: (ih / H) * 100,
    }
    : null;
  return h(
    "div",
    {
      className: "wb-usage-hour-plot",
      onMouseMove: onMove,
      onMouseLeave: function () { setHover(-1); },
    },
    h("div", { dangerouslySetInnerHTML: { __html: usageDualCombinedSvg(rows, hover, axis) } }),
    tip
      ? h("div", { className: "wb-usage-hour-guide", style: { left: tip.left + "%", top: tip.gTop + "%", height: tip.gH + "%" } })
      : null,
    row
      ? h(
        "div",
        { className: "wb-usage-hour-tip wb-usage-hour-tip-dual", style: { left: tip.left + "%" } },
        h("span", { className: "r" }, String(row.range || "")),
        h("span", { className: "v llm" }, "LLM " + fmtUsageTokens(row.llm_tokens)),
        h("span", { className: "c" }, String(row.llm_calls || 0) + " 次"),
        h("span", { className: "v cur" }, "Cursor " + fmtUsageTokens(row.cursor_tokens)),
        h("span", { className: "c" }, String(row.cursor_calls || 0) + " 次"),
      )
      : null,
  );
}

function usageHourCombinedCard(title, series, day, opts) {
  var monthMode = !!(opts && opts.monthMode);
  var rows = monthMode
    ? usageDayCombinedRows(series)
    : usageHourCombinedRows(series);
  var sumLlmTok = rows.reduce(function (a, r) { return a + r.llm_tokens; }, 0);
  var sumCurTok = rows.reduce(function (a, r) { return a + r.cursor_tokens; }, 0);
  var sumLlmCalls = rows.reduce(function (a, r) { return a + r.llm_calls; }, 0);
  var sumCurCalls = rows.reduce(function (a, r) { return a + r.cursor_calls; }, 0);
  var when = String(day || "").slice(0, 10) || "所选日期";
  var monthLab = usageMonthLabel((opts && opts.monthLabel) || when) || String((opts && opts.monthLabel) || when).slice(0, 7);
  var rangeLab = monthMode
    ? (monthLab + " 逐日")
    : (when + " 00:00–24:00");
  return h(
    "div",
    { className: "wb-set-card" },
    h("h3", null, title),
    h(
      "div",
      { className: "body" },
      h(
        "div",
        { className: "wb-usage-hour-sub" },
        rangeLab +
          " · LLM " +
          sumLlmCalls +
          " 次 / " +
          fmtUsageTokens(sumLlmTok) +
          " · Cursor " +
          sumCurCalls +
          " 次 / " +
          fmtUsageTokens(sumCurTok),
      ),
      h(
        "div",
        { className: "wb-usage-legend", style: { marginBottom: "8px" } },
        h("span", null, h("i", { style: { background: "#ff5a1f" } }), "LLM"),
        h("span", null, h("i", { style: { background: "#14b8a6" } }), "Cursor 写码"),
      ),
      h(UsageDualCombinedChart, { rows: rows, axis: monthMode ? "day" : "hour" }),
    ),
  );
}

function usageKpiCard(title, calls, tokens) {
  return h(
    "div",
    { className: "wb-usage-kpi" },
    h("div", { className: "k" }, title),
    h("div", { className: "row" }, h("span", { className: "t" }, "API 请求次数"), h("span", { className: "n" }, String(calls || 0))),
    h("div", { className: "row" }, h("span", { className: "t" }, "Token 消耗"), h("span", { className: "n", title: fmtUsageTokensTitle(tokens) }, fmtUsageTokens(tokens))),
  );
}

function usageTodayKpis(today, dateLabel) {
  var t = today || {};
  var llmT = t.llm || {};
  var curT = t.cursor || {};
  var day = dateLabel || "今日";
  return h(
    "div",
    { className: "wb-usage-kpis" },
    usageKpiCard(day + " · LLM", llmT.calls, llmT.tokens),
    usageKpiCard(day + " · Cursor 写码", curT.calls, curT.tokens),
  );
}

function usageMeterNode(title, subtitle, series, prefix, palette, extraNote, axis) {
  var axisMode = axis === "hour" ? "hour" : "day";
  var rows = series || [];
  if (axisMode === "hour") {
    var byH = {};
    rows.forEach(function (r) {
      byH[Number(r.hour)] = r;
    });
    rows = [];
    for (var hr = 0; hr < 24; hr++) {
      rows.push(byH[hr] || { hour: hr });
    }
  }
  var calls = rows.map(function (d) { return Number(d[prefix + "calls"]) || 0; });
  var labels = rows.map(function (d, i) {
    if (axisMode === "hour") {
      var hh = d.hour != null ? Number(d.hour) : i;
      return (hh < 10 ? "0" : "") + hh + ":00";
    }
    return usageMd(d.date);
  });
  var stacks = rows.map(function (d, i) {
    return {
      label: labels[i],
      hit: Number(d[prefix + "cache_hit"]) || 0,
      miss: Number(d[prefix + "cache_miss"]) || 0,
      out: Number(d[prefix + "output"]) || 0,
    };
  });
  var sumCalls = calls.reduce(function (a, b) { return a + b; }, 0);
  var sumTok = rows.reduce(function (a, d) { return a + (Number(d[prefix + "tokens"]) || 0); }, 0);
  return h(
    "section",
    { className: "wb-usage-meter" },
    h("div", { className: "wb-usage-meter-title" }, title),
    h("div", { className: "wb-usage-meter-sub" }, subtitle + (extraNote ? " · " + extraNote : "")),
    h(
      "div",
      { className: "wb-usage-meter-grid" },
      h(
        "div",
        { className: "wb-usage-chart" },
        h("div", { className: "wb-usage-chart-head" }, h("span", { className: "t" }, "API 请求次数"), h("span", { className: "n" }, String(sumCalls))),
        usageChartScroll(calls.length, h(UsageCurveChart, { values: calls, labels: labels, fill: palette.fill, stroke: palette.stroke, gid: prefix, axis: axisMode })),
      ),
      h(
        "div",
        { className: "wb-usage-chart" },
        h("div", { className: "wb-usage-chart-head" }, h("span", { className: "t" }, "Tokens"), h("span", { className: "n", title: fmtUsageTokensTitle(sumTok) }, fmtUsageTokens(sumTok))),
        usageChartScroll(stacks.length, h(UsageStackChart, { rows: stacks, colors: palette, axis: axisMode })),
        h(
          "div",
          { className: "wb-usage-legend" },
          h("span", null, h("i", { style: { background: palette.hit } }), "输入（命中缓存）"),
          h("span", null, h("i", { style: { background: palette.miss } }), "输入（未命中缓存）"),
          h("span", null, h("i", { style: { background: palette.out } }), "输出"),
        ),
      ),
    ),
  );
}

function usageMonthRangeFromDay(ymd) {
  var s = String(ymd || usageTodayYmd());
  var y = Number(s.slice(0, 4));
  var m = Number(s.slice(5, 7));
  if (!y || !m) {
    s = usageTodayYmd();
    y = Number(s.slice(0, 4));
    m = Number(s.slice(5, 7));
  }
  var from = s.slice(0, 7) + "-01";
  var last = new Date(y, m, 0).getDate();
  var to = s.slice(0, 7) + "-" + String(last).padStart(2, "0");
  var today = usageTodayYmd();
  if (to > today) to = today;
  return { from: from, to: to, label: s.slice(0, 7) };
}

function usagePeopleHBars(rows) {
  var list = (rows || []).slice().sort(function (a, b) {
    var ta = (Number(a.llm_tokens) || 0) + (Number(a.cursor_tokens) || 0);
    var tb = (Number(b.llm_tokens) || 0) + (Number(b.cursor_tokens) || 0);
    if (tb !== ta) return tb - ta;
    return String(a.display_name || a.username || "").localeCompare(
      String(b.display_name || b.username || ""),
      "zh",
    );
  });
  var maxTok = 0;
  list.forEach(function (r) {
    var llm = Number(r.llm_tokens) || 0;
    var cur = Number(r.cursor_tokens) || 0;
    if (llm > maxTok) maxTok = llm;
    if (cur > maxTok) maxTok = cur;
  });
  if (!list.length) {
    return h("p", { className: "wb-usage-people-sub" }, "暂无员工账号。");
  }
  function barPct(n) {
    if (maxTok <= 0) return 0;
    var v = Number(n) || 0;
    if (v <= 0) return 0;
    return Math.max(2, Math.round((v / maxTok) * 100));
  }
  return h(
    "div",
    { className: "wb-usage-hbar" },
    h(
      "div",
      { className: "wb-usage-hbar-legend" },
      h("span", null, h("i", { style: { background: "#3b82f6" } }), "LLM Token"),
      h("span", null, h("i", { style: { background: "#14b8a6" } }), "Cursor 写码 Token"),
    ),
    list.map(function (r, idx) {
      var name = r.display_name || r.username || r.user_id || "—";
      var llmTok = Number(r.llm_tokens) || 0;
      var curTok = Number(r.cursor_tokens) || 0;
      var llmCalls = Number(r.llm_calls) || 0;
      var curCalls = Number(r.cursor_calls) || 0;
      var total = llmTok + curTok;
      return h(
        "div",
        { className: "wb-usage-hbar-person", key: String(r.user_id || name) + "|" + idx },
        h(
          "div",
          { className: "wb-usage-hbar-head" },
          h("div", { className: "wb-usage-hbar-name", title: name }, name),
          h(
            "div",
            {
              className: "wb-usage-hbar-total",
              title: "LLM+Cursor 合计 " + fmtUsageTokensTitle(total),
            },
            "合计 " + fmtUsageTokens(total),
          ),
        ),
        h(
          "div",
          { className: "wb-usage-hbar-row" },
          h("div", { className: "wb-usage-hbar-lab" }, "LLM"),
          h(
            "div",
            { className: "wb-usage-hbar-track" },
            h("div", {
              className: "wb-usage-hbar-fill llm",
              style: { width: barPct(llmTok) + "%" },
              title: fmtUsageTokensTitle(llmTok) + " · " + llmCalls + " 次",
            }),
          ),
          h(
            "div",
            { className: "wb-usage-hbar-val", title: fmtUsageTokensTitle(llmTok) + " · API " + llmCalls + " 次" },
            fmtUsageTokens(llmTok),
          ),
        ),
        h(
          "div",
          { className: "wb-usage-hbar-row" },
          h("div", { className: "wb-usage-hbar-lab" }, "Cursor"),
          h(
            "div",
            { className: "wb-usage-hbar-track" },
            h("div", {
              className: "wb-usage-hbar-fill cursor",
              style: { width: barPct(curTok) + "%" },
              title: fmtUsageTokensTitle(curTok) + " · " + curCalls + " 次",
            }),
          ),
          h(
            "div",
            {
              className: "wb-usage-hbar-val",
              title: fmtUsageTokensTitle(curTok) + " · " + curCalls + " 次",
            },
            fmtUsageTokens(curTok),
          ),
        ),
      );
    }),
  );
}

function usagePeopleBarsNode(title, subtitle, rows) {
  return h(
    "section",
    { className: "wb-usage-people" },
    h("div", { className: "wb-usage-people-title" }, title),
    h("div", { className: "wb-usage-people-sub" }, subtitle),
    usagePeopleHBars(rows),
  );
}

  ctx.fmtUsageTokens = fmtUsageTokens;
  ctx.fmtUsageTokensTitle = fmtUsageTokensTitle;
  ctx.qualityLabel = qualityLabel;
  ctx.usageNiceMax = usageNiceMax;
  ctx.usageMd = usageMd;
  ctx.usageMonthLabel = usageMonthLabel;
  ctx.usageShowDayTick = usageShowDayTick;
  ctx.usageChartWidth = usageChartWidth;
  ctx.usagePlotBox = usagePlotBox;
  ctx.usageXTickAnchor = usageXTickAnchor;
  ctx.usageTipShift = usageTipShift;
  ctx.usageChartScroll = usageChartScroll;
  ctx.usageAlignMonthScroll = usageAlignMonthScroll;
  ctx.usageHourScrollIndex = usageHourScrollIndex;
  ctx.usageScrollToFocus = usageScrollToFocus;
  ctx.usageScrollToHour = usageScrollToHour;
  ctx.usageTodayYmd = usageTodayYmd;
  ctx.usageAddDays = usageAddDays;
  ctx.usageKpiDayLabel = usageKpiDayLabel;
  ctx.usageCatmullPath = usageCatmullPath;
  ctx.usageCurveSvg = usageCurveSvg;
  ctx.UsageCurveChart = UsageCurveChart;
  ctx.usageStackSvg = usageStackSvg;
  ctx.UsageStackChart = UsageStackChart;
  ctx.usageHourRange = usageHourRange;
  ctx.usageHourCombinedRows = usageHourCombinedRows;
  ctx.usageDayCombinedRows = usageDayCombinedRows;
  ctx.usageDualCombinedSvg = usageDualCombinedSvg;
  ctx.UsageDualCombinedChart = UsageDualCombinedChart;
  ctx.usageHourCombinedCard = usageHourCombinedCard;
  ctx.usageKpiCard = usageKpiCard;
  ctx.usageTodayKpis = usageTodayKpis;
  ctx.usageMeterNode = usageMeterNode;
  ctx.usageMonthRangeFromDay = usageMonthRangeFromDay;
  ctx.usagePeopleHBars = usagePeopleHBars;
  ctx.usagePeopleBarsNode = usagePeopleBarsNode;
}

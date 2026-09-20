export function installPreamble(ctx) {
  var React = ctx.React, h = ctx.h, useState = ctx.useState, useEffect = ctx.useEffect,
      useLayoutEffect = ctx.useLayoutEffect, useRef = ctx.useRef, useMemo = ctx.useMemo;

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

/** 与引擎 SPA / simplified 对齐的本机会话（:3081 与 :8000 localStorage 不同源，各存一份） */
var AUTH_LS_KEY = "mes_auth_session";
var AUTH_ENTERPRISES = [
  { key: "jsry", label: "江苏软云", code: "" },
  { key: "jxzr", label: "江西中软", code: "" },
  { key: "qhzr", label: "前海中软", code: "" },
];
var AUTH_EVENT = "wb-auth-changed";

function readAuthSession() {
  try {
    var raw = localStorage.getItem(AUTH_LS_KEY);
    if (!raw) return null;
    var data = JSON.parse(raw);
    if (!data || !data.access_token) return null;
    if (data.expires_at && Date.now() / 1000 > Number(data.expires_at) - 30) {
      try {
        localStorage.removeItem(AUTH_LS_KEY);
      } catch (e0) {}
      return null;
    }
    return data;
  } catch (e1) {
    return null;
  }
}
function writeAuthSession(session) {
  try {
    if (session && session.access_token) localStorage.setItem(AUTH_LS_KEY, JSON.stringify(session));
    else localStorage.removeItem(AUTH_LS_KEY);
  } catch (e2) {}
  try {
    window.dispatchEvent(new CustomEvent(AUTH_EVENT));
  } catch (e3) {}
}
function authHeaders(extra) {
  var headers = Object.assign({}, extra || {});
  var s = readAuthSession();
  if (s && s.access_token) headers.Authorization = "Bearer " + s.access_token;
  return headers;
}
function notifyAuthChanged() {
  try {
    window.dispatchEvent(new CustomEvent(AUTH_EVENT));
  } catch (e4) {}
}
function doAppLogout() {
  return fetch(engineBase() + "/api/auth/logout", {
    method: "POST",
    headers: authHeaders(),
  })
    .catch(function () {})
    .then(function () {
      writeAuthSession(null);
    });
}

/** 一体包走 Electron 原生选目录，避免 osascript→Finder 报 -1743。 */
function pickLocalFolder(prompt, signal) {
  var p = prompt || "选择工程目录";
  try {
    var desk = typeof window !== "undefined" ? window.workbuddyDesktop : null;
    if (desk && typeof desk.pickFolder === "function") {
      return Promise.resolve(desk.pickFolder(p)).then(function (d) {
        if (d && typeof d === "object") return d;
        return { ok: false, path: "", error: "选文件夹失败" };
      });
    }
  } catch (e0) {}
  return fetch(engineBase() + "/api/pick-folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: p }),
    signal: signal,
  }).then(function (r) {
    return r.json();
  });
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

  ctx.engineHost = engineHost;
  ctx.enginePort = enginePort;
  ctx.engineBase = engineBase;
  ctx.AUTH_LS_KEY = AUTH_LS_KEY;
  ctx.AUTH_ENTERPRISES = AUTH_ENTERPRISES;
  ctx.AUTH_EVENT = AUTH_EVENT;
  ctx.readAuthSession = readAuthSession;
  ctx.writeAuthSession = writeAuthSession;
  ctx.authHeaders = authHeaders;
  ctx.notifyAuthChanged = notifyAuthChanged;
  ctx.doAppLogout = doAppLogout;
  ctx.pickLocalFolder = pickLocalFolder;
  ctx.issueHitl = issueHitl;
  ctx.discoverEngine = discoverEngine;
}

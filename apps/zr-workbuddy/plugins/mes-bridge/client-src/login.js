export function installLogin(ctx) {
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

function WorkBuddyLoginForm(props) {
  ensureCss();
  var onSuccess = props && props.onSuccess;
  var busyState = useState(false);
  var busy = busyState[0];
  var setBusy = busyState[1];
  var authErrState = useState((props && props.initialError) || "");
  var authErr = authErrState[0];
  var setAuthErr = authErrState[1];
  var loginUserState = useState("");
  var loginUser = loginUserState[0];
  var setLoginUser = loginUserState[1];
  var loginPassState = useState("");
  var loginPass = loginPassState[0];
  var setLoginPass = loginPassState[1];
  var entKeyState = useState("jxzr");
  var entKey = entKeyState[0];
  var setEntKey = entKeyState[1];
  var entOpenState = useState(false);
  var entOpen = entOpenState[0];
  var setEntOpen = entOpenState[1];
  function selectedEnt() {
    return AUTH_ENTERPRISES.find(function (e) { return e.key === entKey; }) || AUTH_ENTERPRISES[1];
  }
  function doLogin() {
    var u = (loginUser || "").trim();
    var p = loginPass || "";
    if (!u || !p) {
      setAuthErr("请输入账号和密码");
      return;
    }
    setAuthErr("");
    setBusy(true);
    fetch(engineBase() + "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: u,
        password: p,
        enterprise_code: String(selectedEnt().code || "").trim(),
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok || !d.token) throw new Error((d && d.detail) || "登录失败");
        writeAuthSession({
          access_token: d.token,
          token_type: d.token_type || "Bearer",
          username: (d.user && d.user.username) || u,
          display_name: (d.user && d.user.display_name) || u,
          user_id: (d.user && d.user.id) || "",
          enterprise_code: String(selectedEnt().code || "").trim(),
          expires_at: d.expires_at,
        });
        setLoginPass("");
        if (typeof onSuccess === "function") onSuccess(d.user || null);
      })
      .catch(function (err) {
        writeAuthSession(null);
        setAuthErr(err && err.message ? err.message : String(err));
      })
      .finally(function () {
        setBusy(false);
      });
  }
  var logoUrl = engineBase() + "/zr-logo.svg";
  return h(
    "div",
    { className: "wb-login-card" },
    h(
      "div",
      { className: "wb-login-brand" },
      h("div", { className: "brand-icon", "aria-hidden": "true" }, h("img", { src: logoUrl, alt: "" })),
      h("h1", null, "ZR WorkBuddy"),
      h("p", null, "你的工作搭档 · 登录 ZR WorkBuddy"),
    ),
    h(
      "form",
      {
        className: "wb-login-form",
        onSubmit: function (ev) {
          ev.preventDefault();
          doLogin();
        },
      },
      h(
        "div",
        { className: "field" },
        h("span", null, "企业编码"),
        h(
          "div",
          { className: "ent-select" + (entOpen ? " open" : "") },
          h(
            "button",
            {
              type: "button",
              className: "ent-trigger",
              "aria-expanded": entOpen,
              onClick: function () {
                setEntOpen(!entOpen);
              },
            },
            h("span", null, selectedEnt().label),
          ),
          h(
            "ul",
            { className: "ent-menu", role: "listbox" },
            AUTH_ENTERPRISES.map(function (item) {
              return h(
                "li",
                {
                  key: item.key,
                  role: "option",
                  className: "ent-option" + (item.key === entKey ? " active" : ""),
                  onMouseDown: function (ev) {
                    ev.preventDefault();
                    setEntKey(item.key);
                    setEntOpen(false);
                  },
                },
                item.label,
              );
            }),
          ),
        ),
      ),
      h(
        "label",
        { className: "field" },
        h("span", null, "账号"),
        h("input", {
          type: "text",
          autoComplete: "username",
          placeholder: "账号",
          required: true,
          value: loginUser,
          onChange: function (ev) {
            setLoginUser(ev.target.value);
          },
        }),
      ),
      h(
        "label",
        { className: "field" },
        h("span", null, "密码"),
        h("input", {
          type: "password",
          autoComplete: "current-password",
          placeholder: "密码",
          required: true,
          value: loginPass,
          onChange: function (ev) {
            setLoginPass(ev.target.value);
          },
        }),
      ),
      authErr ? h("p", { className: "error" }, authErr) : null,
      h("button", { className: "submit", type: "submit", disabled: busy }, busy ? "登录中…" : "登录"),
    ),
    h("p", { className: "wb-login-hint" }, "本页是 ZR WorkBuddy 登录，与系统配置里上传的 MES 接口文档无关。"),
  );
}

/** :3081 进应用全屏登录挡板（对齐 simplified；不改 DSH 内核） */
function WorkBuddyAppLoginGate() {
  ensureCss();
  var readyState = useState(false);
  var ready = readyState[0];
  var setReady = readyState[1];
  var authedState = useState(false);
  var authed = authedState[0];
  var setAuthed = authedState[1];
  var errState = useState("");
  var errMsg = errState[0];
  var setErrMsg = errState[1];

  function refresh() {
    var sess = readAuthSession();
    if (!sess) {
      setAuthed(false);
      setReady(true);
      return;
    }
    fetch(engineBase() + "/api/auth/me", { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok && d.authenticated && d.user) {
          setAuthed(true);
          setErrMsg("");
        } else {
          writeAuthSession(null);
          setAuthed(false);
          setErrMsg("登录已失效，请重新登录");
        }
      })
      .catch(function () {
        setAuthed(false);
        setErrMsg("无法连接引擎，请确认 scripts/engine.sh zr-workbuddy ensure");
      })
      .finally(function () {
        setReady(true);
      });
  }

  useEffect(function () {
    refresh();
    function onAuth() {
      refresh();
    }
    window.addEventListener(AUTH_EVENT, onAuth);
    return function () {
      window.removeEventListener(AUTH_EVENT, onAuth);
    };
  }, []);

  if (!ready) {
    return h(
      "div",
      { className: "wb-app-login-gate", role: "dialog", "aria-modal": "true", "aria-label": "登录" },
      h("div", { className: "wb-login-card" }, h("p", { className: "wb-login-hint" }, "检查登录状态…")),
    );
  }
  if (authed) return null;
  return h(
    "div",
    { className: "wb-app-login-gate", role: "dialog", "aria-modal": "true", "aria-label": "登录" },
    h(WorkBuddyLoginForm, {
      initialError: errMsg,
      onSuccess: function () {
        setAuthed(true);
        setErrMsg("");
      },
    }),
  );
}

function mountAppLoginGate() {
  if (typeof document === "undefined") return function () {};
  var disposed = false;
  var cleanupInner = function () {};

  function start() {
    if (disposed) return;
    ensureCss();
    var host = document.getElementById("wb-app-login-gate-root");
    if (!host) {
      host = document.createElement("div");
      host.id = "wb-app-login-gate-root";
      (document.body || document.documentElement).appendChild(host);
    }

    function paintDomFallback(errMsg) {
      var logoUrl = engineBase() + "/zr-logo.svg";
      host.innerHTML =
        '<div class="wb-app-login-gate" role="dialog" aria-modal="true" aria-label="登录">' +
        '<div class="wb-login-card">' +
        '<div class="wb-login-brand"><div class="brand-icon" aria-hidden="true">' +
        '<img src="' + logoUrl + '" alt="" /></div>' +
        "<h1>ZR WorkBuddy</h1><p>你的工作搭档 · 登录 ZR WorkBuddy</p></div>" +
        '<form class="wb-login-form" id="wbDomLoginForm">' +
        '<div class="field"><span>企业编码</span>' +
        '<select id="wbDomEnt" style="height:40px;border:1px solid #dbe1ea;border-radius:10px;padding:0 12px;font:14px inherit">' +
        AUTH_ENTERPRISES.map(function (e) {
          return '<option value="' + e.key + '"' + (e.key === "jxzr" ? " selected" : "") + ">" + e.label + "</option>";
        }).join("") +
        "</select></div>" +
        '<label class="field"><span>账号</span><input id="wbDomUser" type="text" autocomplete="username" placeholder="账号" required /></label>' +
        '<label class="field"><span>密码</span><input id="wbDomPass" type="password" autocomplete="current-password" placeholder="密码" required /></label>' +
        (errMsg ? '<p class="error">' + String(errMsg).replace(/</g, "&lt;") + "</p>" : "") +
        '<button class="submit" type="submit" id="wbDomSubmit">登录</button></form>' +
        '<p class="wb-login-hint">本页是 ZR WorkBuddy 登录，与系统配置里上传的 MES 接口文档无关。</p>' +
        "</div></div>";
      var form = document.getElementById("wbDomLoginForm");
      if (form) {
        form.onsubmit = function (ev) {
          ev.preventDefault();
          var u = (document.getElementById("wbDomUser").value || "").trim();
          var p = document.getElementById("wbDomPass").value || "";
          var ek = (document.getElementById("wbDomEnt") && document.getElementById("wbDomEnt").value) || "jxzr";
          var ent = AUTH_ENTERPRISES.find(function (e) { return e.key === ek; }) || AUTH_ENTERPRISES[1];
          var btn = document.getElementById("wbDomSubmit");
          if (!u || !p) {
            paintDomFallback("请输入账号和密码");
            return;
          }
          if (btn) {
            btn.disabled = true;
            btn.textContent = "登录中…";
          }
          fetch(engineBase() + "/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              username: u,
              password: p,
              enterprise_code: String(ent.code || "").trim(),
            }),
          })
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (!d || !d.ok || !d.token) throw new Error((d && d.detail) || "登录失败");
              writeAuthSession({
                access_token: d.token,
                token_type: d.token_type || "Bearer",
                username: (d.user && d.user.username) || u,
                display_name: (d.user && d.user.display_name) || u,
                user_id: (d.user && d.user.id) || "",
                enterprise_code: String(ent.code || "").trim(),
                expires_at: d.expires_at,
              });
              host.innerHTML = "";
            })
            .catch(function (err) {
              writeAuthSession(null);
              paintDomFallback(err && err.message ? err.message : String(err));
            });
        };
      }
    }

    function syncDomGate() {
      var sess = readAuthSession();
      if (!sess) {
        paintDomFallback("");
        return;
      }
      fetch(engineBase() + "/api/auth/me", { headers: authHeaders() })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.ok && d.authenticated && d.user) {
            host.innerHTML = "";
          } else {
            writeAuthSession(null);
            paintDomFallback("登录已失效，请重新登录");
          }
        })
        .catch(function () {
          paintDomFallback("无法连接引擎，请确认 scripts/engine.sh zr-workbuddy ensure");
        });
    }

    // 优先纯 DOM 挡板：不依赖 react-dom，保证 :3081 进应用必见登录
    syncDomGate();
    window.addEventListener(AUTH_EVENT, syncDomGate);
    cleanupInner = function () {
      try {
        window.removeEventListener(AUTH_EVENT, syncDomGate);
      } catch (e4) {}
      if (host && host.parentNode) host.parentNode.removeChild(host);
    };
    console.log("[dsh-mes-bridge] 已挂载 :3081 登录挡板");
  }

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);

  return function () {
    disposed = true;
    cleanupInner();
  };
}

  ctx.WorkBuddyLoginForm = WorkBuddyLoginForm;
  ctx.WorkBuddyAppLoginGate = WorkBuddyAppLoginGate;
  ctx.mountAppLoginGate = mountAppLoginGate;
}

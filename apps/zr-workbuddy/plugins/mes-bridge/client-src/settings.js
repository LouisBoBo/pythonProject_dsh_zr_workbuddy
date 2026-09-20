export function installSettings(ctx) {
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

function field(label, props, full) {
  var p = props || {};
  return h(
    "div",
    { className: "wb-set-field" + (full ? " full" : "") },
    h("label", null, label),
    p.multiline ? h("textarea", p) : h("input", p),
  );
}

var WB_SECRET_MASK = "••••••••••••";
var HOST_SET_HIDE_LABELS = ["远端审码", "Cursor 写码"];

var _wbHostHideCleanup = null;
function hideHostSettingsDupes() {
  if (typeof document === "undefined") return function () {};
  if (_wbHostHideCleanup) return _wbHostHideCleanup;
  var marked = [];
  function labelMatch(text) {
    for (var i = 0; i < HOST_SET_HIDE_LABELS.length; i++) {
      var lab = HOST_SET_HIDE_LABELS[i];
      if (text === lab || text.indexOf(lab) >= 0) return true;
    }
    return false;
  }
  function scan() {
    var nodes = document.querySelectorAll("button, [class*='_navCell'], [role='tab']");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      // 只藏宿主设置侧栏，勿藏 WorkBuddy 内二级导航
      if (el.closest && el.closest(".wb-set")) continue;
      var text = String(el.textContent || "")
        .replace(/\s+/g, " ")
        .trim();
      if (!labelMatch(text)) continue;
      var cell =
        (el.closest && (el.closest("[class*='_navCell']") || el.closest("[role='tab']"))) || el;
      if (cell.closest && cell.closest(".wb-set")) continue;
      if (cell.getAttribute("data-wb-host-hide") === "1") continue;
      cell.setAttribute("data-wb-host-hide", "1");
      marked.push(cell);
    }
  }
  scan();
  var obs =
    typeof MutationObserver !== "undefined"
      ? new MutationObserver(function () {
          scan();
        })
      : null;
  if (obs) obs.observe(document.body, { childList: true, subtree: true });
  _wbHostHideCleanup = function () {
    if (obs) obs.disconnect();
    marked.forEach(function (el) {
      try {
        el.removeAttribute("data-wb-host-hide");
      } catch (e) {}
    });
    _wbHostHideCleanup = null;
  };
  return _wbHostHideCleanup;
}

function WbRemoteReviewPanel(props) {
  ensureCss();
  var reportStatus = (props && props.reportStatus) || null;
  var apiRef = (props && props.apiRef) || null;
  var hostState = useState(function () {
    try {
      return localStorage.getItem("dsh-remote-review-host") || "127.0.0.1";
    } catch (e) {
      return "127.0.0.1";
    }
  });
  var svcHost = hostState[0];
  var setSvcHost = hostState[1];
  var portState = useState(function () {
    try {
      return localStorage.getItem("dsh-remote-review-port") || "18787";
    } catch (e) {
      return "18787";
    }
  });
  var svcPort = portState[0];
  var setSvcPort = portState[1];
  var prefixState = useState(function () {
    try {
      var x = localStorage.getItem("dsh-remote-review-prefix");
      return x != null ? x : "";
    } catch (e) {
      return "";
    }
  });
  var svcPrefix = prefixState[0];
  var setSvcPrefix = prefixState[1];
  var draftState = useState({
    engine: "http://127.0.0.1:8000",
    listen: "127.0.0.1",
    port: "18787",
    secret: "",
    secretConfigured: false,
    feishuAppId: "",
    feishuAppSecret: "",
    feishuAppSecretConfigured: false,
    feishuFolderToken: "",
    feishuWikiSpaceId: "",
    feishuWikiParentNodeToken: "",
    webhook: "",
    dataRoot: "",
  });
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
  var healthState = useState("");
  var health = healthState[0];
  var setHealth = healthState[1];

  function setStatus(nextBusy, nextMsg, nextOk) {
    setBusy(!!nextBusy);
    if (nextMsg != null) setMsg(String(nextMsg));
    if (nextOk != null) setMsgOk(!!nextOk);
    if (reportStatus) reportStatus(!!nextBusy, nextMsg, nextOk);
  }

  function remember() {
    try {
      localStorage.setItem("dsh-remote-review-host", String(svcHost || "127.0.0.1").trim());
      localStorage.setItem("dsh-remote-review-port", String(svcPort || "18787").trim());
      localStorage.setItem("dsh-remote-review-prefix", String(svcPrefix || "").trim());
    } catch (e) {}
  }

  function base() {
    var host = String(svcHost || "127.0.0.1").trim();
    var port = String(svcPort || "18787").trim();
    var prefix = String(svcPrefix || "").trim();
    if (prefix && prefix.charAt(0) !== "/") prefix = "/" + prefix;
    if (prefix.endsWith("/")) prefix = prefix.slice(0, -1);
    if (port === "80") return "http://" + host + prefix;
    if (port === "443") return "https://" + host + prefix;
    return "http://" + host + ":" + port + prefix;
  }

  function secretForSave(v) {
    var s = String(v || "").trim();
    if (!s || s === WB_SECRET_MASK || /^•+$/.test(s)) return undefined;
    return s;
  }

  function loadConfig() {
    setStatus(true, "加载中…", false);
    remember();
    fetch(base() + "/api/config")
      .then(function (r) {
        return r.json().then(function (d) {
          return { ok: r.ok, d: d };
        });
      })
      .then(function (x) {
        if (!x.ok || !x.d || !x.d.ok || !x.d.config) {
          throw new Error((x.d && x.d.detail) || "无法加载：请先启用「远端审码」插件");
        }
        var c = x.d.config;
        setDraft({
          engine: c.engine || "http://127.0.0.1:8000",
          listen: c.listen || "127.0.0.1",
          port: String(c.port != null ? c.port : 18787),
          secret: c.secretConfigured ? WB_SECRET_MASK : "",
          secretConfigured: !!c.secretConfigured,
          feishuAppId: c.feishuAppId || "",
          feishuAppSecret: c.feishuAppSecretConfigured ? WB_SECRET_MASK : "",
          feishuAppSecretConfigured: !!c.feishuAppSecretConfigured,
          feishuFolderToken: c.feishuFolderToken || "",
          feishuWikiSpaceId: c.feishuWikiSpaceId || "",
          feishuWikiParentNodeToken: c.feishuWikiParentNodeToken || "",
          webhook: c.webhook || "",
          dataRoot: c.dataRoot || "",
        });
        setStatus(false, "已加载远端审码配置（本机，不进 git）", true);
      })
      .catch(function (e) {
        setStatus(false, "加载失败：" + (e && e.message ? e.message : String(e)), false);
      });
  }

  function saveConfig() {
    setStatus(true, "保存中…", false);
    remember();
    if (!String(draft.feishuAppId || "").trim()) {
      setStatus(false, "保存失败：请填写飞书 App ID", false);
      return;
    }
    if (!draft.feishuAppSecretConfigured && !secretForSave(draft.feishuAppSecret)) {
      setStatus(false, "保存失败：请填写飞书 App Secret", false);
      return;
    }
    var payload = {
      engine: draft.engine,
      listen: draft.listen,
      port: draft.port,
      secret: secretForSave(draft.secret),
      feishuAppId: draft.feishuAppId,
      feishuAppSecret: secretForSave(draft.feishuAppSecret),
      feishuFolderToken: draft.feishuFolderToken,
      feishuWikiSpaceId: draft.feishuWikiSpaceId,
      feishuWikiParentNodeToken: draft.feishuWikiParentNodeToken,
    };
    fetch(base() + "/api/config", {
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
        if (!x.ok || !x.d || !x.d.ok) throw new Error((x.d && x.d.detail) || "保存失败");
        setStatus(false, (x.d.detail || "已保存") + (x.d.note ? "；" + x.d.note : ""), true);
        loadConfig();
      })
      .catch(function (e) {
        setStatus(false, "保存失败：" + (e && e.message ? e.message : String(e)), false);
      });
  }

  function checkHealth() {
    remember();
    setHealth("检测中…");
    fetch(base() + "/health")
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        setHealth((d && d.ok ? "OK" : "FAIL") + " · " + ((d && d.detail) || JSON.stringify(d).slice(0, 120)));
      })
      .catch(function (e) {
        setHealth("无法连接 " + base() + "：" + (e && e.message ? e.message : e));
      });
  }

  useEffect(function () {
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (apiRef) {
    apiRef.current = { save: saveConfig, load: loadConfig };
  }

  function patch(k, v) {
    var n = Object.assign({}, draft);
    n[k] = v;
    setDraft(n);
  }

  return h(
    "div",
    { className: "wb-set-card" },
    h("h3", null, "远端审码"),
    h(
      "div",
      { className: "body" },
      h(
        "p",
        { className: "wb-set-hint" },
        "配置写到本机 ~/.zhongruan/remote-review（插件服务），不进业务 git。保存请用底部「保存配置」。",
      ),
      h(
        "div",
        { className: "wb-set-eng", style: { marginBottom: "14px" } },
        h("div", { className: "eng-field" }, h("label", null, "服务 host"), h("input", {
          value: svcHost,
          onChange: function (e) {
            setSvcHost(e.target.value);
          },
        })),
        h("div", { className: "eng-field" }, h("label", null, "port"), h("input", {
          value: svcPort,
          onChange: function (e) {
            setSvcPort(e.target.value);
          },
        })),
        h("div", { className: "eng-field" }, h("label", null, "路径前缀"), h("input", {
          value: svcPrefix,
          placeholder: "本机空",
          style: { width: "140px" },
          onChange: function (e) {
            setSvcPrefix(e.target.value);
          },
        })),
        h(
          "button",
          {
            type: "button",
            className: "wb-set-btn",
            disabled: busy,
            onClick: function () {
              loadConfig();
              checkHealth();
            },
          },
          "连接并加载",
        ),
      ),
      h("div", { className: "wb-set-grid" },
        field("WorkBuddy 引擎地址", {
          value: draft.engine,
          onChange: function (e) {
            patch("engine", e.target.value);
          },
        }, true),
        field("飞书 App ID", {
          value: draft.feishuAppId,
          onChange: function (e) {
            patch("feishuAppId", e.target.value);
          },
        }, true),
        field(draft.feishuAppSecretConfigured ? "飞书 App Secret（已保存）" : "飞书 App Secret", {
          type: "password",
          autoComplete: "new-password",
          value: draft.feishuAppSecret,
          onFocus: function () {
            if (draft.feishuAppSecret === WB_SECRET_MASK) patch("feishuAppSecret", "");
          },
          onChange: function (e) {
            patch("feishuAppSecret", e.target.value);
          },
        }, true),
        field("文档库 space_id", {
          value: draft.feishuWikiSpaceId,
          onChange: function (e) {
            patch("feishuWikiSpaceId", e.target.value);
          },
        }, true),
        field("文档库父节点（可选）", {
          value: draft.feishuWikiParentNodeToken,
          onChange: function (e) {
            patch("feishuWikiParentNodeToken", e.target.value);
          },
        }, true),
        field("云盘文件夹 Token（备用）", {
          value: draft.feishuFolderToken,
          onChange: function (e) {
            patch("feishuFolderToken", e.target.value);
          },
        }, true),
        field("Webhook 监听", {
          value: draft.listen,
          onChange: function (e) {
            patch("listen", e.target.value);
          },
        }),
        field("Webhook 端口", {
          value: draft.port,
          onChange: function (e) {
            patch("port", e.target.value);
          },
        }),
        field(draft.secretConfigured ? "Webhook 密钥（已保存）" : "Webhook 密钥（可选）", {
          type: "password",
          autoComplete: "new-password",
          value: draft.secret,
          onFocus: function () {
            if (draft.secret === WB_SECRET_MASK) patch("secret", "");
          },
          onChange: function (e) {
            patch("secret", e.target.value);
          },
        }, true),
      ),
      h(
        "p",
        { className: "wb-set-hint" },
        "Webhook：" + (draft.webhook || base() + "/webhook") + (draft.dataRoot ? " · " + draft.dataRoot : ""),
      ),
      h(
        "div",
        { className: "wb-set-actions" },
        h(
          "button",
          { type: "button", className: "wb-set-btn", disabled: busy, onClick: checkHealth },
          "检测服务",
        ),
        !reportStatus && msg
          ? h("span", { className: "wb-set-msg" + (msgOk ? " ok" : " err") }, msg)
          : null,
      ),
      health ? h("p", { className: "wb-set-hint" }, health) : null,
    ),
  );
}

function WbCursorCodingPanel(props) {
  ensureCss();
  var reportStatus = (props && props.reportStatus) || null;
  var apiRef = (props && props.apiRef) || null;
  var draftState = useState({
    port: "18788",
    cursorApiKey: "",
    cursorKeyConfigured: false,
    writeScopeText: "",
    dataRoot: "",
  });
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
  var healthState = useState("");
  var health = healthState[0];
  var setHealth = healthState[1];
  var jobIdState = useState("");
  var jobId = jobIdState[0];
  var setJobId = jobIdState[1];
  var jobBodyState = useState("");
  var jobBody = jobBodyState[0];
  var setJobBody = jobBodyState[1];
  var jobMetaState = useState("");
  var jobMeta = jobMetaState[0];
  var setJobMeta = jobMetaState[1];

  function setStatus(nextBusy, nextMsg, nextOk) {
    setBusy(!!nextBusy);
    if (nextMsg != null) setMsg(String(nextMsg));
    if (nextOk != null) setMsgOk(!!nextOk);
    if (reportStatus) reportStatus(!!nextBusy, nextMsg, nextOk);
  }

  function base() {
    return "http://127.0.0.1:" + String(draft.port || "18788").trim();
  }

  function remember() {
    try {
      localStorage.setItem("dsh-cursor-coding-host", "127.0.0.1");
      localStorage.setItem("dsh-cursor-coding-port", String(draft.port || "18788").trim());
    } catch (e) {}
  }

  function loadConfig() {
    setStatus(true, "加载中…", false);
    fetch(base() + "/api/config")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) throw new Error((data && data.detail) || "加载失败");
        var c = data.config || {};
        setDraft({
          port: String(c.port || 18788),
          cursorApiKey: c.cursorKeyConfigured ? WB_SECRET_MASK : "",
          cursorKeyConfigured: Boolean(c.cursorKeyConfigured),
          writeScopeText: c.writeScopeText || "",
          dataRoot: c.dataRoot || "",
        });
        remember();
        setStatus(false, "已加载 Cursor 写码配置（本机，不进 git）", true);
      })
      .catch(function (err) {
        setStatus(false, String(err && err.message ? err.message : err) + "（请先启用 Cursor 写码插件）", false);
      });
  }

  function saveConfig() {
    setStatus(true, "保存中…", false);
    remember();
    var key = String(draft.cursorApiKey || "").trim();
    var body = {
      listen: "127.0.0.1",
      port: draft.port,
      writeScopeText: draft.writeScopeText,
    };
    if (key && key !== WB_SECRET_MASK && !/^•+$/.test(key)) body.cursorApiKey = key;
    fetch(base() + "/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (d) {
          return { ok: r.ok, d: d };
        });
      })
      .then(function (out) {
        if (!out.d || !out.d.ok) throw new Error((out.d && out.d.detail) || "保存失败");
        setStatus(false, out.d.detail || "已保存", true);
        loadConfig();
      })
      .catch(function (err) {
        setStatus(false, String(err && err.message ? err.message : err), false);
      });
  }

  function checkHealth() {
    remember();
    fetch(base() + "/health")
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        setHealth(
          (d.ok ? "OK" : "FAIL") +
            " · Key " +
            (d.cursorKeyReady ? "已配置" : "未配置") +
            " · " +
            (d.detail || ""),
        );
      })
      .catch(function (err) {
        setHealth("无法连接 " + base() + "：" + String(err));
      });
  }

  function loadJobBody() {
    var jid = String(jobId || "").trim();
    if (!jid) {
      setJobMeta("请填写 job_id");
      return;
    }
    setBusy(true);
    setJobMeta("加载中…");
    setJobBody("");
    fetch(base() + "/api/cursor-coding/jobs/" + encodeURIComponent(jid))
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d || !d.ok) throw new Error((d && d.detail) || "加载失败");
        var text =
          (d.job && (d.job.assistant_text || d.job.body || d.job.reply)) ||
          d.assistant_text ||
          d.body ||
          "";
        setJobBody(String(text || ""));
        setJobMeta(text ? "已加载" : "无正文");
      })
      .catch(function (err) {
        setJobMeta(String(err && err.message ? err.message : err));
      })
      .finally(function () {
        setBusy(false);
      });
  }

  useEffect(function () {
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (apiRef) {
    apiRef.current = { save: saveConfig, load: loadConfig };
  }

  return h(
    "div",
    { className: "wb-set-card" },
    h("h3", null, "Cursor 写码"),
    h(
      "div",
      { className: "body" },
      h(
        "p",
        { className: "wb-set-hint" },
        "唯一写码通道。配置写到 ~/.zhongruan/cursor-coding。保存请用底部「保存配置」。",
      ),
      h(
        "div",
        { className: "wb-set-grid" },
        field("Cursor API Key", {
          type: "password",
          autoComplete: "new-password",
          value: draft.cursorApiKey,
          placeholder: draft.cursorKeyConfigured ? "已配置，留空保存则保持不变" : "必填",
          onChange: function (e) {
            setDraft(Object.assign({}, draft, { cursorApiKey: e.target.value }));
          },
        }, true),
        field("监听端口", {
          value: draft.port,
          onChange: function (e) {
            setDraft(Object.assign({}, draft, { port: e.target.value }));
          },
        }),
        field("默认可写范围（每行一个相对前缀）", {
          multiline: true,
          rows: 3,
          value: draft.writeScopeText,
          placeholder: "例如\nsrc/\napps/",
          onChange: function (e) {
            setDraft(Object.assign({}, draft, { writeScopeText: e.target.value }));
          },
        }, true),
      ),
      draft.dataRoot ? h("p", { className: "wb-set-hint" }, "数据目录：" + draft.dataRoot) : null,
      h("p", { className: "wb-set-hint" }, "回看 Cursor 正文（对照 IDE）"),
      h(
        "div",
        { className: "wb-set-grid" },
        field("job_id", {
          value: jobId,
          placeholder: "例如 ccj-20260911-201421-fb75",
          onChange: function (e) {
            setJobId(e.target.value);
          },
        }, true),
      ),
      h(
        "div",
        { className: "wb-set-actions" },
        h(
          "button",
          { type: "button", className: "wb-set-btn", disabled: busy, onClick: loadJobBody },
          "加载正文",
        ),
        h(
          "button",
          { type: "button", className: "wb-set-btn", disabled: busy, onClick: checkHealth },
          "检测服务",
        ),
        !reportStatus && msg
          ? h("span", { className: "wb-set-msg" + (msgOk ? " ok" : " err") }, msg)
          : null,
      ),
      jobMeta ? h("p", { className: "wb-set-hint" }, jobMeta) : null,
      h("div", { className: "wb-set-jobbody" + (jobBody ? "" : " empty") }, jobBody || "加载后显示 Cursor 完整正文。"),
      health ? h("p", { className: "wb-set-hint" }, health) : null,
    ),
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
    vision: {
      api_key: "",
      base_url: "",
      model: "",
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
      enabled: true,
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
    automations: {
      wecom_webhook_key: "",
      wecom_push_enabled: false,
      wecom_push_dry_run: false,
      feishu_app_id: "",
      feishu_app_secret: "",
      feishu_bitable_enabled: false,
      feishu_bitable_dry_run: false,
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

function fetchAbout() {
  return fetch(engineBase() + "/api/about", { headers: authHeaders() })
    .then(function (r) {
      return r.json().then(function (d) {
        return { http: r.status, data: d };
      });
    })
    .catch(function (e) {
      return { http: 0, data: { ok: false, detail: (e && e.message) || "网络错误" } };
    });
}

function WorkBuddyHeaderLogout() {
  ensureCss();
  var userState = useState(null);
  var user = userState[0];
  var setUser = userState[1];
  var openState = useState(false);
  var open = openState[0];
  var setOpen = openState[1];
  var busyState = useState(false);
  var busy = busyState[0];
  var setBusy = busyState[1];
  var panelState = useState(null);
  var panel = panelState[0];
  var setPanel = panelState[1];
  var feedbackState = useState("");
  var feedback = feedbackState[0];
  var setFeedback = feedbackState[1];
  var imagesState = useState([]);
  var images = imagesState[0];
  var setImages = imagesState[1];
  var previewImgState = useState(null);
  var previewImg = previewImgState[0];
  var setPreviewImg = previewImgState[1];
  var fileInputRef = useRef(null);
  var successCloseTimerRef = useRef(null);
  var panelBusyState = useState(false);
  var panelBusy = panelBusyState[0];
  var setPanelBusy = panelBusyState[1];
  var panelMsgState = useState("");
  var panelMsg = panelMsgState[0];
  var setPanelMsg = panelMsgState[1];
  var panelOkState = useState(false);
  var panelOk = panelOkState[0];
  var setPanelOk = panelOkState[1];
  var aboutState = useState(null);
  var about = aboutState[0];
  var setAbout = aboutState[1];
  var feedbackDoneState = useState(false);
  var feedbackDone = feedbackDoneState[0];
  var setFeedbackDone = feedbackDoneState[1];

  function refresh() {
    var sess = readAuthSession();
    if (!sess) {
      setUser(null);
      return;
    }
    setUser({
      username: sess.username || "",
      display_name: sess.display_name || sess.username || "",
    });
    fetch(engineBase() + "/api/auth/me", { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok && d.authenticated && d.user) setUser(d.user);
        else setUser(null);
      })
      .catch(function () {});
  }

  function clearFeedbackImages(list) {
    (list || images || []).forEach(function (it) {
      try {
        if (it && it.url) URL.revokeObjectURL(it.url);
      } catch (e0) {}
    });
  }

  function closePanel() {
    if (successCloseTimerRef.current) {
      clearTimeout(successCloseTimerRef.current);
      successCloseTimerRef.current = null;
    }
    if (panel === "feedback") clearFeedbackImages();
    setPreviewImg(null);
    setPanel(null);
    setPanelBusy(false);
    setPanelMsg("");
    setPanelOk(false);
    setFeedbackDone(false);
    setFeedback("");
    setImages([]);
  }

  function openFeedback() {
    setOpen(false);
    clearFeedbackImages();
    setFeedback("");
    setImages([]);
    setPreviewImg(null);
    setPanelMsg("");
    setPanelOk(false);
    setFeedbackDone(false);
    setPanel("feedback");
  }

  function openUpdate() {
    setOpen(false);
    setPanelMsg("");
    setPanelOk(false);
    setAbout(null);
    setPanel("update");
    setPanelBusy(true);
    var desk =
      typeof window !== "undefined" && window.workbuddyDesktop
        ? window.workbuddyDesktop
        : null;
    var deskP =
      desk && typeof desk.checkUpdate === "function"
        ? Promise.resolve(desk.checkUpdate()).catch(function () {
            return null;
          })
        : Promise.resolve(null);
    Promise.all([fetchAbout(), deskP])
      .then(function (pair) {
        var aboutRes = pair[0] || {};
        var deskRes = pair[1];
        var d = (aboutRes && aboutRes.data) || {};
        var info = {
          ok: !!(d && d.ok),
          app_version: (d && d.app_version) || "",
          product: (d && d.product) || "ZR-WorkBuddy",
          desktop: deskRes && typeof deskRes === "object" ? deskRes : null,
          detail: (d && d.detail) || "",
        };
        setAbout(info);
        if (!info.ok && info.detail) {
          setPanelOk(false);
          setPanelMsg(info.detail);
        } else {
          setPanelOk(true);
          var deskMsg =
            info.desktop && info.desktop.message
              ? String(info.desktop.message)
              : "";
          setPanelMsg(
            deskMsg ||
              (info.desktop && info.desktop.updateAvailable
                ? "发现可用更新，请按提示安装新包。"
                : "当前为本机已安装版本；在线升级通道未开通时，请向管理员索取新安装包覆盖安装。"),
          );
        }
      })
      .finally(function () {
        setPanelBusy(false);
      });
  }

  function onPickImages(ev) {
    var files = ev && ev.target && ev.target.files ? Array.from(ev.target.files) : [];
    if (ev && ev.target) ev.target.value = "";
    if (!files.length) return;
    var next = images.slice();
    var err = "";
    files.forEach(function (f) {
      if (next.length >= 6) {
        err = "最多上传 6 张图片";
        return;
      }
      if (!f || !(f.type || "").startsWith("image/")) {
        err = "仅支持图片文件";
        return;
      }
      if (f.size > 5 * 1024 * 1024) {
        err = "单张图片请不超过 5MB";
        return;
      }
      next.push({
        id: String(Date.now()) + "-" + Math.random().toString(36).slice(2, 8),
        file: f,
        name: f.name || "image",
        url: URL.createObjectURL(f),
        broken: false,
      });
    });
    setImages(next);
    if (err) {
      setPanelOk(false);
      setPanelMsg(err);
    } else {
      setPanelMsg("");
    }
  }

  function removeImage(id) {
    var kept = [];
    images.forEach(function (it) {
      if (it.id === id) {
        try {
          if (it.url) URL.revokeObjectURL(it.url);
        } catch (e1) {}
      } else {
        kept.push(it);
      }
    });
    setImages(kept);
  }

  function submitFeedback() {
    var text = String(feedback || "").trim();
    if (!text) {
      setPanelOk(false);
      setPanelMsg("请填写反馈内容");
      return;
    }
    if (text.length > 4000) {
      setPanelOk(false);
      setPanelMsg("反馈内容请控制在 4000 字以内");
      return;
    }
    setPanelBusy(true);
    setPanelMsg("");
    var fd = new FormData();
    fd.append("message", text);
    images.forEach(function (it) {
      if (it && it.file) fd.append("images", it.file, it.name || "image.png");
    });
    var headers = authHeaders();
    // 让浏览器自动带 multipart boundary，勿手写 Content-Type
    fetch(engineBase() + "/api/feedback", {
      method: "POST",
      headers: headers,
      body: fd,
    })
      .then(function (r) {
        return r.json().then(function (d) {
          return { http: r.status, data: d };
        });
      })
      .then(function (res) {
        var d = res.data || {};
        if (res.http >= 200 && res.http < 300 && d.ok) {
          clearFeedbackImages();
          setFeedback("");
          setImages([]);
          setPreviewImg(null);
          setPanelBusy(false);
          setPanelOk(true);
          setPanelMsg("提交成功");
          setFeedbackDone(true);
          if (successCloseTimerRef.current) {
            clearTimeout(successCloseTimerRef.current);
          }
          successCloseTimerRef.current = setTimeout(function () {
            successCloseTimerRef.current = null;
            setPanel(null);
            setPanelMsg("");
            setPanelOk(false);
            setFeedbackDone(false);
          }, 2000);
        } else {
          setPanelOk(false);
          setPanelMsg((d && d.detail) || "提交失败");
          setPanelBusy(false);
        }
      })
      .catch(function (e) {
        setPanelOk(false);
        setPanelMsg((e && e.message) || "网络错误");
        setPanelBusy(false);
      });
  }

  useEffect(function () {
    refresh();
    function onAuth() { refresh(); }
    window.addEventListener(AUTH_EVENT, onAuth);
    return function () { window.removeEventListener(AUTH_EVENT, onAuth); };
  }, []);

  useEffect(
    function () {
      if (!open && !panel && !previewImg) return undefined;
      function onKey(ev) {
        if (ev.key !== "Escape") return;
        if (previewImg) setPreviewImg(null);
        else if (panel) closePanel();
        else setOpen(false);
      }
      document.addEventListener("keydown", onKey);
      return function () { document.removeEventListener("keydown", onKey); };
    },
    [open, panel, previewImg],
  );

  if (!user) return null;
  var label = user.display_name || user.username || "";
  var initial = (label || "?").trim().charAt(0).toUpperCase() || "U";
  var dialog =
    panel === "feedback"
      ? h(
          "div",
          {
            className: "wb-account-dialog-overlay",
            role: "dialog",
            "aria-modal": "true",
            "aria-label": "帮助与反馈",
            onClick: closePanel,
          },
          h(
            "div",
            {
              className: "wb-account-dialog feedback",
              onClick: function (ev) {
                ev.stopPropagation();
              },
            },
            h(
              "div",
              { className: "wb-account-dialog-head" },
              h("span", { className: "t" }, "帮助与反馈"),
              h(
                "button",
                {
                  type: "button",
                  className: "wb-account-dialog-x",
                  "aria-label": "关闭",
                  onClick: closePanel,
                },
                "×",
              ),
            ),
            h(
              "div",
              { className: "wb-account-dialog-body" },
              feedbackDone
                ? h(
                    "div",
                    { className: "wb-fb-success", role: "status", "aria-live": "polite" },
                    h("div", { className: "ico", "aria-hidden": "true" }, "✓"),
                    h("p", { className: "t" }, "提交成功"),
                    h("p", { className: "s" }, "感谢反馈，窗口即将关闭…"),
                  )
                : h(
                    React.Fragment,
                    null,
                    h(
                      "p",
                      { className: "hint" },
                      "请描述现象、复现步骤与期望结果；可附截图（最多 6 张，单张 ≤5MB）。资料库、用量在会话顶栏页签。",
                    ),
                    h("textarea", {
                      value: feedback,
                      placeholder: "请描述你的问题或建议…",
                      disabled: panelBusy,
                      onChange: function (ev) {
                        setFeedback(ev.target.value);
                      },
                    }),
                    h(
                      "div",
                      { className: "wb-fb-images" },
                      images.map(function (it) {
                        return h(
                          "div",
                          {
                            key: it.id,
                            className: "wb-fb-thumb",
                            role: "button",
                            tabIndex: 0,
                            title: "点击预览",
                            onClick: function () {
                              if (it.broken || !it.url) return;
                              setPreviewImg({ url: it.url, name: it.name || "截图" });
                            },
                            onKeyDown: function (ev) {
                              if (ev.key === "Enter" || ev.key === " ") {
                                ev.preventDefault();
                                if (it.broken || !it.url) return;
                                setPreviewImg({ url: it.url, name: it.name || "截图" });
                              }
                            },
                          },
                          it.broken
                            ? h("div", { className: "wb-fb-broken" }, "无法预览此图")
                            : h("img", {
                                src: it.url,
                                alt: it.name || "截图",
                                onError: function () {
                                  setImages(function (prev) {
                                    return (prev || []).map(function (row) {
                                      if (row.id !== it.id) return row;
                                      return Object.assign({}, row, { broken: true });
                                    });
                                  });
                                },
                              }),
                          h(
                            "button",
                            {
                              type: "button",
                              className: "rm",
                              title: "移除",
                              "aria-label": "移除图片",
                              disabled: panelBusy,
                              onClick: function (ev) {
                                ev.stopPropagation();
                                removeImage(it.id);
                                if (previewImg && previewImg.url === it.url) setPreviewImg(null);
                              },
                            },
                            "×",
                          ),
                        );
                      }),
                      images.length < 6
                        ? h(
                            "label",
                            {
                              className: "wb-fb-add",
                              title: "添加图片",
                            },
                            h("span", null, "+"),
                            h("span", null, "图片"),
                            h("input", {
                              ref: fileInputRef,
                              type: "file",
                              accept: "image/*,.png,.jpg,.jpeg,.gif,.webp,.bmp",
                              multiple: true,
                              disabled: panelBusy,
                              onChange: onPickImages,
                            }),
                          )
                        : null,
                    ),
                    panelMsg
                      ? h(
                          "p",
                          { className: "msg-banner " + (panelOk ? "ok" : "err") },
                          panelMsg,
                        )
                      : null,
                    h(
                      "div",
                      { className: "wb-account-dialog-actions" },
                      h(
                        "button",
                        {
                          type: "button",
                          className: "btn",
                          disabled: panelBusy,
                          onClick: closePanel,
                        },
                        "关闭",
                      ),
                      h(
                        "button",
                        {
                          type: "button",
                          className: "btn primary",
                          disabled: panelBusy,
                          onClick: submitFeedback,
                        },
                        panelBusy ? "提交中…" : "提交反馈",
                      ),
                    ),
                  ),
            ),
          ),
        )
      : panel === "update"
        ? h(
            "div",
            {
              className: "wb-account-dialog-overlay",
              role: "dialog",
              "aria-modal": "true",
              "aria-label": "检查更新",
              onClick: closePanel,
            },
            h(
              "div",
              {
                className: "wb-account-dialog",
                onClick: function (ev) {
                  ev.stopPropagation();
                },
              },
              h(
                "div",
                { className: "wb-account-dialog-head" },
                h("span", { className: "t" }, "检查更新"),
                h(
                  "button",
                  {
                    type: "button",
                    className: "wb-account-dialog-x",
                    "aria-label": "关闭",
                    onClick: closePanel,
                  },
                  "×",
                ),
              ),
              h(
                "div",
                { className: "wb-account-dialog-body" },
                panelBusy
                  ? h("p", { className: "hint" }, "正在检查…")
                  : h(
                      React.Fragment,
                      null,
                      h(
                        "p",
                        { className: "ver" },
                        (about && about.product ? about.product : "ZR-WorkBuddy") +
                          " " +
                          (about && about.app_version
                            ? "v" + about.app_version
                            : ""),
                      ),
                      about &&
                        about.desktop &&
                        about.desktop.currentVersion
                        ? h(
                            "p",
                            { className: "hint" },
                            "桌面壳版本 v" + about.desktop.currentVersion,
                          )
                        : h(
                            "p",
                            { className: "hint" },
                            "当前为浏览器/开发壳；桌面一体包可在应用内检查桌面版本。",
                          ),
                      panelMsg
                        ? h(
                            "p",
                            { className: panelOk ? "hint" : "err" },
                            panelMsg,
                          )
                        : null,
                    ),
                h(
                  "div",
                  { className: "wb-account-dialog-actions" },
                  h(
                    "button",
                    {
                      type: "button",
                      className: "btn primary",
                      disabled: panelBusy,
                      onClick: closePanel,
                    },
                    "知道了",
                  ),
                ),
              ),
            ),
          )
        : null;

  return h(
    React.Fragment,
    null,
    open
      ? h("div", {
          className: "wb-header-logout-mask",
          onClick: function () { setOpen(false); },
        })
      : null,
    h(
      "div",
      { className: "wb-header-logout" + (open ? " open" : "") },
      h(
        "button",
        {
          type: "button",
          className: "trigger",
          "aria-haspopup": "menu",
          "aria-expanded": open,
          title: "账号",
          onClick: function () { setOpen(!open); },
        },
        h("span", { className: "avatar", "aria-hidden": "true" }, initial),
        h("span", { className: "name" }, label),
        h(
          "svg",
          { className: "caret", viewBox: "0 0 12 8", width: 10, height: 8, "aria-hidden": "true" },
          h("path", {
            d: "M1 1.5L6 6.5L11 1.5",
            fill: "none",
            stroke: "currentColor",
            strokeWidth: "1.5",
            strokeLinecap: "round",
            strokeLinejoin: "round",
          }),
        ),
      ),
      open
        ? h(
            "div",
            { className: "menu", role: "menu" },
            h(
              "button",
              {
                type: "button",
                className: "menu-item",
                role: "menuitem",
                onClick: openFeedback,
              },
              "帮助与反馈",
            ),
            h(
              "button",
              {
                type: "button",
                className: "menu-item",
                role: "menuitem",
                onClick: openUpdate,
              },
              "检查更新",
            ),
            h("div", { className: "menu-sep", role: "separator" }),
            h(
              "button",
              {
                type: "button",
                className: "menu-logout",
                role: "menuitem",
                disabled: busy,
                onClick: function () {
                  setBusy(true);
                  doAppLogout().finally(function () {
                    setBusy(false);
                    setOpen(false);
                  });
                },
              },
              busy ? "退出中…" : "退出登录",
            ),
          )
        : null,
    ),
    dialog,
    previewImg
      ? h(
          "div",
          {
            className: "wb-fb-lightbox",
            role: "dialog",
            "aria-modal": "true",
            "aria-label": "图片预览",
            onClick: function () {
              setPreviewImg(null);
            },
          },
          h(
            "div",
            {
              className: "wb-fb-lightbox-inner",
              onClick: function (ev) {
                ev.stopPropagation();
              },
            },
            h(
              "button",
              {
                type: "button",
                className: "wb-fb-lightbox-x",
                "aria-label": "关闭预览",
                onClick: function () {
                  setPreviewImg(null);
                },
              },
              "×",
            ),
            h("img", {
              src: previewImg.url,
              alt: previewImg.name || "预览",
            }),
            previewImg.name
              ? h("p", { className: "wb-fb-lightbox-cap" }, previewImg.name)
              : null,
          ),
        )
      : null,
  );
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
  var tabState = useState("mes");
  var tab = tabState[0];
  var setTab = tabState[1];
  var SET_NAV = [
    { id: "mes", label: "MES 连接" },
    { id: "llm", label: "商用模型" },
    { id: "remote_review", label: "远端审码" },
    { id: "cursor_coding", label: "Cursor 写码" },
    { id: "code_deploy", label: "自动化部署" },
    { id: "automations", label: "自动化推送" },
  ];

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
          vision: Object.assign({}, base.vision, c.vision || {}),
          code_dev: Object.assign({}, base.code_dev, c.code_dev || {}),
          code_review: Object.assign({}, base.code_review, c.code_review || {}),
          code_commit: Object.assign({}, base.code_commit, c.code_commit || {}),
          code_deploy: Object.assign({}, base.code_deploy, c.code_deploy || {}),
          automations: Object.assign({}, base.automations, c.automations || {}),
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

  var rootRef = useRef(null);
  var pluginApiRef = useRef(null);

  function reportPluginStatus(nextBusy, nextMsg, nextOk) {
    setBusy(!!nextBusy);
    if (nextMsg != null) setMsg(String(nextMsg));
    if (nextOk != null) setMsgOk(!!nextOk);
  }

  function saveCurrent() {
    if (tab === "remote_review" || tab === "cursor_coding") {
      var api = pluginApiRef.current;
      if (api && typeof api.save === "function") api.save();
      else {
        setMsg("当前页尚未就绪，请稍候再保存");
        setMsgOk(false);
      }
      return;
    }
    saveConfig();
  }

  function loadCurrent() {
    if (tab === "remote_review" || tab === "cursor_coding") {
      var api = pluginApiRef.current;
      if (api && typeof api.load === "function") api.load();
      else {
        setMsg("当前页尚未就绪，请稍候再加载");
        setMsgOk(false);
      }
      return;
    }
    loadConfig();
  }

  useEffect(function () {
    if (tab === "remote_review" || tab === "cursor_coding") return;
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 兜底：仅拉宽宿主设置 panel，不改其 display（避免内容被顶到底）
  useLayoutEffect(function () {
    var el = rootRef.current;
    if (!el || typeof document === "undefined") return undefined;
    var panel =
      document.querySelector(".VOzbGW_panel") ||
      (el.closest && el.closest("[class*='_panel']")) ||
      null;
    if (!panel) {
      var node = el.parentElement;
      while (node && node !== document.body) {
        if (node.className && String(node.className).indexOf("_panel") >= 0) {
          panel = node;
          break;
        }
        node = node.parentElement;
      }
    }
    if (!panel) return undefined;
    panel.classList.add("wb-set-host-wide");
    var prevW = panel.style.width;
    var prevMw = panel.style.maxWidth;
    // 清掉上一版误加的 flex/maxHeight，避免残留
    panel.style.removeProperty("display");
    panel.style.removeProperty("flex-direction");
    panel.style.removeProperty("max-height");
    panel.style.setProperty("width", "920px", "important");
    panel.style.setProperty("max-width", "calc(100vw - 48px)", "important");
    var options =
      panel.querySelector("[class*='_options']") ||
      (el.closest && el.closest("[class*='_options']")) ||
      null;
    if (options) {
      options.style.removeProperty("display");
      options.style.removeProperty("flex-direction");
      options.style.removeProperty("flex");
      options.style.removeProperty("min-height");
      options.style.removeProperty("padding-bottom");
      options.style.removeProperty("margin-bottom");
      options.style.removeProperty("overflow");
      options.style.removeProperty("height");
    }
    return function () {
      panel.classList.remove("wb-set-host-wide");
      panel.style.width = prevW;
      panel.style.maxWidth = prevMw;
    };
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
      vision: Object.assign({}, draft.vision || {}, {
        api_key: (draft.vision && draft.vision.api_key) || "",
        base_url: String((draft.vision && draft.vision.base_url) || "").trim().replace(/\/$/, ""),
        model: String((draft.vision && draft.vision.model) || "").trim(),
      }),
      code_dev: Object.assign({}, draft.code_dev, {
        model: (draft.code_dev.model || "").trim() || "composer-2.5",
        max_concurrent: Math.max(1, Number(draft.code_dev.max_concurrent) || 1),
        cursor_timeout_sec: Math.max(60, Number(draft.code_dev.cursor_timeout_sec) || 2700),
        default_workspace: (draft.code_dev.default_workspace || "").trim(),
      }),
      code_review: Object.assign({}, draft.code_review, {
        enabled: true,
        max_files: Math.max(1, Number(draft.code_review.max_files) || 40),
        max_file_bytes: Math.max(1024, Number(draft.code_review.max_file_bytes) || 120000),
        max_total_bytes: Math.max(4096, Number(draft.code_review.max_total_bytes) || 800000),
        default_workspace: (draft.code_review.default_workspace || "").trim(),
      }),
      code_commit: Object.assign({}, draft.code_commit, {
        enabled: true,
        default_workspace: (draft.code_commit.default_workspace || "").trim(),
        work_branch: "",
        remote_name: (draft.code_commit.remote_name || "").trim() || "origin",
        default_push: draft.code_commit.default_push !== false,
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
      automations: Object.assign({}, draft.automations || {}, {
        wecom_webhook_key: (draft.automations && draft.automations.wecom_webhook_key) || "",
        wecom_push_enabled: !!(draft.automations && draft.automations.wecom_push_enabled),
        wecom_push_dry_run: !!(draft.automations && draft.automations.wecom_push_dry_run),
        feishu_app_id: String((draft.automations && draft.automations.feishu_app_id) || "").trim(),
        feishu_app_secret: (draft.automations && draft.automations.feishu_app_secret) || "",
        feishu_bitable_enabled: !!(draft.automations && draft.automations.feishu_bitable_enabled),
        feishu_bitable_dry_run: !!(draft.automations && draft.automations.feishu_bitable_dry_run),
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
          vision: Object.assign({}, base.vision, c.vision || {}),
          code_dev: Object.assign({}, base.code_dev, c.code_dev || {}),
          code_review: Object.assign({}, base.code_review, c.code_review || {}),
          code_commit: Object.assign({}, base.code_commit, c.code_commit || {}),
          code_deploy: Object.assign({}, base.code_deploy, c.code_deploy || {}),
          automations: Object.assign({}, base.automations, c.automations || {}),
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
  var vision = draft.vision || {};
  var cdp = draft.code_deploy;
  var auto = draft.automations || {};

  var VISION_PRESETS = [
    {
      id: "zhipu",
      label: "智谱 GLM-4V",
      base: "https://open.bigmodel.cn/api/paas/v4",
      model: "glm-4v-flash",
    },
    {
      id: "qwen-vl",
      label: "Qwen-VL",
      base: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      model: "qwen-vl-plus",
    },
    { id: "custom", label: "自定义", base: "", model: "" },
  ];

  function inferVisionPresetId() {
    var base = String(vision.base_url || "")
      .trim()
      .replace(/\/$/, "");
    if (!base) return vision.model ? "custom" : "";
    for (var i = 0; i < VISION_PRESETS.length; i++) {
      var p = VISION_PRESETS[i];
      if (p.id === "custom" || !p.base) continue;
      if (String(p.base).replace(/\/$/, "") === base) return p.id;
    }
    return "custom";
  }

  var visionPresetId = inferVisionPresetId();
  var visionKeyConfigured =
    !!vision.api_key && (/^•+$/.test(String(vision.api_key)) || String(vision.api_key).length > 0);

  function applyVisionPreset(p) {
    if (p.id === "custom") {
      setMsg("请自行填写视觉模型 Base URL 与模型名称");
      setMsgOk(true);
      return;
    }
    patchDraft(setDraft, ["vision", "base_url"], p.base);
    patchDraft(setDraft, ["vision", "model"], p.model);
    setMsg("已填入 " + p.label + "（请确认视觉 API Key）");
    setMsgOk(true);
  }

  function labeledField(label, props, full, meta) {
    var p = props || {};
    return h(
      "div",
      { className: "wb-set-field" + (full ? " full" : "") },
      h("label", null, label, h("span", { className: "wb-set-badge" }, "界面")),
      p.multiline ? h("textarea", p) : h("input", p),
      meta || null,
    );
  }

  var sectionMes = h(
    "div",
    { className: "wb-set-card" },
    h("h3", null, "MES 连接"),
    h(
      "div",
      { className: "body" },
      h("p", { className: "wb-set-hint" }, "业务系统 HTTP 接入；保存后写入引擎 config.yaml。"),
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
              var on = (mes.auth_type || "password") === v;
              return h(
                "label",
                { key: v, className: on ? "active" : "" },
                h("input", {
                  type: "radio",
                  name: "wb-mes-auth",
                  checked: on,
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
          { className: "wb-set-check full" },
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
        "div",
        { className: "wb-set-actions" },
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
      ),
      tests.mes ? h("div", { className: "wb-set-test" }, tests.mes) : null,
    ),
  );

  var sectionLlm = h(
    "div",
    { className: "wb-set-auto-stack" },
    h(
      "div",
      { className: "wb-set-card" },
      h("h3", null, "商用模型 / LLM 意图引擎"),
      h(
        "div",
        { className: "body" },
        h("p", { className: "wb-set-hint" }, "审码依赖此处 LLM；DeepSeek / Ollama / 关闭任选。"),
        h(
          "div",
          { className: "wb-set-field", style: { marginBottom: "12px" } },
          h("label", null, "提供方"),
          h(
            "div",
            { className: "wb-set-radios" },
            [
              ["deepseek", "DeepSeek API"],
              ["ollama", "Ollama 本地"],
              ["none", "不使用 LLM"],
            ].map(function (pair) {
              var on = (llm.provider || "deepseek") === pair[0];
              return h(
                "label",
                { key: pair[0], className: on ? "active" : "" },
                h("input", {
                  type: "radio",
                  name: "wb-llm",
                  checked: on,
                  onChange: function () {
                    patchDraft(setDraft, ["deepseek", "provider"], pair[0]);
                  },
                }),
                " ",
                pair[1],
              );
            }),
          ),
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
          "div",
          { className: "wb-set-actions" },
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
        ),
        tests.llm ? h("div", { className: "wb-set-test" }, tests.llm) : null,
      ),
    ),
    h(
      "div",
      { className: "wb-set-card" },
      h("h3", null, "视觉模型"),
      h(
        "div",
        { className: "body" },
        h("p", { className: "wb-set-hint", style: { marginBottom: "8px" } }, "快速填入视觉模型默认地址"),
        h(
          "div",
          { className: "wb-set-presets" },
          VISION_PRESETS.map(function (p) {
            return h(
              "button",
              {
                key: p.id,
                type: "button",
                className: "wb-set-preset" + (visionPresetId === p.id ? " active" : ""),
                onClick: function () {
                  applyVisionPreset(p);
                },
              },
              p.label,
            );
          }),
        ),
        h(
          "p",
          { className: "wb-set-hint" },
          "需支持多模态 / 识图的 OpenAI 兼容接口；未配置时贴图无法生成视觉规格。",
        ),
        h(
          "div",
          { className: "wb-set-grid" },
          labeledField(
            "API Key",
            {
              type: "password",
              autoComplete: "new-password",
              value: /^•+$/.test(String(vision.api_key || "")) ? "" : vision.api_key || "",
              placeholder: visionKeyConfigured
                ? "留空表示不修改；输入新值则覆盖"
                : "必填（智谱 / 通义等）",
              onChange: function (e) {
                patchDraft(setDraft, ["vision", "api_key"], e.target.value);
              },
            },
            true,
            visionKeyConfigured
              ? h(
                  "div",
                  { className: "wb-set-field-meta" },
                  /^•+$/.test(String(vision.api_key || ""))
                    ? "当前已配置（已脱敏）"
                    : "当前已配置：" +
                      String(vision.api_key || "")
                        .replace(/./g, "*")
                        .slice(0, 8) +
                      (String(vision.api_key || "").length > 4
                        ? String(vision.api_key || "").slice(-4)
                        : "****"),
                  h(
                    "button",
                    {
                      type: "button",
                      className: "wb-set-clear",
                      onClick: function () {
                        patchDraft(setDraft, ["vision", "api_key"], "");
                        setMsg("已清除视觉 API Key，保存后生效");
                        setMsgOk(true);
                      },
                    },
                    "清除界面覆盖",
                  ),
                )
              : null,
          ),
          labeledField(
            "API Base URL",
            {
              value: vision.base_url || "",
              placeholder: "https://open.bigmodel.cn/api/paas/v4",
              onChange: function (e) {
                patchDraft(setDraft, ["vision", "base_url"], e.target.value);
              },
            },
            true,
            h("div", { className: "wb-set-field-meta" }, "例：https://open.bigmodel.cn/api/paas/v4/"),
          ),
          labeledField(
            "视觉模型名称",
            {
              value: vision.model || "",
              placeholder: "glm-4v-flash",
              onChange: function (e) {
                patchDraft(setDraft, ["vision", "model"], e.target.value);
              },
            },
            true,
            h(
              "div",
              { className: "wb-set-field-meta" },
              "例：glm-4v-flash、glm-4v、qwen-vl-plus",
            ),
          ),
        ),
      ),
    ),
  );

  var sectionCdp = h(
    "div",
    { className: "wb-set-card" },
    h("h3", null, "自动化部署"),
    h(
      "div",
      { className: "body" },
      h(
        "p",
        { className: "wb-set-hint" },
        "开启后：确认一次即同步到远端。Vite+后端项目会本机构建 frontend/dist、同步 backend，并自动重启远端 API。不自动 git commit。一体部署才会拉远端 WorkBuddy 引擎。"
      ),
      h(
        "div",
        { className: "wb-set-check", style: { marginBottom: "8px" } },
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
        { className: "wb-set-check", style: { marginBottom: "12px" } },
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
        field(
          "远端重启命令（可选；不填则自动重启该目录的 API 服务）",
          {
            value: cdp.remote_restart_cmd || "",
            onChange: function (e) {
              patchDraft(setDraft, ["code_deploy", "remote_restart_cmd"], e.target.value);
            },
          },
          true,
        ),
      ),
      h(
        "div",
        { className: "wb-set-actions" },
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
      ),
      tests.cdp ? h("div", { className: "wb-set-test" }, tests.cdp) : null,
    ),
  );

  var sectionAuto = h(
    "div",
    { className: "wb-set-auto-stack" },
    h(
      "div",
      { className: "wb-set-card" },
      h("h3", null, "自动化任务推送"),
      h(
        "div",
        { className: "body" },
        h(
          "p",
          { className: "wb-set-hint" },
          "企微群消息与飞书多维表格写数是两套独立能力，可只开其一。保存写入引擎 config.yaml → automations。",
        ),
        h(
          "div",
          { className: "wb-set-grid" },
          field(
            "群机器人 Webhook",
            {
              type: "password",
              autoComplete: "new-password",
              value: auto.wecom_webhook_key || "",
              placeholder: "完整 Webhook 地址，或 key= 后的值",
              onChange: function (e) {
                patchDraft(setDraft, ["automations", "wecom_webhook_key"], e.target.value);
              },
            },
            true,
          ),
        ),
        h(
          "div",
          { className: "wb-set-check", style: { marginBottom: "8px" } },
          h("input", {
            type: "checkbox",
            checked: !!auto.wecom_push_enabled,
            onChange: function (e) {
              patchDraft(setDraft, ["automations", "wecom_push_enabled"], e.target.checked);
            },
          }),
          h("span", null, "开启自动化结果推送"),
        ),
        h(
          "div",
          { className: "wb-set-check" },
          h("input", {
            type: "checkbox",
            checked: !!auto.wecom_push_dry_run,
            onChange: function (e) {
              patchDraft(setDraft, ["automations", "wecom_push_dry_run"], e.target.checked);
            },
          }),
          h("span", null, "推送联调模式（仅打日志）"),
        ),
        h(
          "p",
          { className: "wb-set-hint", style: { marginTop: "12px", marginBottom: 0 } },
          "开启后，任务勾选「推送到企业微信」且执行成功时会发到上述群；联调模式不真正调用企微接口。",
        ),
      ),
    ),
    h(
      "div",
      { className: "wb-set-card" },
      h("h3", null, "飞书多维表格同步"),
      h(
        "div",
        { className: "body" },
        h(
          "div",
          { className: "wb-set-grid" },
          field(
            "飞书应用 App ID",
            {
              value: auto.feishu_app_id || "",
              placeholder: "cli_xxxxxxxx",
              onChange: function (e) {
                patchDraft(setDraft, ["automations", "feishu_app_id"], e.target.value);
              },
            },
            true,
          ),
          field(
            "飞书应用 App Secret",
            {
              type: "password",
              autoComplete: "new-password",
              value: auto.feishu_app_secret || "",
              placeholder: "开放平台凭证页复制；勿提交 git",
              onChange: function (e) {
                patchDraft(setDraft, ["automations", "feishu_app_secret"], e.target.value);
              },
            },
            true,
          ),
        ),
        h(
          "div",
          { className: "wb-set-check", style: { marginBottom: "8px", marginTop: "4px" } },
          h("input", {
            type: "checkbox",
            checked: !!auto.feishu_bitable_enabled,
            onChange: function (e) {
              patchDraft(setDraft, ["automations", "feishu_bitable_enabled"], e.target.checked);
            },
          }),
          h("span", null, "开启飞书多维表格同步"),
        ),
        h(
          "div",
          { className: "wb-set-check" },
          h("input", {
            type: "checkbox",
            checked: !!auto.feishu_bitable_dry_run,
            onChange: function (e) {
              patchDraft(setDraft, ["automations", "feishu_bitable_dry_run"], e.target.checked);
            },
          }),
          h("span", null, "写表联调模式（仅打日志）"),
        ),
        h(
          "p",
          { className: "wb-set-hint", style: { marginTop: "12px", marginBottom: 0 } },
          "总开关与企微互不干涉。任务还需开启「同步到飞书多维表格」并填写 app_token / table_id。",
        ),
      ),
    ),
  );

  var isPluginTab = tab === "remote_review" || tab === "cursor_coding";
  var pluginPanelProps = {
    apiRef: pluginApiRef,
    reportStatus: reportPluginStatus,
  };
  var activeSection =
    tab === "llm"
      ? sectionLlm
      : tab === "remote_review"
        ? h(WbRemoteReviewPanel, pluginPanelProps)
        : tab === "cursor_coding"
          ? h(WbCursorCodingPanel, pluginPanelProps)
          : tab === "code_deploy"
            ? sectionCdp
            : tab === "automations"
              ? sectionAuto
              : sectionMes;

  return h(
    "div",
    { className: "wb-set", ref: rootRef },
    h(
      "p",
      { className: "wb-set-lead" },
      "WorkBuddy 配置中心：MES / 商用模型 / 远端审码 / Cursor 写码 / 部署 / 推送。底部统一保存当前页。",
    ),
    h(
      "div",
      { className: "wb-set-shell" },
      h(
        "nav",
        { className: "wb-set-nav", "aria-label": "配置分类" },
        SET_NAV.map(function (item) {
          return h(
            "button",
            {
              key: item.id,
              type: "button",
              className: "wb-set-nav-btn" + (tab === item.id ? " active" : ""),
              onClick: function () {
                setTab(item.id);
                setMsg("");
              },
            },
            item.label,
          );
        }),
      ),
      h(
        "div",
        { className: "wb-set-main" },
        isPluginTab
          ? null
          : h(
              "div",
              { className: "wb-set-eng" },
              h(
                "div",
                { className: "eng-field" },
                h("label", null, "引擎 host"),
                h("input", {
                  value: engHost,
                  onChange: function (e) {
                    setEngHost(e.target.value);
                  },
                }),
              ),
              h(
                "div",
                { className: "eng-field" },
                h("label", null, "port"),
                h("input", {
                  value: engPort,
                  onChange: function (e) {
                    setEngPort(e.target.value);
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
                    applyEngineEndpoint();
                    loadConfig();
                  },
                },
                "连接并加载",
              ),
            ),
        activeSection,
      ),
    ),
    h(
      "div",
      { className: "wb-set-bar" },
      msg
        ? h("span", { className: "wb-set-msg" + (msgOk ? " ok" : " err") }, msg)
        : null,
      h(
        "button",
        {
          type: "button",
          className: "wb-set-btn",
          disabled: busy,
          onClick: loadCurrent,
        },
        "重新加载",
      ),
      h(
        "button",
        {
          type: "button",
          className: "wb-set-btn primary",
          disabled: busy,
          onClick: saveCurrent,
        },
        busy ? "处理中…" : "保存配置",
      ),
    ),
  );
}

  ctx.field = field;
  ctx.hideHostSettingsDupes = hideHostSettingsDupes;
  ctx.WbRemoteReviewPanel = WbRemoteReviewPanel;
  ctx.WbCursorCodingPanel = WbCursorCodingPanel;
  ctx.WorkBuddyHeaderLogout = WorkBuddyHeaderLogout;
  ctx.WorkBuddySettingsSection = WorkBuddySettingsSection;
}

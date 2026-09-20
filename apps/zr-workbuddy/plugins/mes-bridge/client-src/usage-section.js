export function installUsageSection(ctx) {
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
  var fmtUsageTokens = ctx.fmtUsageTokens,
      fmtUsageTokensTitle = ctx.fmtUsageTokensTitle,
      qualityLabel = ctx.qualityLabel,
      usageNiceMax = ctx.usageNiceMax,
      usageMd = ctx.usageMd,
      usageMonthLabel = ctx.usageMonthLabel,
      usageShowDayTick = ctx.usageShowDayTick,
      usageChartWidth = ctx.usageChartWidth,
      usagePlotBox = ctx.usagePlotBox,
      usageXTickAnchor = ctx.usageXTickAnchor,
      usageTipShift = ctx.usageTipShift,
      usageChartScroll = ctx.usageChartScroll,
      usageAlignMonthScroll = ctx.usageAlignMonthScroll,
      usageHourScrollIndex = ctx.usageHourScrollIndex,
      usageScrollToFocus = ctx.usageScrollToFocus,
      usageScrollToHour = ctx.usageScrollToHour,
      usageTodayYmd = ctx.usageTodayYmd,
      usageAddDays = ctx.usageAddDays,
      usageKpiDayLabel = ctx.usageKpiDayLabel,
      usageCatmullPath = ctx.usageCatmullPath,
      usageCurveSvg = ctx.usageCurveSvg,
      UsageCurveChart = ctx.UsageCurveChart,
      usageStackSvg = ctx.usageStackSvg,
      UsageStackChart = ctx.UsageStackChart,
      usageHourRange = ctx.usageHourRange,
      usageHourCombinedRows = ctx.usageHourCombinedRows,
      usageDayCombinedRows = ctx.usageDayCombinedRows,
      usageDualCombinedSvg = ctx.usageDualCombinedSvg,
      UsageDualCombinedChart = ctx.UsageDualCombinedChart,
      usageHourCombinedCard = ctx.usageHourCombinedCard,
      usageKpiCard = ctx.usageKpiCard,
      usageTodayKpis = ctx.usageTodayKpis,
      usageMeterNode = ctx.usageMeterNode,
      usageMonthRangeFromDay = ctx.usageMonthRangeFromDay,
      usagePeopleHBars = ctx.usagePeopleHBars,
      usagePeopleBarsNode = ctx.usagePeopleBarsNode;
  var WorkBuddyLoginForm = ctx.WorkBuddyLoginForm;

function WorkBuddyUsageSection(props) {
  ensureCss();
  var AUTH_LS = "mes_auth_session";
  var ENTERPRISES = [
    { key: "jsry", label: "江苏软云", code: "" },
    { key: "jxzr", label: "江西中软", code: "" },
    { key: "qhzr", label: "前海中软", code: "" },
  ];
  var scope = props && props.scope === "enterprise" ? "enterprise" : "personal";
  var onScopeChange = props && typeof props.onScopeChange === "function" ? props.onScopeChange : null;
  var onAdminChange = props && typeof props.onAdminChange === "function" ? props.onAdminChange : null;
  var busyState = useState(false);
  var busy = busyState[0];
  var setBusy = busyState[1];
  var msgState = useState("");
  var msg = msgState[0];
  var setMsg = msgState[1];
  var msgOkState = useState(false);
  var msgOk = msgOkState[0];
  var setMsgOk = msgOkState[1];
  var dataState = useState(null);
  var data = dataState[0];
  var setData = dataState[1];
  var onDateState = useState(usageTodayYmd);
  var onDate = onDateState[0];
  var setOnDate = onDateState[1];
  var pageRef = useRef(null);
  var userState = useState(null);
  var authUser = userState[0];
  var setAuthUser = userState[1];
  var authReadyState = useState(false);
  var authReady = authReadyState[0];
  var setAuthReady = authReadyState[1];
  var authErrState = useState("");
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
  var peopleGrainState = useState("day");
  var peopleGrain = peopleGrainState[0];
  var setPeopleGrain = peopleGrainState[1];
  var peopleRowsState = useState([]);
  var peopleRows = peopleRowsState[0];
  var setPeopleRows = peopleRowsState[1];
  var peoplePeriodState = useState("");
  var peoplePeriod = peoplePeriodState[0];
  var setPeoplePeriod = peoplePeriodState[1];

  function readSession() {
    try {
      var raw = localStorage.getItem(AUTH_LS);
      if (!raw) return null;
      var data0 = JSON.parse(raw);
      if (!data0 || !data0.access_token) return null;
      if (data0.expires_at && Date.now() / 1000 > Number(data0.expires_at) - 30) {
        try {
          localStorage.removeItem(AUTH_LS);
        } catch (e) {}
        return null;
      }
      return data0;
    } catch (e) {
      return null;
    }
  }
  function writeSession(session) {
    try {
      if (session && session.access_token) localStorage.setItem(AUTH_LS, JSON.stringify(session));
      else localStorage.removeItem(AUTH_LS);
    } catch (e) {}
  }
  function authHeaders() {
    var s = readSession();
    return s && s.access_token ? { Authorization: "Bearer " + s.access_token } : {};
  }
  function selectedEnt() {
    return ENTERPRISES.find(function (e) { return e.key === entKey; }) || ENTERPRISES[1];
  }

  function loadUsage(day, scopeOverride, grainOverride) {
    if (!authUser) return;
    var d = day || onDate || usageTodayYmd();
    var sc = scopeOverride || scope;
    var isEnt = sc === "enterprise" && String(authUser.role || "") === "admin";
    var grain = grainOverride || peopleGrain || "day";
    if (grain !== "month") grain = "day";
    var path = isEnt
      ? "/api/usage/enterprise/summary?days=7&grain=" +
        encodeURIComponent(grain) +
        "&on="
      : "/api/usage/summary?days=7&grain=" +
        encodeURIComponent(grain) +
        "&on=";
    setBusy(true);
    setMsg("加载中…");
    setMsgOk(false);
    fetch(engineBase() + path + encodeURIComponent(d), {
      headers: authHeaders(),
    })
      .then(function (r) {
        if (r.status === 401) {
          writeSession(null);
          setAuthUser(null);
          throw new Error("登录已失效，请重新登录");
        }
        if (r.status === 403) {
          throw new Error("仅管理员可查看企业用量");
        }
        return r.json();
      })
      .then(function (s) {
        if (!s || !s.ok) {
          throw new Error((s && (s.detail || s.message)) || "引擎未响应");
        }
        setData(s);
        // 按月模式保留月份锚点（用 month_from），避免被单日 on 冲掉
        if (s.grain === "month" && s.month_from) {
          setOnDate(String(s.month_from).slice(0, 10));
        } else if (s.on && s.on !== d && grain === "day") {
          setOnDate(s.on);
        }
        setMsg(
          isEnt
            ? grain === "month"
              ? "已加载企业整月用量"
              : "已加载企业总用量"
            : grain === "month"
              ? "已加载个人整月用量"
              : "已从引擎加载",
        );
        setMsgOk(true);
      })
      .catch(function (err) {
        setMsg(
          "加载失败：" +
            (err && err.message ? err.message : String(err)) +
            "（请先 scripts/engine.sh zr-workbuddy ensure）",
        );
        setMsgOk(false);
      })
      .finally(function () {
        setBusy(false);
      });
  }

  function loadPeople(day, grainOverride) {
    if (!authUser || String(authUser.role || "") !== "admin") {
      setPeopleRows([]);
      setPeoplePeriod("");
      return;
    }
    var d = day || onDate || usageTodayYmd();
    var grain = grainOverride || peopleGrain || "day";
    var from = d;
    var to = d;
    var periodLabel = d;
    if (grain === "month") {
      var mr = usageMonthRangeFromDay(d);
      from = mr.from;
      to = mr.to;
      periodLabel = mr.label;
    }
    var q =
      "from=" +
      encodeURIComponent(from) +
      "&to=" +
      encodeURIComponent(to) +
      "&grain=" +
      encodeURIComponent(grain);
    fetch(engineBase() + "/api/usage/enterprise/people?" + q, { headers: authHeaders() })
      .then(function (r) {
        if (r.status === 401) {
          writeSession(null);
          setAuthUser(null);
          throw new Error("登录已失效");
        }
        if (r.status === 403) throw new Error("仅管理员可查看");
        return r.json();
      })
      .then(function (p) {
        if (!p || !p.ok) throw new Error((p && p.detail) || "按人汇总失败");
        var rows = p.rows || [];
        // 同人多 period 时按人聚合（容错）
        var by = {};
        rows.forEach(function (r) {
          var uid = String(r.user_id || "");
          if (!uid) return;
          if (!by[uid]) {
            by[uid] = {
              user_id: uid,
              username: r.username || "",
              display_name: r.display_name || "",
              period: r.period || periodLabel,
              llm_tokens: 0,
              llm_calls: 0,
              cursor_tokens: 0,
              cursor_calls: 0,
            };
          }
          by[uid].llm_tokens += Number(r.llm_tokens) || 0;
          by[uid].llm_calls += Number(r.llm_calls) || 0;
          by[uid].cursor_tokens += Number(r.cursor_tokens) || 0;
          by[uid].cursor_calls += Number(r.cursor_calls) || 0;
          if (r.display_name) by[uid].display_name = r.display_name;
          if (r.username) by[uid].username = r.username;
        });
        setPeopleRows(Object.keys(by).map(function (k) { return by[k]; }));
        setPeoplePeriod(periodLabel);
      })
      .catch(function () {
        setPeopleRows([]);
        setPeoplePeriod(periodLabel);
      });
  }

  function refreshAuth() {
    var sess = readSession();
    if (!sess) {
      setAuthUser(null);
      setAuthReady(true);
      if (onAdminChange) onAdminChange(false);
      return;
    }
    fetch(engineBase() + "/api/auth/me", { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok && d.authenticated && d.user) {
          setAuthUser(d.user);
          if (onAdminChange) onAdminChange(String(d.user.role || "") === "admin");
        } else {
          writeSession(null);
          setAuthUser(null);
          if (onAdminChange) onAdminChange(false);
        }
      })
      .catch(function () {
        setAuthUser(null);
        if (onAdminChange) onAdminChange(false);
      })
      .finally(function () {
        setAuthReady(true);
      });
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
        writeSession({
          access_token: d.token,
          token_type: d.token_type || "Bearer",
          username: (d.user && d.user.username) || u,
          display_name: (d.user && d.user.display_name) || u,
          user_id: (d.user && d.user.id) || "",
          enterprise_code: String(selectedEnt().code || "").trim(),
          expires_at: d.expires_at,
        });
        setAuthUser(d.user || null);
        setLoginPass("");
        setAuthErr("");
        if (onAdminChange) onAdminChange(String((d.user && d.user.role) || "") === "admin");
      })
      .catch(function (err) {
        writeSession(null);
        setAuthUser(null);
        setAuthErr(err && err.message ? err.message : String(err));
        if (onAdminChange) onAdminChange(false);
      })
      .finally(function () {
        setBusy(false);
      });
  }

  useEffect(function () {
    refreshAuth();
    function onAuth() {
      refreshAuth();
    }
    window.addEventListener(AUTH_EVENT, onAuth);
    return function () {
      window.removeEventListener(AUTH_EVENT, onAuth);
    };
  }, []);

  useEffect(
    function () {
      if (authReady && authUser) {
        var isAdmin = String(authUser.role || "") === "admin";
        if (scope === "enterprise" && !isAdmin && onScopeChange) {
          onScopeChange("personal");
          return;
        }
        loadUsage(onDate, scope, peopleGrain);
        if (scope === "enterprise" && isAdmin) loadPeople(onDate, peopleGrain);
        else {
          setPeopleRows([]);
          setPeoplePeriod("");
        }
      }
    },
    [authReady, authUser, scope, peopleGrain],
  );

  useLayoutEffect(function () {
    if (!data || !pageRef.current) return;
    if (peopleGrain === "month") {
      usageScrollToFocus(pageRef.current, data.monthly || data.daily || [], data.on || onDate);
      return;
    }
    usageScrollToHour(pageRef.current, data.hourly || []);
  }, [data, onDate, peopleGrain]);

  var llm = (data && data.llm) || {};
  var cursor = (data && data.cursor) || {};
  var daily = (data && data.monthly) || (data && data.daily) || [];
  var monthLab = usageMonthLabel(data && data.month);
  var llmModel = (llm.models && llm.models[0] && llm.models[0].model) || "暂无调用";
  var curModel = (cursor.models && cursor.models[0] && cursor.models[0].model) || "暂无调用";
  var llmPal = { fill: "#93c5fd", stroke: "#3b82f6", hit: "#93c5fd", miss: "#3b82f6", out: "#1d4ed8" };
  var curPal = { fill: "#99f6e4", stroke: "#14b8a6", hit: "#99f6e4", miss: "#14b8a6", out: "#0f766e" };
  var hourly = (data && data.hourly) || [];
  var isEnt = scope === "enterprise";
  var monthMode = peopleGrain === "month";
  var meterAxis = monthMode ? "day" : "hour";
  var meterSeries = monthMode ? daily : hourly;
  var dayLab = monthMode
    ? ((isEnt ? "全员 · " : "") + (usageMonthLabel((data && data.month) || onDate) || String(onDate || "").slice(0, 7)))
    : usageKpiDayLabel((data && data.on) || onDate);
  if (isEnt && !monthMode && dayLab) dayLab = "全员 · " + dayLab;

  if (!authReady) {
    return h("div", { className: "wb-usage-page" }, h("p", { className: "wb-set-lead" }, "检查登录状态…"));
  }

  if (!authUser) {
    return h(
      "div",
      { className: "wb-usage-page wb-login-page", ref: pageRef },
      h(WorkBuddyLoginForm, {
        onSuccess: function (user) {
          setAuthUser(user);
          if (onAdminChange) onAdminChange(String((user && user.role) || "") === "admin");
        },
      }),
    );
  }

  return h(
    "div",
    { className: "wb-usage-page", ref: pageRef },
    h(
      "div",
      { className: "wb-usage-filter" },
      h("label", { htmlFor: "wb-usage-on" }, monthMode ? "月份" : "日期"),
      h("input", {
        id: "wb-usage-on",
        type: monthMode ? "month" : "date",
        value: monthMode ? String(onDate || "").slice(0, 7) : onDate,
        min: monthMode
          ? usageAddDays(usageTodayYmd(), -89).slice(0, 7)
          : usageAddDays(usageTodayYmd(), -89),
        max: monthMode ? usageTodayYmd().slice(0, 7) : usageTodayYmd(),
        onChange: function (ev) {
          var v = ev.target.value;
          if (!v) return;
          var day = v;
          if (v.length === 7) day = v + "-01";
          setOnDate(day);
          loadUsage(day, scope, peopleGrain);
          if (scope === "enterprise") loadPeople(day, peopleGrain);
        },
      }),
      h(
        "label",
        { htmlFor: "wb-people-grain", style: { marginLeft: "4px" } },
        "统计粒度",
      ),
      h(
        "select",
        {
          id: "wb-people-grain",
          value: peopleGrain,
          onChange: function (ev) {
            var g = ev.target.value === "month" ? "month" : "day";
            setPeopleGrain(g);
            loadUsage(onDate, scope, g);
            if (scope === "enterprise") loadPeople(onDate, g);
          },
        },
        h("option", { value: "day" }, "按日"),
        h("option", { value: "month" }, "按月"),
      ),
    ),
    usageTodayKpis(data && data.today, dayLab),
    usageHourCombinedCard(
      monthMode
        ? isEnt
          ? "各日用量（全员）"
          : "各日用量"
        : isEnt
          ? "各时段用量（全员）"
          : "各时段用量",
      monthMode ? daily : hourly,
      (data && data.on) || onDate,
      { monthMode: monthMode, monthLabel: (data && data.month) || onDate },
    ),
    usageMeterNode(
      isEnt ? "LLM（全员）" : "LLM",
      llmModel +
        (monthMode
          ? monthLab
            ? " · " + monthLab
            : ""
          : " · " + ((data && data.on) || onDate || "")),
      meterSeries,
      "llm_",
      llmPal,
      "",
      meterAxis,
    ),
    usageMeterNode(
      isEnt ? "Cursor 写码（全员）" : "Cursor 写码",
      curModel +
        (monthMode
          ? monthLab
            ? " · " + monthLab
            : ""
          : " · " + ((data && data.on) || onDate || "")),
      meterSeries,
      "cursor_",
      curPal,
      "",
      meterAxis,
    ),
    isEnt
      ? usagePeopleBarsNode(
          "员工用量（LLM + Cursor）",
          (peopleGrain === "month" ? "按月" : "按日") +
            " · " +
            (peoplePeriod || onDate || "") +
            " · 按合计 Token 从高到低 · 含全部账号（含管理员）· 共 " +
            String(peopleRows.length) +
            " 人",
          peopleRows,
        )
      : null,
    h(
      "div",
      { className: "wb-set-bar" },
      h(
        "button",
        {
          type: "button",
          className: "wb-set-btn",
          disabled: busy,
          onClick: function () {
            loadUsage(onDate, scope, peopleGrain);
            if (scope === "enterprise") loadPeople(onDate, peopleGrain);
          },
        },
        busy ? "刷新中…" : "刷新",
      ),
      msg ? h("span", { className: "wb-set-msg" + (msgOk ? " ok" : " err") }, msg) : null,
    ),
  );
}

  ctx.WorkBuddyUsageSection = WorkBuddyUsageSection;
}

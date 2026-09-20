export function installUsageView(ctx) {
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
  var WorkBuddyUsageSection = ctx.WorkBuddyUsageSection;

function usageNavIcon(size) {
  return h(
    "svg",
    { width: size, height: size, viewBox: "0 0 16 16", fill: "none", "aria-hidden": "true" },
    h("rect", { x: "2", y: "8", width: "3", height: "6", rx: "0.5", fill: "currentColor" }),
    h("rect", { x: "6.5", y: "4", width: "3", height: "10", rx: "0.5", fill: "currentColor" }),
    h("rect", { x: "11", y: "6", width: "3", height: "8", rx: "0.5", fill: "currentColor" }),
  );
}

function WorkBuddyUsageView(_props) {
  ensureCss();
  var scopeState = useState("personal");
  var scope = scopeState[0];
  var setScope = scopeState[1];
  var isAdminState = useState(false);
  var isAdmin = isAdminState[0];
  var setIsAdmin = isAdminState[1];
  return h(
    "div",
    { className: "wb-usage-view", "data-wb-usage-view": "1" },
    isAdmin
      ? h(
          "div",
          { className: "wb-usage-view-head" },
          h(
            "table",
            { className: "wb-usage-tabs", role: "tablist", "aria-label": "用量范围" },
            h(
              "tbody",
              null,
              h(
                "tr",
                null,
                h(
                  "td",
                  {
                    className: scope === "personal" ? "active" : "",
                    role: "presentation",
                  },
                  h(
                    "button",
                    {
                      type: "button",
                      role: "tab",
                      "aria-selected": scope === "personal",
                      onClick: function () {
                        setScope("personal");
                      },
                    },
                    "个人用量",
                  ),
                ),
                h(
                  "td",
                  {
                    className: scope === "enterprise" ? "active" : "",
                    role: "presentation",
                  },
                  h(
                    "button",
                    {
                      type: "button",
                      role: "tab",
                      "aria-selected": scope === "enterprise",
                      onClick: function () {
                        setScope("enterprise");
                      },
                    },
                    "企业用量",
                  ),
                ),
              ),
            ),
          ),
        )
      : null,
    h(
      "div",
      { className: "wb-usage-view-body" },
      h(WorkBuddyUsageSection, {
        scope: isAdmin ? scope : "personal",
        onScopeChange: function (next) {
          setScope(next === "enterprise" ? "enterprise" : "personal");
        },
        onAdminChange: function (admin) {
          setIsAdmin(!!admin);
          if (!admin) setScope("personal");
        },
      }),
    ),
  );
}

  ctx.usageNavIcon = usageNavIcon;
  ctx.WorkBuddyUsageView = WorkBuddyUsageView;
}

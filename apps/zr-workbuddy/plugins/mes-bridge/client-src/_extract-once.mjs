/**
 * One-shot mechanical split of lib/client.js → client-src ES modules.
 * Zero logic changes — wrap scopes only. Does NOT overwrite lib/client.js.
 *
 * Shared mutables (_wbClientCtx, _loginGateUnmount) become bag.* on the install
 * ctx so space / login-mount / apply share one bag (apply(ctx) would shadow).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BRIDGE = path.resolve(__dirname, "..");
const CLIENT = path.join(BRIDGE, "lib/client.js");
const OUT = __dirname;
const LANES = path.join(OUT, "lanes");

const lines = fs.readFileSync(CLIENT, "utf8").split(/\n/);

function sliceLines(start1, end1) {
  return lines.slice(start1 - 1, end1);
}

function dedentFactory(chunkLines) {
  return chunkLines
    .map((ln) => (ln.startsWith("    ") ? ln.slice(4) : ln))
    .join("\n")
    .replace(/\n+$/, "");
}

/** Shared mutables → bag.* (bag = install ctx; avoids apply(ctx) shadowing). */
function rewriteSharedMutablesAsBag(body) {
  return body
    .replace(/^[ \t]*var _loginGateUnmount = null;\n?/m, "")
    .replace(/^[ \t]*var _wbClientCtx = null;\n?/m, "")
    .replace(/\b_loginGateUnmount\b/g, "bag._loginGateUnmount")
    .replace(/\b_wbClientCtx\b/g, "bag._wbClientCtx");
}

const SHARED_BIND = `  var React = ctx.React, h = ctx.h, useState = ctx.useState, useEffect = ctx.useEffect,
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
      WorkspaceMismatchHint = ctx.WorkspaceMismatchHint;`;

const USAGE_HELPER_FUNCS = [
  "fmtUsageTokens",
  "fmtUsageTokensTitle",
  "qualityLabel",
  "usageNiceMax",
  "usageMd",
  "usageMonthLabel",
  "usageShowDayTick",
  "usageChartWidth",
  "usagePlotBox",
  "usageXTickAnchor",
  "usageTipShift",
  "usageChartScroll",
  "usageAlignMonthScroll",
  "usageHourScrollIndex",
  "usageScrollToFocus",
  "usageScrollToHour",
  "usageTodayYmd",
  "usageAddDays",
  "usageKpiDayLabel",
  "usageCatmullPath",
  "usageCurveSvg",
  "UsageCurveChart",
  "usageStackSvg",
  "UsageStackChart",
  "usageHourRange",
  "usageHourCombinedRows",
  "usageDayCombinedRows",
  "usageDualCombinedSvg",
  "UsageDualCombinedChart",
  "usageHourCombinedCard",
  "usageKpiCard",
  "usageTodayKpis",
  "usageMeterNode",
  "usageMonthRangeFromDay",
  "usagePeopleHBars",
  "usagePeopleBarsNode",
];

function usageHelperBind() {
  return (
    "  var " +
    USAGE_HELPER_FUNCS.map((n) => `${n} = ctx.${n}`).join(",\n      ") +
    ";"
  );
}

function wrapInstall(name, body, { bindExtra = "", attach = [] } = {}) {
  const attachBlock = attach.map((n) => `  ctx.${n} = ${n};`).join("\n");
  return (
    `export function ${name}(ctx) {\n` +
    SHARED_BIND +
    (bindExtra ? "\n" + bindExtra : "") +
    "\n\n" +
    body +
    "\n\n" +
    (attachBlock ? attachBlock + "\n" : "") +
    "}\n"
  );
}

function writeFile(rel, content) {
  const full = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  const text = content.endsWith("\n") ? content : content + "\n";
  fs.writeFileSync(full, text, "utf8");
  const st = fs.statSync(full);
  const lc = text.split(/\n/).length - (text.endsWith("\n") ? 1 : 0);
  console.log(
    `  ${rel.padEnd(36)} ${String(st.size).padStart(8)} bytes  ${String(lc).padStart(6)} lines`
  );
  return { rel, size: st.size, lines: lc };
}

fs.mkdirSync(LANES, { recursive: true });
console.log("Extracting from", CLIENT);
console.log("Into", OUT);
console.log("");

writeFile(
  "deps-init.js",
  `/** Create shared ctx with React bindings (esbuild entry helper). */
export function createCtx(require) {
  var React = require("react");
  return {
    React: React,
    h: React.createElement,
    useState: React.useState,
    useMemo: React.useMemo,
    useEffect: React.useEffect,
    useLayoutEffect: React.useLayoutEffect || React.useEffect,
    useRef: React.useRef,
    _wbClientCtx: null,
    _loginGateUnmount: null,
  };
}
`
);

{
  const body = dedentFactory(sliceLines(23, 160));
  const attach = [
    "engineHost",
    "enginePort",
    "engineBase",
    "AUTH_LS_KEY",
    "AUTH_ENTERPRISES",
    "AUTH_EVENT",
    "readAuthSession",
    "writeAuthSession",
    "authHeaders",
    "notifyAuthChanged",
    "doAppLogout",
    "pickLocalFolder",
    "issueHitl",
    "discoverEngine",
  ];
  writeFile(
    "shared-preamble.js",
    `export function installPreamble(ctx) {\n` +
      `  var React = ctx.React, h = ctx.h, useState = ctx.useState, useEffect = ctx.useEffect,\n` +
      `      useLayoutEffect = ctx.useLayoutEffect, useRef = ctx.useRef, useMemo = ctx.useMemo;\n\n` +
      body +
      "\n\n" +
      attach.map((n) => `  ctx.${n} = ${n};`).join("\n") +
      "\n}\n"
  );
}

writeFile(
  "css.js",
  `import cssText from './styles.css';

export function installCss(ctx) {
  var cssInjected = false;
  function ensureCss() {
    if (typeof document === "undefined") return;
    var ver = "composer-105";
    if (cssInjected && document.querySelector("style[data-wb-cd-css='" + ver + "']")) return;
    document.querySelectorAll("style[data-plugin='@dsh-external/dsh-mes-bridge']").forEach(function (el) {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
    cssInjected = true;
    var s = document.createElement("style");
    s.dataset.plugin = "@dsh-external/dsh-mes-bridge";
    s.dataset.wbCdCss = ver;
    s.textContent = cssText;
    document.head.appendChild(s);
  }
  ctx.ensureCss = ensureCss;
}
`
);

{
  const body = dedentFactory(sliceLines(195, 355));
  const attach = [
    "readMeta",
    "expandHomePath",
    "pathsEqual",
    "resolveDshCwd",
    "initialWorkspace",
    "textFromContentBlocks",
    "toolArgsMessage",
    "lastUserUtterance",
    "initialRequirement",
    "WorkspaceMismatchHint",
  ];
  writeFile(
    "shared-helpers.js",
    `export function installSharedHelpers(ctx) {\n` +
      `  var React = ctx.React, h = ctx.h, useState = ctx.useState, useEffect = ctx.useEffect,\n` +
      `      useLayoutEffect = ctx.useLayoutEffect, useRef = ctx.useRef, useMemo = ctx.useMemo;\n` +
      `  var engineBase = ctx.engineBase, engineHost = ctx.engineHost, enginePort = ctx.enginePort;\n` +
      `  var ensureCss = ctx.ensureCss;\n\n` +
      body +
      "\n\n" +
      attach.map((n) => `  ctx.${n} = ${n};`).join("\n") +
      "\n}\n"
  );
}

writeFile(
  "lanes/code-review.js",
  wrapInstall("installCodeReview", dedentFactory(sliceLines(357, 1239)), {
    attach: ["CodeReviewBeginCard"],
  })
);

writeFile(
  "lanes/code-commit.js",
  wrapInstall("installCodeCommit", dedentFactory(sliceLines(1241, 2702)), {
    attach: ["CodeCommitBeginCard"],
  })
);

writeFile(
  "lanes/code-dev.js",
  wrapInstall("installCodeDev", dedentFactory(sliceLines(2705, 7011)), {
    attach: ["CodeDevBeginCard"],
  })
);

writeFile(
  "lanes/code-deploy.js",
  wrapInstall("installCodeDeploy", dedentFactory(sliceLines(7013, 7470)), {
    attach: ["CodeDeployConfirmCard"],
  })
);

writeFile(
  "settings.js",
  wrapInstall("installSettings", dedentFactory(sliceLines(7472, 10002)), {
    attach: [
      "field",
      "hideHostSettingsDupes",
      "WbRemoteReviewPanel",
      "WbCursorCodingPanel",
      "WorkBuddyHeaderLogout",
      "WorkBuddySettingsSection",
    ],
  })
);

writeFile(
  "usage-helpers.js",
  wrapInstall("installUsageHelpers", dedentFactory(sliceLines(10004, 10825)), {
    attach: USAGE_HELPER_FUNCS,
  })
);

writeFile(
  "login.js",
  wrapInstall("installLogin", dedentFactory(sliceLines(10827, 11187)), {
    attach: ["WorkBuddyLoginForm", "WorkBuddyAppLoginGate", "mountAppLoginGate"],
  })
);

writeFile(
  "usage-section.js",
  wrapInstall("installUsageSection", dedentFactory(sliceLines(11189, 11681)), {
    bindExtra: usageHelperBind(),
    attach: ["WorkBuddyUsageSection"],
  })
);

writeFile(
  "space.js",
  wrapInstall(
    "installSpace",
    rewriteSharedMutablesAsBag(dedentFactory(sliceLines(11683, 13105))),
    {
      bindExtra: "  var bag = ctx;",
      attach: [
        "installWorkBuddySessionSwitchWatcher",
        "WorkBuddySessionSwitchGuard",
        "WorkBuddySpaceSection",
        "WorkBuddySpaceView",
      ],
    }
  )
);

writeFile(
  "usage-view.js",
  wrapInstall("installUsageView", dedentFactory(sliceLines(13107, 13199)), {
    bindExtra: "  var WorkBuddyUsageSection = ctx.WorkBuddyUsageSection;",
    attach: ["usageNavIcon", "WorkBuddyUsageView"],
  })
);

writeFile(
  "login-mount.js",
  wrapInstall(
    "installLoginMount",
    rewriteSharedMutablesAsBag(dedentFactory(sliceLines(13201, 13209))),
    {
      bindExtra:
        "  var bag = ctx;\n  var mountAppLoginGate = ctx.mountAppLoginGate;",
      attach: ["ensureLoginGateMounted"],
    }
  )
);

{
  const applyBody = rewriteSharedMutablesAsBag(
    dedentFactory(sliceLines(13211, 13393))
  );
  const bindExtra = [
    "  var bag = ctx;",
    "  var CodeReviewBeginCard = ctx.CodeReviewBeginCard;",
    "  var CodeCommitBeginCard = ctx.CodeCommitBeginCard;",
    "  var CodeDevBeginCard = ctx.CodeDevBeginCard;",
    "  var CodeDeployConfirmCard = ctx.CodeDeployConfirmCard;",
    "  var WorkBuddySettingsSection = ctx.WorkBuddySettingsSection;",
    "  var WorkBuddyHeaderLogout = ctx.WorkBuddyHeaderLogout;",
    "  var WorkBuddyAppLoginGate = ctx.WorkBuddyAppLoginGate;",
    "  var WorkBuddyUsageSection = ctx.WorkBuddyUsageSection;",
    "  var WorkBuddySpaceSection = ctx.WorkBuddySpaceSection;",
    "  var WorkBuddySpaceView = ctx.WorkBuddySpaceView;",
    "  var WorkBuddyUsageView = ctx.WorkBuddyUsageView;",
    "  var WorkBuddySessionSwitchGuard = ctx.WorkBuddySessionSwitchGuard;",
    "  var installWorkBuddySessionSwitchWatcher = ctx.installWorkBuddySessionSwitchWatcher;",
    "  var hideHostSettingsDupes = ctx.hideHostSettingsDupes;",
    "  var usageNavIcon = ctx.usageNavIcon;",
    "  var ensureLoginGateMounted = ctx.ensureLoginGateMounted;",
  ].join("\n");
  writeFile(
    "apply.js",
    wrapInstall("installApply", applyBody, {
      bindExtra,
      attach: ["apply"],
    })
  );
}

writeFile(
  "entry.js",
  `import { createCtx } from './deps-init.js';
import { installPreamble } from './shared-preamble.js';
import { installCss } from './css.js';
import { installSharedHelpers } from './shared-helpers.js';
import { installCodeReview } from './lanes/code-review.js';
import { installCodeCommit } from './lanes/code-commit.js';
import { installCodeDev } from './lanes/code-dev.js';
import { installCodeDeploy } from './lanes/code-deploy.js';
import { installSettings } from './settings.js';
import { installUsageHelpers } from './usage-helpers.js';
import { installLogin } from './login.js';
import { installUsageSection } from './usage-section.js';
import { installSpace } from './space.js';
import { installUsageView } from './usage-view.js';
import { installLoginMount } from './login-mount.js';
import { installApply } from './apply.js';

export function createBridgeModule(require) {
  var ctx = createCtx(require);
  installPreamble(ctx);
  installCss(ctx);
  installSharedHelpers(ctx);
  installCodeReview(ctx);
  installCodeCommit(ctx);
  installCodeDev(ctx);
  installCodeDeploy(ctx);
  installSettings(ctx);
  installUsageHelpers(ctx);
  installLogin(ctx);
  installUsageSection(ctx);
  installSpace(ctx);
  installUsageView(ctx);
  installLoginMount(ctx);
  installApply(ctx);
  return { inject: ['slots'], apply: ctx.apply };
}
`
);

const codeDevSrc = fs.readFileSync(path.join(OUT, "lanes/code-dev.js"), "utf8");
const hasCard = /function CodeDevBeginCard\b/.test(codeDevSrc);
console.log("\nCodeDevBeginCard in lanes/code-dev.js:", hasCard ? "YES" : "NO");

const helpersBody = dedentFactory(sliceLines(195, 355));
const helperFns = [...helpersBody.matchAll(/^function ([A-Za-z0-9_]+)/gm)].map(
  (m) => m[1]
);
console.log("\nshared-helpers functions on ctx:");
helperFns.forEach((n) => console.log("  -", n));

for (const f of ["space.js", "apply.js", "login-mount.js"]) {
  const src = fs.readFileSync(path.join(OUT, f), "utf8");
  const bareWb = (src.match(/(?<![.\w])_wbClientCtx\b/g) || []).length;
  const bareLg = (src.match(/(?<![.\w])_loginGateUnmount\b/g) || []).length;
  const bagRefs = (src.match(/bag\._wbClientCtx|bag\._loginGateUnmount/g) || [])
    .length;
  console.log(
    `${f}: bare _wbClientCtx=${bareWb} _loginGateUnmount=${bareLg}; bag.*=${bagRefs}`
  );
}

console.log("\nlib/client.js NOT overwritten.");
console.log("Backup: /tmp/client.js.before-esbuild-split");


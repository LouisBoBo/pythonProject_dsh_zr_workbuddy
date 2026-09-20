export function installApply(ctx) {
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
  var bag = ctx;
  var CodeReviewBeginCard = ctx.CodeReviewBeginCard;
  var CodeCommitBeginCard = ctx.CodeCommitBeginCard;
  var CodeDevBeginCard = ctx.CodeDevBeginCard;
  var CodeDeployConfirmCard = ctx.CodeDeployConfirmCard;
  var WorkBuddySettingsSection = ctx.WorkBuddySettingsSection;
  var WorkBuddyHeaderLogout = ctx.WorkBuddyHeaderLogout;
  var WorkBuddyAppLoginGate = ctx.WorkBuddyAppLoginGate;
  var WorkBuddyUsageSection = ctx.WorkBuddyUsageSection;
  var WorkBuddySpaceSection = ctx.WorkBuddySpaceSection;
  var WorkBuddySpaceView = ctx.WorkBuddySpaceView;
  var WorkBuddyUsageView = ctx.WorkBuddyUsageView;
  var WorkBuddySessionSwitchGuard = ctx.WorkBuddySessionSwitchGuard;
  var installWorkBuddySessionSwitchWatcher = ctx.installWorkBuddySessionSwitchWatcher;
  var hideHostSettingsDupes = ctx.hideHostSettingsDupes;
  var borrowChatStore = ctx.borrowChatStore;
  var usageNavIcon = ctx.usageNavIcon;
  var ensureLoginGateMounted = ctx.ensureLoginGateMounted;


function apply(ctx) {
  bag._wbClientCtx = ctx || null;
  ensureCss();
  discoverEngine();
  ensureLoginGateMounted();
  if (ctx && typeof ctx.effect === "function" && bag._loginGateUnmount) {
    ctx.effect(function () {
      return function () {
        if (bag._loginGateUnmount) {
          try {
            bag._loginGateUnmount();
          } catch (e0) {}
          bag._loginGateUnmount = null;
        }
      };
    }, "workbuddy-app-login-gate");
  }
  if (!ctx || !ctx.slots || typeof ctx.slots.inject !== "function") {
    console.error("[dsh-mes-bridge] 无 slots 服务：无法注册 WorkBuddy 客户端能力");
    return;
  }
  // 宿主官方 overlay 槽（若本版 DSH 有声明则双保险）
  try {
    ctx.slots.inject("shell.overlay", function () {
      return ctx.slots.register(
        {
          name: "shell.overlay",
          id: "workbuddy-login",
          order: 1,
          priority: 1,
        },
        WorkBuddyAppLoginGate,
      );
    });
  } catch (eOverlay) {
    console.warn("[dsh-mes-bridge] shell.overlay 不可用，仅用 DOM 登录挡板", eOverlay);
  }
  // 聊天顶栏右上角（session header utilities）+ 会话切换守卫
  try {
    ctx.slots.inject("conversation.session.header.utilities", function () {
      var chatStore = borrowChatStore(ctx.slots);
      var regs = [];
      regs.push(
        ctx.slots.register(
          {
            name: "conversation.session.header.utilities",
            id: "workbuddy-session-switch-guard",
            order: 0,
            store: chatStore || undefined,
          },
          WorkBuddySessionSwitchGuard,
        ),
      );
      regs.push(
        ctx.slots.register(
          {
            name: "conversation.session.header.utilities",
            id: "workbuddy-logout",
            order: 1,
            label: "账号",
          },
          WorkBuddyHeaderLogout,
        ),
      );
      return regs;
    });
  } catch (eHeader) {
    console.warn("[dsh-mes-bridge] header.utilities 不可用", eHeader);
  }
  // 主路径：订阅 sessions.list，不依赖 header（知识库盖住 conversation 时顶栏守卫不存在）
  try {
    if (typeof ctx.effect === "function") {
      ctx.effect(function () {
        return installWorkBuddySessionSwitchWatcher(ctx);
      }, "workbuddy-session-switch-watcher");
    } else {
      installWorkBuddySessionSwitchWatcher(ctx);
    }
  } catch (eWatch) {
    console.warn("[dsh-mes-bridge] session-switch watcher 安装失败", eWatch);
  }
  ctx.slots.inject("settings.section", function () {
    return ctx.slots.register(
      {
        name: "settings.section",
        id: "workbuddy",
        order: 5,
        label: "WorkBuddy",
      },
      WorkBuddySettingsSection,
    );
  });
  // 宿主侧栏「远端审码 / Cursor 写码」并入 WorkBuddy 后常驻隐藏，避免双入口
  try {
    hideHostSettingsDupes();
  } catch (eHide) {
    console.warn("[dsh-mes-bridge] hideHostSettingsDupes", eHide);
  }
  // 「资料库」「用量」均为 conversation.view，与对话/轨迹同级 tab（不再弹框）
  // 宿主同一槽位多次 inject 会互相覆盖（与当初 sidebar.footer 丢「用量」同类）；必须一次 inject 返回多项 register
  try {
    ctx.slots.inject("conversation.view", function () {
      var regs = [];
      if (typeof WorkBuddySpaceView === "function") {
        regs.push(
          ctx.slots.register(
            {
              name: "conversation.view",
              id: "workbuddy-library",
              order: 15,
              label: "资料库",
            },
            WorkBuddySpaceView,
          ),
        );
      } else {
        console.warn("[dsh-mes-bridge] WorkBuddySpaceView 未就绪，跳过资料库页签");
      }
      if (typeof WorkBuddyUsageView === "function") {
        regs.push(
          ctx.slots.register(
            {
              name: "conversation.view",
              id: "workbuddy-usage",
              order: 20,
              label: "用量",
            },
            WorkBuddyUsageView,
          ),
        );
      } else {
        console.warn("[dsh-mes-bridge] WorkBuddyUsageView 未就绪，跳过用量页签");
      }
      return regs;
    });
  } catch (eViews) {
    console.warn("[dsh-mes-bridge] conversation.view 资料库/用量页不可用", eViews);
  }
  ctx.slots.inject("tool.call.toolview", function () {
    return ctx.slots.register(
      { name: "tool.call.toolview", key: "mes_code_review_begin" },
      CodeReviewBeginCard,
    );
  });
  ctx.slots.inject("tool.call.toolview", function () {
    return ctx.slots.register(
      { name: "tool.call.toolview", key: "mes_code_commit_begin" },
      CodeCommitBeginCard,
    );
  });
  ctx.slots.inject("tool.call.toolview", function () {
    return ctx.slots.register(
      { name: "tool.call.toolview", key: "mes_code_dev_begin" },
      CodeDevBeginCard,
    );
  });
  ctx.slots.inject("tool.call.toolview", function () {
    return ctx.slots.register(
      { name: "tool.call.toolview", key: "mes_code_deploy_begin" },
      CodeDeployConfirmCard,
    );
  });
  ctx.slots.inject("tool.call.toolview", function () {
    return ctx.slots.register(
      { name: "tool.call.toolview", key: "mes_code_deploy_prepare" },
      CodeDeployConfirmCard,
    );
  });
  ctx.slots.inject("tool.call.toolview", function () {
    return ctx.slots.register(
      { name: "tool.call.toolview", key: "mes_code_deploy_confirm" },
      CodeDeployConfirmCard,
    );
  });
  console.log(
    "[dsh-mes-bridge] app-login-gate + settings.section=WorkBuddy + conversation.view=资料库/用量 + toolview review/commit/code_dev/deploy",
  );
  try {
    if (document && document.title && document.title.indexOf("WorkBuddy") < 0) {
      document.title = "WorkBuddy · " + document.title;
    }
  } catch (_eTitle) {}
}

// 模块一加载就挂登录挡板（不等 slots / apply），保证打开 :3081 就能看到
try {
  ensureLoginGateMounted();
} catch (eEager) {
  console.error("[dsh-mes-bridge] 登录挡板预挂载失败", eEager);
}

  ctx.apply = apply;
}

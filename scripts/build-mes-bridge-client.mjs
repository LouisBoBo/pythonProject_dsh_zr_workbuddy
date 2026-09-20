#!/usr/bin/env node
/**
 * 从 client-src/ 用 esbuild 打出 lib/client.js（单文件 + ModuleLoader 外壳）。
 *
 * 用法：
 *   node scripts/build-mes-bridge-client.mjs
 *   node scripts/build-mes-bridge-client.mjs --check   # 仅校验已构建产物可加载
 */
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const BRIDGE = join(ROOT, "apps/zr-workbuddy/plugins/mes-bridge");
const ENTRY = join(BRIDGE, "client-src/entry.js");
const CSS_FILE = join(BRIDGE, "client-src/styles.css");
const OUT = join(BRIDGE, "lib/client.js");
const TMP_DIR = join(BRIDGE, "client-src/.build");
const TMP_BUNDLE = join(TMP_DIR, "bridge-factory.cjs");

const RUNTIME = `/*RUNTIME_BEGIN*/
window.__APP_ENGINE__ = { host: "127.0.0.1", port: 8000 };
/*RUNTIME_END*/`;

function sha256(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function findEsbuild() {
  const require = createRequire(join(BRIDGE, "package.json"));
  try {
    return require.resolve("esbuild/bin/esbuild");
  } catch {
    try {
      return require.resolve("esbuild/bin/esbuild", { paths: [ROOT, BRIDGE] });
    } catch {
      return null;
    }
  }
}

function runEsbuild() {
  mkdirSync(TMP_DIR, { recursive: true });
  let bin = findEsbuild();
  const args = [
    ENTRY,
    "--bundle",
    "--format=cjs",
    "--platform=browser",
    "--target=es2019",
    "--external:react",
    "--loader:.css=text",
    `--outfile=${TMP_BUNDLE}`,
    "--log-level=warning",
  ];
  if (!bin) {
    // npx 拉取（仅本机构建；不写进发版默认依赖亦可）
    const r = spawnSync("npx", ["--yes", "esbuild", ...args], {
      cwd: BRIDGE,
      encoding: "utf8",
      env: process.env,
    });
    if (r.status !== 0) {
      console.error(r.stderr || r.stdout || "esbuild failed");
      process.exit(r.status || 1);
    }
    return;
  }
  // bin/esbuild is a native executable (not a JS file) — do not run via node
  const r = spawnSync(bin, args, {
    cwd: BRIDGE,
    encoding: "utf8",
  });
  if (r.status !== 0) {
    console.error(r.stderr || r.stdout || "esbuild failed");
    process.exit(r.status || 1);
  }
}

function wrapBundle(cjs) {
  return `${RUNTIME}
window.__ModuleLoader__.load({
  id: "@dsh-external/dsh-mes-bridge",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
${cjs}
    var __wbFactory =
      (exports && exports.createBridgeModule) ||
      (module.exports && module.exports.createBridgeModule);
    if (typeof __wbFactory !== "function") {
      throw new Error("[dsh-mes-bridge] createBridgeModule missing after bundle");
    }
    module.exports = __wbFactory(require);
    return module.exports;
  },
});
`;
}

function smokeFactory(clientSrc) {
  // 抽出 factory 体并在 mock ModuleLoader 下执行
  let captured = null;
  const sandbox = {
    window: {
      __APP_ENGINE__: { host: "127.0.0.1", port: 8000 },
      __ModuleLoader__: {
        load: function (spec) {
          captured = spec;
        },
      },
      localStorage: {
        getItem: function () {
          return null;
        },
        setItem: function () {},
        removeItem: function () {},
      },
      addEventListener: function () {},
      removeEventListener: function () {},
      dispatchEvent: function () {},
      CustomEvent: function () {},
    },
    document: {
      createElement: function () {
        return { dataset: {}, style: {}, appendChild: function () {} };
      },
      head: { appendChild: function () {} },
      querySelector: function () {
        return null;
      },
      querySelectorAll: function () {
        return [];
      },
      getElementById: function () {
        return null;
      },
      body: { appendChild: function () {} },
      title: "WorkBuddy",
    },
    console: console,
  };
  // eslint-disable-next-line no-new-func
  const fn = new Function(
    "window",
    "document",
    "console",
    clientSrc + "\n;return window;",
  );
  fn(sandbox.window, sandbox.document, sandbox.console);
  if (!captured || typeof captured.factory !== "function") {
    throw new Error("ModuleLoader factory not registered");
  }
  const React = {
    createElement: function () {
      return null;
    },
    useState: function (v) {
      return [v, function () {}];
    },
    useMemo: function (f) {
      return f();
    },
    useEffect: function () {},
    useLayoutEffect: function () {},
    useRef: function (v) {
      return { current: v };
    },
  };
  const mod = captured.factory(function (name) {
    if (name === "react") return React;
    throw new Error("unexpected require: " + name);
  });
  if (!mod || mod.inject?.[0] !== "slots" || typeof mod.apply !== "function") {
    throw new Error("bridge module shape invalid: " + JSON.stringify(Object.keys(mod || {})));
  }
  return mod;
}

function main() {
  const checkOnly = process.argv.includes("--check");
  if (!existsSync(ENTRY)) {
    console.error("缺少 entry:", ENTRY);
    process.exit(1);
  }
  if (!existsSync(CSS_FILE)) {
    console.error("缺少 styles.css");
    process.exit(1);
  }

  if (checkOnly) {
    if (!existsSync(OUT)) {
      console.error("缺少构建产物", OUT);
      process.exit(1);
    }
    const src = readFileSync(OUT, "utf8");
    if (!src.includes("/*RUNTIME_BEGIN*/") || !src.includes("/*RUNTIME_END*/")) {
      console.error("CHECK FAIL: RUNTIME 标记缺失");
      process.exit(1);
    }
    if (!src.includes("WB_CSS") && !src.includes(".wb-cr{")) {
      // 构建后 CSS 以字符串字面量嵌入，应含典型选择器
      console.error("CHECK FAIL: 未见面板 CSS 痕迹");
      process.exit(1);
    }
    try {
      smokeFactory(src);
    } catch (e) {
      console.error("CHECK FAIL: factory 烟测", e && e.message ? e.message : e);
      process.exit(1);
    }
    console.log("CHECK OK  client.js bytes=" + src.length + "  css.sha=" + sha256(readFileSync(CSS_FILE)));
    return;
  }

  console.log("esbuild bundle…");
  runEsbuild();
  const cjs = readFileSync(TMP_BUNDLE, "utf8");
  const out = wrapBundle(cjs);
  try {
    smokeFactory(out);
  } catch (e) {
    console.error("构建后烟测失败，未写盘:", e && e.message ? e.message : e);
    process.exit(1);
  }
  writeFileSync(OUT, out, "utf8");
  console.log("OK →", OUT);
  console.log("  bytes=" + out.length + "  styles.css.sha256=" + sha256(readFileSync(CSS_FILE)));
}

main();

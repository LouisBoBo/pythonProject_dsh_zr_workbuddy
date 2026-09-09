/**
 * ZR-WorkBuddy 宿主一体桌面壳
 * - 内嵌引擎（CPython）+ 内嵌 Host（staged dsh CLI）
 * - 使用独立 DSH_HOME（userData/dsh-home），不复用本机 ~/.dsh 里的皮肤/残缺 profile
 * - 启动时接线 link → 可写业务副本，并确保 mes-bridge
 * - 安装后在设置 / WorkBuddy 配置中心填 Key 即可用
 */
'use strict'

const { app, BrowserWindow, dialog, shell, ipcMain } = require('electron')
const { spawn, execFileSync } = require('child_process')
const http = require('http')
const net = require('net')
const fs = require('fs')
const path = require('path')
const os = require('os')

const ENGINE_PORT_START = Number(process.env.WORKBUDDY_DESKTOP_ENGINE_PORT || 18000)
const DSH_PORT_START = Number(process.env.WORKBUDDY_DESKTOP_DSH_PORT || 13080)
const LINK_NAME = 'DSH-ZR-WorkBuddy'
const BRIDGE_PKG = '@dsh-external/dsh-mes-bridge'
const BRIDGE_ID = 'dsh-mes-bridge'
const MARKET_PKG = 'dshmarket'
/** 旧 0.2.7/0.2.8 把 name 写成文件路径，client-modules 解析不了 package.json，设置里没有 WorkBuddy。 */
const BRIDGE_REL_LEGACY =
  `../../link/${LINK_NAME}/apps/zr-workbuddy/plugins/mes-bridge/lib/index.js`

/** @type {import('child_process').ChildProcess[]} */
const children = []
/** @type {BrowserWindow | null} */
let mainWindow = null
let shuttingDown = false
/** @type {string} */
let persistedEngineDir = ''

ipcMain.handle('workbuddy:pick-folder', async (event, prompt) => {
  const srcUrl = String((event.sender && event.sender.getURL && event.sender.getURL()) || '')
  if (!/^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(\/|$)/i.test(srcUrl)) {
    return { ok: false, path: '', error: '非法来源' }
  }
  const senderWin = BrowserWindow.fromWebContents(event.sender)
  const opts = {
    title: String(prompt || '选择工程目录'),
    properties: ['openDirectory', 'createDirectory'],
  }
  const result = senderWin
    ? await dialog.showOpenDialog(senderWin, opts)
    : await dialog.showOpenDialog(opts)
  if (result.canceled || !result.filePaths || !result.filePaths.length) {
    return { ok: false, path: '', error: '已取消选择' }
  }
  return { ok: true, path: result.filePaths[0], error: '' }
})

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })
}

function runtimeRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'runtime')
  }
  return path.join(__dirname, 'runtime')
}

function hostRuntimeRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'host')
  }
  return path.join(__dirname, 'runtime', 'host')
}

function marketRuntimeRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'market')
  }
  return path.join(__dirname, 'runtime', 'market')
}

function persistRoot() {
  return path.join(app.getPath('userData'), 'persist')
}

function stashEngineUserState(engineDir) {
  if (!engineDir || !fs.existsSync(engineDir)) return
  const persist = persistRoot()
  fs.mkdirSync(persist, { recursive: true })
  const cfg = path.join(engineDir, 'config', 'config.yaml')
  if (fs.existsSync(cfg)) {
    fs.copyFileSync(cfg, path.join(persist, 'config.yaml'))
  }
  const plugins = path.join(engineDir, 'data', 'plugins.json')
  if (fs.existsSync(plugins)) {
    fs.copyFileSync(plugins, path.join(persist, 'plugins.json'))
  }
  const lastDeploy = path.join(engineDir, 'data', 'code_deploy', 'last_deploy.json')
  if (fs.existsSync(lastDeploy)) {
    fs.mkdirSync(path.join(persist, 'code_deploy'), { recursive: true })
    fs.copyFileSync(lastDeploy, path.join(persist, 'code_deploy', 'last_deploy.json'))
  }
}

function restoreEngineUserState(engineDir) {
  const persist = persistRoot()
  const persistCfg = path.join(persist, 'config.yaml')
  const cfg = path.join(engineDir, 'config', 'config.yaml')
  if (fs.existsSync(persistCfg)) {
    fs.mkdirSync(path.dirname(cfg), { recursive: true })
    fs.copyFileSync(persistCfg, cfg)
  }
  const persistPlugins = path.join(persist, 'plugins.json')
  const destPlugins = path.join(engineDir, 'data', 'plugins.json')
  if (fs.existsSync(persistPlugins)) {
    fs.mkdirSync(path.dirname(destPlugins), { recursive: true })
    fs.copyFileSync(persistPlugins, destPlugins)
  }
  const persistLast = path.join(persist, 'code_deploy', 'last_deploy.json')
  const destLast = path.join(engineDir, 'data', 'code_deploy', 'last_deploy.json')
  if (fs.existsSync(persistLast)) {
    fs.mkdirSync(path.dirname(destLast), { recursive: true })
    fs.copyFileSync(persistLast, destLast)
  }
}

/** 一体包默认隔离；设 WORKBUDDY_USE_SYSTEM_DSH_HOME=1 才用本机 ~/.dsh */
function dshHome() {
  if (process.env.WORKBUDDY_USE_SYSTEM_DSH_HOME === '1') {
    return process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
  }
  if (process.env.DSH_HOME && process.env.DSH_HOME.length > 0) {
    return process.env.DSH_HOME
  }
  return path.join(app.getPath('userData'), 'dsh-home')
}

function applyDesktopDshHome() {
  const home = dshHome()
  process.env.DSH_HOME = home
  fs.mkdirSync(home, { recursive: true })
  return home
}

function ensureWritableAppCopy() {
  const srcApp = path.join(runtimeRoot(), 'app')
  const dstApp = path.join(app.getPath('userData'), 'runtime-app')
  const marker = path.join(dstApp, '.bundle_ready')
  const bundleVer = path.join(runtimeRoot(), 'app', 'version.json')
  let want = ''
  try {
    want = fs.readFileSync(bundleVer, 'utf8')
  } catch {
    want = 'unknown'
  }
  const needRefresh =
    !fs.existsSync(marker) ||
    (fs.existsSync(marker) && fs.readFileSync(marker, 'utf8').trim() !== want.trim())

  if (!fs.existsSync(srcApp)) {
    throw new Error(`缺少运行时 app：${srcApp}（请先 scripts/package-desktop.sh）`)
  }
  const eng = path.join(dstApp, 'apps', 'zr-workbuddy', 'engine')
  if (fs.existsSync(eng)) stashEngineUserState(eng)
  if (needRefresh) {
    fs.mkdirSync(path.dirname(dstApp), { recursive: true })
    if (fs.existsSync(dstApp)) {
      fs.rmSync(dstApp, { recursive: true, force: true })
    }
    fs.cpSync(srcApp, dstApp, { recursive: true })
    fs.writeFileSync(marker, want, 'utf8')
  }
  restoreEngineUserState(eng)
  const cfg = path.join(eng, 'config', 'config.yaml')
  const example = path.join(eng, 'config', 'config.example.yaml')
  if (!fs.existsSync(cfg) && fs.existsSync(example)) {
    fs.copyFileSync(example, cfg)
  }
  persistedEngineDir = eng
  return { appRoot: dstApp, engineDir: eng }
}

// Packaged copies omit feature plugin node_modules; materialize Bridge deps before boot.
function materializeBridgeDeps(appRoot) {
  const bridge = path.join(appRoot, 'apps', 'zr-workbuddy', 'plugins', 'mes-bridge')
  const toolsSrc = path.join(appRoot, 'vendor', '@deepseek-ai', 'dsh-tools')
  const runtimeSrc = path.join(appRoot, 'apps', 'zr-workbuddy', 'plugins', 'mes-runtime')
  const toolsDst = path.join(bridge, 'node_modules', '@deepseek-ai', 'dsh-tools')
  const runtimeDst = path.join(bridge, 'node_modules', '@dsh-external', 'mes-runtime')
  if (!fs.existsSync(bridge)) return
  if (fs.existsSync(toolsSrc)) {
    fs.mkdirSync(path.dirname(toolsDst), { recursive: true })
    if (fs.existsSync(toolsDst)) fs.rmSync(toolsDst, { recursive: true, force: true })
    fs.cpSync(toolsSrc, toolsDst, { recursive: true })
  }
  if (fs.existsSync(runtimeSrc)) {
    fs.mkdirSync(path.dirname(runtimeDst), { recursive: true })
    try {
      fs.lstatSync(runtimeDst)
      fs.rmSync(runtimeDst, { force: true, recursive: true })
    } catch {
      /* missing */
    }
    fs.symlinkSync(path.join('..', '..', '..', 'mes-runtime'), runtimeDst)
  }

  // dsh-tools 的 peer（cordis 等）在本机靠仓库根 node_modules；安装副本挂 Host 闭包
  const hostNested = path.join(
    hostRuntimeRoot(),
    'node_modules',
    '@deepseek-ai',
    'dsh',
    'node_modules'
  )
  if (!fs.existsSync(hostNested)) return
  const dstNm = path.join(appRoot, 'node_modules')
  fs.mkdirSync(dstNm, { recursive: true })
  const hostAi = path.join(hostNested, '@deepseek-ai')
  const dstAi = path.join(dstNm, '@deepseek-ai')
  if (fs.existsSync(hostAi)) {
    try {
      fs.lstatSync(dstAi)
      fs.rmSync(dstAi, { force: true, recursive: true })
    } catch {
      /* missing */
    }
    try {
      fs.symlinkSync(hostAi, dstAi)
    } catch {
      fs.cpSync(hostAi, dstAi, { recursive: true })
    }
  }
  for (const name of fs.readdirSync(hostNested)) {
    if (name.startsWith('@') || name === '.bin') continue
    const d = path.join(dstNm, name)
    if (fs.existsSync(d)) continue
    try {
      fs.symlinkSync(path.join(hostNested, name), d)
    } catch {
      /* ignore single fail */
    }
  }
}

function writeEngineRuntime(engineDir, port) {
  const cfgDir = path.join(engineDir, 'config')
  fs.mkdirSync(cfgDir, { recursive: true })
  fs.writeFileSync(
    path.join(cfgDir, 'runtime.yaml'),
    `server:\n  host: 127.0.0.1\n  port: ${port}\npython: python3\n`,
    'utf8'
  )
  const client = path.join(
    engineDir,
    '..',
    'plugins',
    'mes-bridge',
    'lib',
    'client.js'
  )
  if (fs.existsSync(client)) {
    let text = fs.readFileSync(client, 'utf8')
    const block =
      '/*RUNTIME_BEGIN*/\n' +
      `window.__APP_ENGINE__ = { host: "127.0.0.1", port: ${port} };\n` +
      '/*RUNTIME_END*/'
    const next = text.replace(
      /\/\*RUNTIME_BEGIN\*\/[\s\S]*?\/\*RUNTIME_END\*\//,
      block
    )
    if (next !== text) fs.writeFileSync(client, next, 'utf8')
  }
}

function findEngineLauncher() {
  const file = process.platform === 'win32' ? 'workbuddy-engine.cmd' : 'workbuddy-engine'
  const packed = path.join(runtimeRoot(), 'bin', file)
  if (fs.existsSync(packed)) return packed
  return ''
}

function findBundledCliEntry() {
  const cli = path.join(
    hostRuntimeRoot(),
    'node_modules',
    '@deepseek-ai',
    'dsh',
    'lib',
    'bin.js'
  )
  return fs.existsSync(cli) ? cli : ''
}

/** DSH 0.1.1-rc.2 需要 Node≥22（zstd / stripTypeScriptTypes）；禁止用 Electron 内嵌 Node 20 跑宿主。 */
function nodeMajorOf(bin) {
  try {
    const out = execFileSync(bin, ['-p', 'process.versions.node'], {
      encoding: 'utf8',
      timeout: 5000,
      env: { ...process.env, ELECTRON_RUN_AS_NODE: undefined },
    })
      .trim()
      .split('.')[0]
    return Number(out) || 0
  } catch {
    return 0
  }
}

function findHostNodeBinary() {
  if (process.env.WORKBUDDY_HOST_NODE && fs.existsSync(process.env.WORKBUDDY_HOST_NODE)) {
    const maj = nodeMajorOf(process.env.WORKBUDDY_HOST_NODE)
    if (maj >= 22) return process.env.WORKBUDDY_HOST_NODE
  }
  const bundled = path.join(
    runtimeRoot(),
    'node',
    'bin',
    process.platform === 'win32' ? 'node.exe' : 'node'
  )
  if (fs.existsSync(bundled) && nodeMajorOf(bundled) >= 22) return bundled

  const home = os.homedir()
  const candidates = []
  const nvmDir = path.join(home, '.nvm', 'versions', 'node')
  try {
    if (fs.existsSync(nvmDir)) {
      for (const name of fs.readdirSync(nvmDir)) {
        if (!/^v2[2-9]/.test(name) && !/^v[3-9]/.test(name)) continue
        candidates.push(path.join(nvmDir, name, 'bin', 'node'))
      }
    }
  } catch {
    /* ignore */
  }
  for (const c of [
    '/usr/local/bin/node',
    '/opt/homebrew/bin/node',
    path.join(home, '.local', 'bin', 'node'),
  ]) {
    candidates.push(c)
  }
  // PATH 上的 node
  const pathEnv = process.env.PATH || ''
  for (const dir of pathEnv.split(path.delimiter)) {
    if (!dir) continue
    candidates.push(path.join(dir, process.platform === 'win32' ? 'node.exe' : 'node'))
  }

  let best = ''
  let bestMaj = 0
  const seen = new Set()
  for (const c of candidates) {
    if (!c || seen.has(c)) continue
    seen.add(c)
    if (!fs.existsSync(c)) continue
    const maj = nodeMajorOf(c)
    if (maj >= 22 && maj > bestMaj) {
      best = c
      bestMaj = maj
    }
  }
  return best
}

function findBundledPnpmCjs() {
  const cands = [
    path.join(process.resourcesPath, 'pnpm', 'bin', 'pnpm.cjs'),
    path.join(__dirname, 'runtime', 'pnpm', 'node_modules', 'pnpm', 'bin', 'pnpm.cjs'),
    path.join(hostRuntimeRoot(), 'node_modules', 'pnpm', 'bin', 'pnpm.cjs'),
  ]
  for (const c of cands) {
    if (c && fs.existsSync(c)) return c
  }
  return ''
}

function findBundledPnpm() {
  return findBundledPnpmCjs()
}

/** 在可写目录放 pnpm 包装脚本：插件市场会 spawn("pnpm")，不能往 .app 里 npm i -g。 */
function ensureDesktopPnpmHome() {
  const home = path.join(app.getPath('userData'), 'pnpm-home')
  const nodeBin = findHostNodeBinary()
  const pnpmCjs = findBundledPnpmCjs()
  if (!nodeBin || !pnpmCjs) {
    console.warn('[desktop] 未内嵌 pnpm/Node，插件市场无法自动装包')
    return { home, ok: false }
  }
  fs.mkdirSync(home, { recursive: true })
  const shim = path.join(home, 'pnpm')
  const q = (s) => `"${String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
  fs.writeFileSync(shim, `#!/bin/sh\nexec ${q(nodeBin)} ${q(pnpmCjs)} "$@"\n`, 'utf8')
  try {
    fs.chmodSync(shim, 0o755)
  } catch {
    /* ignore */
  }
  return { home, ok: true }
}

function applyDesktopToolchain(env) {
  const nodeBin = findHostNodeBinary()
  const { home, ok } = ensureDesktopPnpmHome()
  env.CI = env.CI || 'true'
  if (ok) {
    env.PNPM_HOME = home
    env.npm_config_store_dir = path.join(app.getPath('userData'), 'pnpm-store')
  }
  const dirs = []
  if (ok) dirs.push(home)
  if (nodeBin) dirs.push(path.dirname(nodeBin))
  try {
    const nvmDir = path.join(os.homedir(), '.nvm', 'versions', 'node')
    if (fs.existsSync(nvmDir)) {
      const names = fs.readdirSync(nvmDir).filter((n) => /^v\d/.test(n)).sort()
      for (let i = names.length - 1; i >= 0; i--) {
        const bin = path.join(nvmDir, names[i], 'bin')
        if (fs.existsSync(path.join(bin, 'npm'))) {
          dirs.push(bin)
          break
        }
      }
    }
  } catch {
    /* ignore */
  }
  if (dirs.length) {
    env.PATH = `${dirs.join(path.delimiter)}${path.delimiter}${env.PATH || ''}`
  }
  if (ok) {
    console.log('[desktop] toolchain PNPM_HOME=', home)
  }
  return env
}

/** 公司插件市场配置（仅 DSHM_REGISTRY_URL + @zhongruan 私有源；不改其它逻辑） */
const COMPANY_MARKET_DEFAULTS = {
  DSHM_REGISTRY_URL: 'http://175.178.238.31/dsh-plugins/plugins.json',
  ZHONGRUAN_NPM_REGISTRY: 'http://175.178.238.31/dsh-plugins/npm/',
}

function loadCompanyDshMarketEnv(appRoot) {
  const out = { ...COMPANY_MARKET_DEFAULTS }
  const cfg = appRoot
    ? path.join(appRoot, 'apps', 'zr-workbuddy', 'config', 'company-dsh-market.env')
    : ''
  if (cfg && fs.existsSync(cfg)) {
    try {
      const text = fs.readFileSync(cfg, 'utf8')
      for (const line of text.split('\n')) {
        const t = line.trim()
        if (!t || t.startsWith('#')) continue
        const i = t.indexOf('=')
        if (i < 0) continue
        const key = t.slice(0, i).trim()
        const val = t.slice(i + 1).trim()
        if (key === 'DSHM_REGISTRY_URL' || key === 'ZHONGRUAN_NPM_REGISTRY') {
          out[key] = val
        }
      }
    } catch (e) {
      console.warn('[desktop] 读取 company-dsh-market.env 失败:', e && e.message ? e.message : e)
    }
  }
  if (process.env.DSHM_REGISTRY_URL) out.DSHM_REGISTRY_URL = process.env.DSHM_REGISTRY_URL
  if (process.env.ZHONGRUAN_NPM_REGISTRY) {
    out.ZHONGRUAN_NPM_REGISTRY = process.env.ZHONGRUAN_NPM_REGISTRY
  }
  return out
}

/** 只重写标记块，保留 profile .npmrc 其它内容 */
function ensureCompanyMarketNpmrc(profileDir, registry) {
  if (!registry || !profileDir || !fs.existsSync(profileDir)) return
  const npmrc = path.join(profileDir, '.npmrc')
  let body = ''
  if (fs.existsSync(npmrc)) {
    body = fs.readFileSync(npmrc, 'utf8')
    body = body.replace(
      /\n?# --- company-dsh-market ---[\s\S]*?# --- \/company-dsh-market ---\n?/g,
      '\n'
    )
  }
  const block =
    `# --- company-dsh-market ---\n` +
    `@zhongruan:registry=${registry}\n` +
    `strict-ssl=false\n` +
    `# --- /company-dsh-market ---\n`
  const next = (body.trimEnd() ? `${body.trimEnd()}\n` : '') + block
  fs.writeFileSync(npmrc, next, 'utf8')
}

function findPathDshBin() {
  if (process.env.DSH_BIN && fs.existsSync(process.env.DSH_BIN)) {
    return process.env.DSH_BIN
  }
  const pathEnv = process.env.PATH || ''
  for (const dir of pathEnv.split(path.delimiter)) {
    const cand = path.join(dir, process.platform === 'win32' ? 'dsh.cmd' : 'dsh')
    if (fs.existsSync(cand)) return cand
  }
  return ''
}

function portFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', () => resolve(false))
    server.once('listening', () => {
      server.close(() => resolve(true))
    })
    server.listen(port, '127.0.0.1')
  })
}

async function findFreePort(start, attempts = 40) {
  for (let i = 0; i < attempts; i++) {
    const p = start + i
    if (await portFree(p)) return p
  }
  throw new Error(`无空闲端口（自 ${start} 起试了 ${attempts} 个）`)
}

function waitHttpOk(port, probePath, timeoutMs = 90000, okCode = 200) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (shuttingDown) {
        reject(new Error('已退出'))
        return
      }
      const req = http.get(
        { host: '127.0.0.1', port, path: probePath, timeout: 2000 },
        (res) => {
          res.resume()
          if (res.statusCode === okCode) {
            resolve()
            return
          }
          retry()
        }
      )
      req.on('error', retry)
      req.on('timeout', () => {
        req.destroy()
        retry()
      })
    }
    const retry = () => {
      if (Date.now() > deadline) {
        reject(new Error(`等待 ${probePath} 超时（:${port}）`))
        return
      }
      setTimeout(tick, 300)
    }
    tick()
  })
}

function spawnLogged(label, cmd, args, env, cwd) {
  const child = spawn(cmd, args, {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const prefix = `[${label}]`
  child.stdout.on('data', (buf) => process.stdout.write(`${prefix} ${buf}`))
  child.stderr.on('data', (buf) => process.stderr.write(`${prefix} ${buf}`))
  child.on('exit', (code, signal) => {
    console.log(`${prefix} exit code=${code} signal=${signal}`)
  })
  children.push(child)
  return child
}

function killChildren() {
  for (const child of children.splice(0)) {
    try {
      if (!child.killed) child.kill('SIGTERM')
    } catch {
      /* ignore */
    }
  }
}

function pathExists(p) {
  try {
    fs.lstatSync(p)
    return true
  } catch {
    return false
  }
}

/** 把内嵌 dshmarket 拷进隔离 profile，设置里才会出现「插件市场」（web 端，不是官方 Desktop 插件中心）。 */
function installMarketIntoProfile(profile) {
  const srcNm = path.join(marketRuntimeRoot(), 'node_modules')
  const srcPkg = path.join(srcNm, MARKET_PKG, 'package.json')
  if (!fs.existsSync(srcPkg)) {
    console.warn('[desktop] 未内嵌 dshmarket，设置里不会有「插件市场」')
    return
  }
  const dstNm = path.join(profile, 'node_modules')
  fs.mkdirSync(dstNm, { recursive: true })
  let wantVer = ''
  try {
    wantVer = String(JSON.parse(fs.readFileSync(srcPkg, 'utf8')).version || '')
  } catch {
    wantVer = ''
  }
  const marker = path.join(profile, '.workbuddy-market')
  let have = ''
  try {
    have = fs.readFileSync(marker, 'utf8').trim()
  } catch {
    have = ''
  }
  const destClient = path.join(dstNm, MARKET_PKG, 'client', 'client.js')
  if (have === wantVer && wantVer && fs.existsSync(destClient)) return

  for (const name of fs.readdirSync(srcNm)) {
    if (name === '.bin' || name.startsWith('.')) continue
    const src = path.join(srcNm, name)
    let st
    try {
      st = fs.lstatSync(src)
    } catch {
      continue
    }
    if (name.startsWith('@') && st.isDirectory()) {
      const dstScope = path.join(dstNm, name)
      fs.mkdirSync(dstScope, { recursive: true })
      for (const pkg of fs.readdirSync(src)) {
        const s = path.join(src, pkg)
        const d = path.join(dstScope, pkg)
        if (pathExists(d)) continue
        fs.cpSync(s, d, { recursive: true })
      }
      continue
    }
    const dst = path.join(dstNm, name)
    const force = name === MARKET_PKG
    if (pathExists(dst)) {
      if (!force) continue
      fs.rmSync(dst, { recursive: true, force: true })
    }
    fs.cpSync(src, dst, { recursive: true })
  }
  fs.writeFileSync(marker, wantVer, 'utf8')
  console.log(`[desktop] 已安装内嵌插件市场 ${MARKET_PKG}@${wantVer}`)
}

/** 把产品 link 指到安装副本，并确保 profile 含 mes-bridge。 */
function ensureWorkBuddyWire(appRoot) {
  const home = dshHome()
  const linkDir = path.join(home, 'link')
  const linkRepo = path.join(linkDir, LINK_NAME)
  const profile = path.join(home, 'profiles', 'web')
  const profilePkg = path.join(profile, 'package.json')
  const patchPath = path.join(profile, 'cordis.patch.yml')

  fs.mkdirSync(linkDir, { recursive: true })
  try {
    fs.lstatSync(linkRepo)
    fs.rmSync(linkRepo, { force: true })
  } catch {
    /* missing ok */
  }
  fs.symlinkSync(appRoot, linkRepo)

  if (!fs.existsSync(profilePkg)) {
    return {
      ok: false,
      detail: `尚未初始化 DSH profile（缺 ${profilePkg}）`,
    }
  }

  const linkSpec = `link:../../link/${LINK_NAME}/apps/zr-workbuddy/plugins/mes-bridge`
  const pkg = JSON.parse(fs.readFileSync(profilePkg, 'utf8'))
  pkg.dependencies = pkg.dependencies || {}
  let changed = false
  if (pkg.dependencies[BRIDGE_PKG] !== linkSpec) {
    pkg.dependencies[BRIDGE_PKG] = linkSpec
    changed = true
  }
  pkg.dsh = pkg.dsh || {}
  pkg.dsh.profile = pkg.dsh.profile || {}
  const bundles = Array.isArray(pkg.dsh.profile.bundles) ? pkg.dsh.profile.bundles : []
  if (!pkg.dependencies[MARKET_PKG]) {
    pkg.dependencies[MARKET_PKG] = '1.34.0'
    changed = true
  }
  if (!bundles.includes(MARKET_PKG)) {
    pkg.dsh.profile.bundles = bundles.concat([MARKET_PKG])
    changed = true
  }
  if (changed) {
    fs.writeFileSync(profilePkg, JSON.stringify(pkg, null, 2) + '\n', 'utf8')
  }

  // dsh 首次生成的 cordis.patch.yml 正文是单独的 []；后面再拼 - insert 会变成非法 YAML。
  // name 必须是 npm 包名：client-modules 用 require.resolve(name/package.json) 发现
  // dsh.client，才会把 Bridge 的 client.js 打进设置侧栏（WorkBuddy 配置中心）。
  const bridgeBlock =
    `# --- ${BRIDGE_ID} (WorkBuddy bridge) ---\n` +
    `- insert:\n` +
    `    - id: ${BRIDGE_ID}\n` +
    `      name: '${BRIDGE_PKG}'\n`

  let patch = fs.existsSync(patchPath) ? fs.readFileSync(patchPath, 'utf8') : ''
  const contentLines = patch
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
  const withoutComments = contentLines.join('\n')
  const isEmptyArrayDoc = withoutComments === '[]' || withoutComments === ''
  const hasLeadingEmptyArray =
    contentLines.length > 1 && contentLines[0] === '[]'
  const hasBridgeRow = /(?:^|\n)\s*-?\s*id:\s*dsh-mes-bridge\b/.test(patch)
  const hasBridgePkgName = new RegExp(`name:\\s*'${BRIDGE_PKG.replace('/', '\\/')}'`).test(
    patch
  )
  const hasLegacyRel = patch.includes(BRIDGE_REL_LEGACY)
  const needsBridgeRewrite =
    isEmptyArrayDoc ||
    hasLeadingEmptyArray ||
    !hasBridgeRow ||
    !hasBridgePkgName ||
    hasLegacyRel

  if (needsBridgeRewrite) {
    // 保留文件头注释（去掉单独的 [] 与旧 bridge 块），再写入合法列表
    const header = patch
      .split('\n')
      .filter((line) => {
        const t = line.trim()
        if (t === '[]') return false
        if (/^-\s*insert:/.test(t)) return false
        if (/id:\s*dsh-mes-bridge/.test(t)) return false
        if (/name:\s*'@dsh-external\/dsh-mes-bridge'/.test(t)) return false
        if (/name:\s*'?\.\.\/\.\.\/link\/DSH-ZR-WorkBuddy\/apps\/zr-workbuddy\/plugins\/mes-bridge/.test(t))
          return false
        if (/^# --- dsh-mes-bridge/.test(t)) return false
        return true
      })
      .join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trimEnd()
    patch = `${header}\n\n${bridgeBlock}`
    fs.writeFileSync(patchPath, patch, 'utf8')
    changed = true
  }

  const bridgeLinked = path.join(profile, 'node_modules', ...BRIDGE_PKG.split('/'))
  const needInstall = changed || !fs.existsSync(bridgeLinked)
  if (needInstall) {
    try {
      const pnpm = findBundledPnpm()
      const hostNode = findHostNodeBinary() || process.execPath
      const env = applyDesktopToolchain({ ...process.env, CI: 'true', DSH_HOME: home })
      delete env.ELECTRON_RUN_AS_NODE
      if (pnpm) {
        execFileSync(hostNode, [pnpm, 'install'], {
          cwd: profile,
          env,
          stdio: 'inherit',
          timeout: 300000,
        })
      } else {
        execFileSync('pnpm', ['install'], {
          cwd: profile,
          env,
          stdio: 'inherit',
          timeout: 300000,
        })
      }
    } catch (e) {
      console.warn('[desktop] profile pnpm install:', e.message || e)
      // link 协议兜底：直接把 bridge 链进 profile node_modules
      try {
        const dst = bridgeLinked
        fs.mkdirSync(path.dirname(dst), { recursive: true })
        try {
          fs.lstatSync(dst)
          fs.rmSync(dst, { force: true, recursive: true })
        } catch {
          /* missing */
        }
        const src = path.join(appRoot, 'apps', 'zr-workbuddy', 'plugins', 'mes-bridge')
        fs.symlinkSync(src, dst)
      } catch (e2) {
        return { ok: false, detail: `Bridge 依赖安装失败: ${e2.message || e2}` }
      }
    }
  }

  // 在 pnpm 之后再拷：隔离 profile 通常没有 pnpm，靠内嵌包出现「插件市场」。
  installMarketIntoProfile(profile)

  // 公司插件市场：仅写 @zhongruan 私有源到本 profile（不改其它依赖）
  try {
    const market = loadCompanyDshMarketEnv(appRoot)
    ensureCompanyMarketNpmrc(profile, market.ZHONGRUAN_NPM_REGISTRY)
  } catch (e) {
    console.warn('[desktop] company market npmrc:', e && e.message ? e.message : e)
  }

  return { ok: true, detail: `link → ${appRoot}` }
}

async function startEngine(engineDir, port) {
  const launcher = findEngineLauncher()
  if (!launcher && !fs.existsSync(path.join(runtimeRoot(), 'python'))) {
    throw new Error('缺少内嵌引擎运行时，请先 scripts/package-desktop.sh')
  }
  writeEngineRuntime(engineDir, port)
  const pyHome = path.join(runtimeRoot(), 'python')
  const env = applyDesktopToolchain({
    ...process.env,
    PYTHONUNBUFFERED: '1',
    WORKBUDDY_DESKTOP: '1',
    WORKBUDDY_ENGINE_DIR: engineDir,
    WORKBUDDY_ENGINE_HOST: '127.0.0.1',
    WORKBUDDY_ENGINE_PORT: String(port),
    APP_ENGINE_HOST: '127.0.0.1',
    APP_ENGINE_PORT: String(port),
    MPLBACKEND: 'Agg',
    VECLIB_MAXIMUM_THREADS: '1',
    OPENBLAS_NUM_THREADS: '1',
  })
  env.PATH = `${path.join(pyHome, 'bin')}${path.delimiter}${env.PATH || ''}`
  const py = path.join(
    pyHome,
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3'
  )
  const pyAlt = path.join(pyHome, 'bin', 'python')
  const runEngine = path.join(runtimeRoot(), 'app', 'desktop', 'py', 'run_engine.py')
  let pyExec = ''
  try {
    if (fs.existsSync(py) && fs.statSync(py).isFile()) pyExec = py
    else if (fs.existsSync(pyAlt)) {
      const st = fs.lstatSync(pyAlt)
      if (st.isSymbolicLink()) {
        const target = fs.readlinkSync(pyAlt)
        if (!path.isAbsolute(target) || fs.existsSync(pyAlt)) pyExec = pyAlt
      } else if (st.isFile()) pyExec = pyAlt
    }
  } catch {
    pyExec = ''
  }
  // 断链时 existsSync 可能仍为 true，再 resolve 一次
  if (pyExec) {
    try {
      fs.realpathSync(pyExec)
    } catch {
      pyExec = ''
    }
  }
  if (pyExec && fs.existsSync(runEngine)) {
    spawnLogged('engine', pyExec, [runEngine], env, engineDir)
  } else if (launcher) {
    spawnLogged('engine', launcher, [], env, path.dirname(launcher))
  } else {
    throw new Error(
      '无法启动引擎：内嵌 Python 断链或缺失。请重新执行 scripts/package-desktop.sh（勿用坏掉的 runtime/python）。'
    )
  }
  await waitHttpOk(port, '/api/runtime', 120000)
  return port
}

async function startBundledHost(enginePort, appRoot) {
  const cli = findBundledCliEntry()
  const port = await findFreePort(DSH_PORT_START)
  const hostNode = findHostNodeBinary()
  const market = loadCompanyDshMarketEnv(appRoot)
  const env = applyDesktopToolchain({
    ...process.env,
    DSH_HOME: dshHome(),
    APP_ENGINE_HOST: '127.0.0.1',
    APP_ENGINE_PORT: String(enginePort),
    DSH_DESKTOP: '1',
    WORKBUDDY_DESKTOP: '1',
    // 仅当配置/环境提供了目录 URL 时注入（公司插件市场）
    ...(market.DSHM_REGISTRY_URL
      ? { DSHM_REGISTRY_URL: market.DSHM_REGISTRY_URL }
      : {}),
    ...(market.ZHONGRUAN_NPM_REGISTRY
      ? { ZHONGRUAN_NPM_REGISTRY: market.ZHONGRUAN_NPM_REGISTRY }
      : {}),
  })
  if (market.DSHM_REGISTRY_URL) {
    console.log('[desktop] 公司插件市场目录:', market.DSHM_REGISTRY_URL)
  }
  // 切勿把 ELECTRON_RUN_AS_NODE 留给宿主：会误用 Electron 的 Node 20
  delete env.ELECTRON_RUN_AS_NODE

  const hostLog = []
  const note = (buf) => {
    const s = buf.toString()
    process.stderr.write(`[host] ${s}`)
    hostLog.push(s)
    if (hostLog.length > 80) hostLog.shift()
  }

  const waitHost = async (child, detail) => {
    child.stdout.on('data', note)
    child.stderr.on('data', note)
    try {
      await waitHttpOk(port, '/', 120000)
      // `/` 先 200 时插件路由可能尚未挂上；过早开窗会 Failed to load plugins
      await waitHttpOk(
        port,
        '/plugins/@deepseek-ai/dsh-api-gateway/client.js',
        60000
      )
      await waitHttpOk(port, `/plugins/${BRIDGE_PKG}/client.js`, 30000)
      try {
        await waitHttpOk(port, `/plugins/${MARKET_PKG}/client.js`, 20000)
      } catch (e) {
        console.warn(
          '[desktop] 插件市场 client 未挂上（设置里可能没有「插件市场」）:',
          e && e.message ? e.message : e
        )
      }
      return { port, detail, log: hostLog.join('') }
    } catch (e) {
      try {
        child.kill('SIGTERM')
      } catch {
        /* ignore */
      }
      const tail = hostLog.join('').slice(-1200)
      const msg = e && e.message ? e.message : String(e)
      return {
        port: 0,
        detail: `${msg}\n--- host 日志 ---\n${tail || '(无输出)'}`,
      }
    }
  }

  if (cli && hostNode) {
    console.log('[desktop] host node:', hostNode, 'major=', nodeMajorOf(hostNode))
    const child = spawn(
      hostNode,
      ['--expose-internals', cli, 'web', '--no-open', '--host', '127.0.0.1', '--port', String(port)],
      { cwd: app.getPath('home'), env, stdio: ['ignore', 'pipe', 'pipe'] }
    )
    children.push(child)
    return waitHost(child, `内嵌 Host（dsh web @ Node ${nodeMajorOf(hostNode)}）`)
  }

  if (cli && !hostNode) {
    return {
      port: 0,
      detail:
        '安装包缺少 Node≥22 运行时（DSH 宿主不能跑在 Electron 内嵌 Node 20 上）。\n' +
        '请重装 0.2.8+ 一体包，或设置 WORKBUDDY_HOST_NODE 指向本机 node（≥22）。',
    }
  }

  const dsh = findPathDshBin()
  if (!dsh) {
    return { port: 0, detail: '安装包缺少内嵌 Host，且 PATH 无 dsh' }
  }
  const child = spawn(
    dsh,
    ['web', '--no-open', '--host', '127.0.0.1', '--port', String(port)],
    { cwd: app.getPath('home'), env, stdio: ['ignore', 'pipe', 'pipe'] }
  )
  children.push(child)
  return waitHost(child, '本机 dsh')
}

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: 'ZR WorkBuddy',
  })
  mainWindow.loadURL(url)
  mainWindow.on('closed', () => {
    mainWindow = null
  })
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    try {
      const u = new URL(target)
      if (u.protocol === 'http:' || u.protocol === 'https:') {
        shell.openExternal(target)
      }
    } catch {
      /* ignore */
    }
    return { action: 'deny' }
  })
}

/** 首次启动：用内嵌 dsh 生成干净 web profile（仅 base + web-app）。 */
async function bootstrapProfileIfNeeded() {
  const profilePkg = path.join(dshHome(), 'profiles', 'web', 'package.json')
  if (fs.existsSync(profilePkg)) return { bootstrapped: false }

  const cli = findBundledCliEntry()
  const hostNode = findHostNodeBinary()
  if (!cli) throw new Error('缺少内嵌 Host，无法初始化 profile')
  if (!hostNode) {
    throw new Error(
      '缺少 Node≥22，无法初始化 DSH profile（不要用 Electron Node 20）。请使用 0.2.8+ 一体包或设置 WORKBUDDY_HOST_NODE。'
    )
  }

  const port = await findFreePort(DSH_PORT_START + 200)
  const env = applyDesktopToolchain({
    ...process.env,
    DSH_HOME: dshHome(),
    DSH_DESKTOP: '1',
  })
  delete env.ELECTRON_RUN_AS_NODE
  const child = spawn(
    hostNode,
    ['--expose-internals', cli, 'web', '--no-open', '--host', '127.0.0.1', '--port', String(port)],
    { cwd: app.getPath('home'), env, stdio: ['ignore', 'pipe', 'pipe'] }
  )
  children.push(child)
  try {
    await waitHttpOk(port, '/', 120000)
  } finally {
    try {
      child.kill('SIGTERM')
    } catch {
      /* ignore */
    }
    const idx = children.indexOf(child)
    if (idx >= 0) children.splice(idx, 1)
    await new Promise((r) => setTimeout(r, 800))
  }
  if (!fs.existsSync(profilePkg)) {
    throw new Error(`初始化 DSH profile 失败：仍缺少 ${profilePkg}`)
  }
  return { bootstrapped: true }
}

async function boot() {
  applyDesktopDshHome()
  const { appRoot, engineDir } = ensureWritableAppCopy()
  materializeBridgeDeps(appRoot)
  const enginePort = await findFreePort(ENGINE_PORT_START)
  await startEngine(engineDir, enginePort)

  await bootstrapProfileIfNeeded()
  const wire = ensureWorkBuddyWire(appRoot)
  console.log('[desktop] DSH_HOME=', dshHome(), 'wire:', wire.detail)

  let host
  try {
    host = await startBundledHost(enginePort, appRoot)
  } catch (e) {
    console.warn('[desktop] Host 启动失败:', e && e.message ? e.message : e)
    host = { port: 0, detail: String(e && e.message ? e.message : e) }
  }

  const url =
    host.port > 0
      ? `http://127.0.0.1:${host.port}/`
      : `http://127.0.0.1:${enginePort}/`
  createWindow(url)

  if (host.port <= 0) {
    dialog.showMessageBox({
      type: 'warning',
      title: 'ZR WorkBuddy',
      message: '聊天壳未拉起，已打开引擎配置页',
      detail:
        `${host.detail}\n\n` +
        `DSH_HOME: ${dshHome()}\n` +
        `引擎: http://127.0.0.1:${enginePort}/\n接线: ${wire.detail}`,
    })
  } else if (!wire.ok) {
    dialog.showMessageBox({
      type: 'info',
      title: 'ZR WorkBuddy',
      message: '聊天壳已打开',
      detail:
        `${wire.detail}\n\n` +
        '请先在「设置 → 模型」填写 API Key，然后完全退出并重新打开本应用以挂载 WorkBuddy 工具。',
    })
  }
}

app.whenReady().then(() => {
  boot().catch((err) => {
    console.error(err)
    dialog.showErrorBox('ZR WorkBuddy 启动失败', String(err && err.message ? err.message : err))
    app.quit()
  })
})

app.on('window-all-closed', () => {
  shuttingDown = true
  if (persistedEngineDir) stashEngineUserState(persistedEngineDir)
  killChildren()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  shuttingDown = true
  if (persistedEngineDir) stashEngineUserState(persistedEngineDir)
  killChildren()
})

app.on('activate', () => {
  if (mainWindow === null && app.isReady()) {
    boot().catch((err) => console.error(err))
  }
})

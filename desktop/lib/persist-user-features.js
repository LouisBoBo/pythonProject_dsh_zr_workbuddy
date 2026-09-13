/**
 * 桌面升级时保住用户后装的 WorkBuddy 功能（features/<id>）。
 * 出厂打进安装包的功能随新包走；只有「当前运行副本有、新包没有」的目录才进 persist。
 * 拷贝不跟随符号链接，且必须落在 features / persist 根目录内。
 */
'use strict'

const fs = require('fs')
const path = require('path')

const FEATURE_ID_RE = /^[a-z][a-z0-9_-]*$/
const FEATURES_REL = path.join('apps', 'zr-workbuddy', 'features')
const PERSIST_REL = 'user-features'
/** 与引擎 feature_install 上限对齐，防止 persist 被撑爆或拷入异常树 */
const MAX_FEATURE_BYTES = 5 * 1024 * 1024
const MAX_FEATURE_FILES = 200

function isSafeFeatureId(id) {
  return FEATURE_ID_RE.test(String(id || ''))
}

function featuresDir(appRoot) {
  return path.join(appRoot, FEATURES_REL)
}

function persistFeaturesDir(persistDir) {
  return path.join(persistDir, PERSIST_REL)
}

function containedPath(root, candidate) {
  if (!root || !candidate) return null
  const rootAbs = path.resolve(root)
  const candAbs = path.resolve(candidate)
  const prefix = rootAbs.endsWith(path.sep) ? rootAbs : rootAbs + path.sep
  if (candAbs !== rootAbs && !candAbs.startsWith(prefix)) return null
  return candAbs
}

function lstatSafe(p) {
  try {
    return fs.lstatSync(p)
  } catch {
    return null
  }
}

function isRealDir(p) {
  const st = lstatSafe(p)
  return Boolean(st && st.isDirectory() && !st.isSymbolicLink())
}

function isRealFile(p) {
  const st = lstatSafe(p)
  return Boolean(st && st.isFile() && !st.isSymbolicLink())
}

function measureTreeOk(root, limits) {
  const maxBytes = (limits && limits.maxBytes) || MAX_FEATURE_BYTES
  const maxFiles = (limits && limits.maxFiles) || MAX_FEATURE_FILES
  let bytes = 0
  let files = 0
  function walk(p) {
    const st = lstatSafe(p)
    if (!st) return false
    if (st.isSymbolicLink()) return true
    if (st.isFile()) {
      files += 1
      bytes += st.size
      return files <= maxFiles && bytes <= maxBytes
    }
    if (!st.isDirectory()) return true
    let names
    try {
      names = fs.readdirSync(p)
    } catch {
      return false
    }
    for (const name of names) {
      if (name === '.' || name === '..') continue
      if (!walk(path.join(p, name))) return false
    }
    return true
  }
  return walk(root)
}

function isRealFeatureDir(parent, id) {
  if (!isSafeFeatureId(id)) return false
  const dir = containedPath(parent, path.join(parent, id))
  if (!dir || !isRealDir(dir)) return false
  return isRealFile(path.join(dir, 'index.js'))
}

function listFeatureIds(dir) {
  if (!dir || !isRealDir(dir)) return []
  const out = []
  let ents
  try {
    ents = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return []
  }
  for (const ent of ents) {
    if (ent.isSymbolicLink()) continue
    if (!ent.isDirectory()) continue
    if (isRealFeatureDir(dir, ent.name)) out.push(ent.name)
  }
  return out
}

function copyFeatureDir(src, dest, srcRoot, destRoot, limits) {
  const srcAbs = containedPath(srcRoot, src)
  const destAbs = containedPath(destRoot, dest)
  if (!srcAbs || !destAbs) return false
  if (!isRealDir(srcAbs) || !isRealFile(path.join(srcAbs, 'index.js'))) return false
  if (!measureTreeOk(srcAbs, limits)) return false
  fs.mkdirSync(path.dirname(destAbs), { recursive: true })
  const destSt = lstatSafe(destAbs)
  if (destSt) {
    if (destSt.isSymbolicLink()) fs.unlinkSync(destAbs)
    else fs.rmSync(destAbs, { recursive: true, force: true })
  }
  fs.cpSync(srcAbs, destAbs, {
    recursive: true,
    filter(p) {
      const st = lstatSafe(p)
      return Boolean(st && !st.isSymbolicLink())
    },
  })
  if (!isRealFile(path.join(destAbs, 'index.js'))) {
    fs.rmSync(destAbs, { recursive: true, force: true })
    return false
  }
  return true
}

function stashUserFeatures(opts) {
  const liveAppRoot = opts.liveAppRoot
  const bundleAppRoot = opts.bundleAppRoot
  const persistDir = opts.persistDir
  if (!liveAppRoot || !persistDir) return []
  const limits = {
    maxBytes: Number(opts.maxBytes) > 0 ? Number(opts.maxBytes) : MAX_FEATURE_BYTES,
    maxFiles: Number(opts.maxFiles) > 0 ? Number(opts.maxFiles) : MAX_FEATURE_FILES,
  }
  const liveRoot = featuresDir(liveAppRoot)
  const liveIds = listFeatureIds(liveRoot)
  const bundled = new Set(listFeatureIds(featuresDir(bundleAppRoot)))
  const destRoot = persistFeaturesDir(persistDir)
  const destRootSt = lstatSafe(destRoot)
  if (destRootSt && destRootSt.isSymbolicLink()) {
    console.error('[desktop] persist/user-features 不能是符号链接')
    return []
  }
  fs.mkdirSync(destRoot, { recursive: true })
  const kept = []
  for (const id of liveIds) {
    if (bundled.has(id)) continue
    try {
      const ok = copyFeatureDir(
        path.join(liveRoot, id),
        path.join(destRoot, id),
        liveRoot,
        destRoot,
        limits,
      )
      if (ok) kept.push(id)
    } catch (err) {
      console.error('[desktop] stash user feature 失败', id, err && err.message ? err.message : err)
    }
  }
  if (isRealDir(destRoot)) {
    for (const name of fs.readdirSync(destRoot)) {
      if (!isSafeFeatureId(name)) continue
      if (kept.includes(name)) continue
      const extra = containedPath(destRoot, path.join(destRoot, name))
      if (!extra) continue
      try {
        const st = lstatSafe(extra)
        if (st && st.isSymbolicLink()) fs.unlinkSync(extra)
        else fs.rmSync(extra, { recursive: true, force: true })
      } catch (err) {
        console.error('[desktop] 清理 persist feature 失败', name, err && err.message ? err.message : err)
      }
    }
  }
  return kept
}

function restoreUserFeatures(opts) {
  const liveAppRoot = opts.liveAppRoot
  const bundleAppRoot = opts.bundleAppRoot
  const persistDir = opts.persistDir
  if (!liveAppRoot || !persistDir) return []
  const srcRoot = persistFeaturesDir(persistDir)
  if (!isRealDir(srcRoot)) return []
  const limits = {
    maxBytes: Number(opts.maxBytes) > 0 ? Number(opts.maxBytes) : MAX_FEATURE_BYTES,
    maxFiles: Number(opts.maxFiles) > 0 ? Number(opts.maxFiles) : MAX_FEATURE_FILES,
  }
  const bundled = new Set(listFeatureIds(featuresDir(bundleAppRoot)))
  const liveFeat = featuresDir(liveAppRoot)
  fs.mkdirSync(liveFeat, { recursive: true })
  const restored = []
  let names
  try {
    names = fs.readdirSync(srcRoot)
  } catch {
    return []
  }
  for (const name of names) {
    if (!isSafeFeatureId(name)) continue
    const src = containedPath(srcRoot, path.join(srcRoot, name))
    if (!src) continue
    try {
      if (bundled.has(name)) {
        const st = lstatSafe(src)
        if (st && st.isSymbolicLink()) fs.unlinkSync(src)
        else fs.rmSync(src, { recursive: true, force: true })
        continue
      }
      if (!isRealFeatureDir(srcRoot, name)) continue
      const dest = containedPath(liveFeat, path.join(liveFeat, name))
      if (!dest) continue
      if (isRealFeatureDir(liveFeat, name)) continue
      const ok = copyFeatureDir(src, dest, srcRoot, liveFeat, limits)
      if (ok) restored.push(name)
    } catch (err) {
      console.error('[desktop] restore user feature 失败', name, err && err.message ? err.message : err)
    }
  }
  return restored
}

module.exports = {
  FEATURE_ID_RE,
  FEATURES_REL,
  PERSIST_REL,
  MAX_FEATURE_BYTES,
  MAX_FEATURE_FILES,
  isSafeFeatureId,
  featuresDir,
  persistFeaturesDir,
  listFeatureIds,
  stashUserFeatures,
  restoreUserFeatures,
}

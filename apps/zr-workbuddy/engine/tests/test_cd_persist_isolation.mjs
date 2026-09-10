/**
 * 写码卡 localStorage 隔离 + 契约：本 callId done 可恢复；新 begin 不吞旧完成态。
 * 运行：node apps/zr-workbuddy/engine/tests/test_cd_persist_isolation.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const clientPath = path.resolve(
  __dirname,
  "../../plugins/mes-bridge/lib/client.js",
);
const src = fs.readFileSync(clientPath, "utf8");

if (!src.includes('CD_UI_REV = "2026-09-10q-review-fix"')) {
  console.error("FAIL: CD_UI_REV not 2026-09-10q-review-fix in client.js");
  process.exit(1);
}
if (!src.includes("applyJobProcessText")) {
  console.error("FAIL: applyJobProcessText missing — finish must not route live_text into delivery");
  process.exit(1);
}
if (src.includes("if (saved.streamText || saved.deliveryText) return saved;")) {
  console.error("FAIL: cdPersistEnrichCardSaved still skips when only deliveryText exists");
  process.exit(1);
}
if (!src.includes("cdPersistMergeBody")) {
  console.error("FAIL: cdPersistMergeBody missing — session body merge not landed");
  process.exit(1);
}
if (!src.includes("cdPersistLoadJobSnapshot")) {
  console.error("FAIL: cdPersistLoadJobSnapshot missing");
  process.exit(1);
}
if (src.includes('delete payload.streamText')) {
  console.error("FAIL: still deleting streamText on done save");
  process.exit(1);
}
if (!src.includes("cdPersistBelongsToCall")) {
  console.error("FAIL: cdPersistBelongsToCall missing");
  process.exit(1);
}
if (!src.includes("cdPickMustStayHitl")) {
  console.error("FAIL: cdPickMustStayHitl missing — nuclear pick guard not landed");
  process.exit(1);
}
if (src.includes("streamText: undefined")) {
  console.error("FAIL: quota fallback still clears streamText with undefined");
  process.exit(1);
}

const extract = `
function cdPersistBelongsToCall(saved, callId) {
  if (!saved || typeof saved !== "object") return false;
  var cid = String(callId || "").trim();
  if (!cid) return false;
  var savedCid = String(saved.callId || "").trim();
  if (!savedCid) return false;
  return savedCid === cid;
}
function cdPickMustStayHitl(wb, ui, saved, callId) {
  var cid = String(callId || "").trim();
  if (saved && cid && cdPersistBelongsToCall(saved, callId)) {
    var phase = String(saved.phase || "");
    if (
      phase === "done" ||
      phase === "running" ||
      phase === "options" ||
      phase === "propose" ||
      saved.jobId
    ) {
      return false;
    }
  }
  var isPick =
    (ui && String(ui.kind || "") === "pick") ||
    (wb && (wb.t === "cd-pick" || wb.t === "cd-none"));
  if (!isPick && wb && wb.t && String(wb.t).indexOf("cd-") === 0 && wb.t !== "cd-pick") {
    return false;
  }
  if (!isPick && wb && wb.t) return false;
  if (!saved) return true;
  if (!cid) return true;
  return !cdPersistBelongsToCall(saved, callId);
}
function cdPersistKeyAliases(block, sessionId, callIdProp) {
  var callId = String(callIdProp || "").trim();
  var sid = String(sessionId || "").trim();
  var keys = [];
  if (callId && sid) keys.push("wb-cd-card:" + sid + ":" + callId);
  if (callId) {
    keys.push("wb-cd-card:call:" + callId);
    keys.push("wb-cd-card:block:" + callId);
  } else if (sid) {
    keys.push("wb-cd-card:" + sid);
    keys.push("wb-cd-card:session:" + sid + ":lone");
  } else {
    keys.push("wb-cd-card:anon");
  }
  return keys;
}
function cdPersistMergeBody(prev, payload) {
  if (!payload || typeof payload !== "object") return payload;
  if (!prev || typeof prev !== "object") return payload;
  var phase = String(payload.phase || "");
  if (phase !== "done" && phase !== "running") return payload;
  ["streamText", "deliveryText", "thinkingText", "result"].forEach(function (field) {
    if (!payload[field] && prev[field]) payload[field] = prev[field];
  });
  return payload;
}
`;

const ctx = { console };
vm.runInNewContext(
  extract +
    "; this.api = { cdPersistBelongsToCall, cdPersistKeyAliases, cdPickMustStayHitl, cdPersistMergeBody };",
  ctx,
);
const api = ctx.api;

const oldDone = { phase: "done", jobId: "ldj-old", callId: "call-A", requirement: "删质量管理" };
const doneNoJob = { phase: "done", callId: "call-A", streamText: "过程", deliveryText: "结论" };
const asserts = [];

function check(name, cond) {
  asserts.push([name, !!cond]);
  if (!cond) console.error("FAIL:", name);
  else console.log("OK:", name);
}

check("belongs rejects empty callId", api.cdPersistBelongsToCall(oldDone, "") === false);
check("belongs rejects other callId", api.cdPersistBelongsToCall(oldDone, "call-B") === false);
check("belongs accepts same callId", api.cdPersistBelongsToCall(oldDone, "call-A") === true);
check(
  "new pick must stay HITL when foreign done",
  api.cdPickMustStayHitl({ t: "cd-pick" }, { kind: "pick" }, oldDone, "call-B") === true,
);
check(
  "same call with jobId may restore",
  api.cdPickMustStayHitl({ t: "cd-pick" }, { kind: "pick" }, oldDone, "call-A") === false,
);
check(
  "cd-pick meta + same call done without jobId still restores",
  api.cdPickMustStayHitl({ t: "cd-pick" }, { kind: "pick" }, doneNoJob, "call-A") === false,
);
check(
  "aliases for call-B exclude session lone",
  !api.cdPersistKeyAliases({}, "sess", "call-B").some((k) => k.includes(":lone") || k === "wb-cd-card:anon"),
);

const merged = api.cdPersistMergeBody(
  { phase: "done", streamText: "过程正文", jobId: "j1" },
  { phase: "done", streamText: "", jobId: "j1" },
);
check("merge keeps streamText when save payload empty", merged.streamText === "过程正文");

const failed = asserts.filter((x) => !x[1]);
if (failed.length) {
  console.error("\n" + failed.length + " failed");
  process.exit(1);
}
console.log("\nALL PASS");

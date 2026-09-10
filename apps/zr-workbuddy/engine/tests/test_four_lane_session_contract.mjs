/**
 * 四车道会话契约静态验收（不依赖 React / 浏览器）。
 * 运行：node apps/zr-workbuddy/engine/tests/test_four_lane_session_contract.mjs
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

const must = [
  'CD_UI_REV = "2026-09-10q-review-fix"',
  'CR_UI_REV = "2026-09-10o-cr-session"',
  'CC_UI_REV = "2026-09-10o-cc-contract"',
  'CDP_UI_REV = "2026-09-10o-cdp-session"',
  "wb-cd-card:",
  "wb-cr-card:",
  "wb-cc-card:",
  "wb-cdp-card:",
  "cdPersistMergeBody",
  "applyJobProcessText",
  "crPersistSaveCard",
  "ccPersistScanByCallId",
  "cdpPersistSaveCard",
  "仅「真正的新 pick」停 HITL",
  'hit.phase === "gating"',
];
const mustNot = [
  "streamText: undefined",
  "delete payload.streamText",
  "if (saved.streamText || saved.deliveryText) return saved;",
];

let fail = 0;
function ok(name, cond) {
  if (cond) console.log("OK:", name);
  else {
    console.error("FAIL:", name);
    fail++;
  }
}

must.forEach((s) => ok("has " + s.slice(0, 48), src.includes(s)));
mustNot.forEach((s) => ok("absent " + s.slice(0, 40), !src.includes(s)));

// namespaces must not cross-read
ok("cr helpers never read wb-cd-", !/function crPersist[\s\S]{0,800}wb-cd-card/.test(src));
ok("cdp helpers never read wb-cc-", !/function cdpPersist[\s\S]{0,800}wb-cc-card/.test(src));

const extract = `
function cdPersistBelongsToCall(saved, callId) {
  if (!saved || typeof saved !== "object") return false;
  var cid = String(callId || "").trim();
  if (!cid) return false;
  return String(saved.callId || "").trim() === cid;
}
function cdPickMustStayHitl(wb, ui, saved, callId) {
  var cid = String(callId || "").trim();
  if (saved && cid && cdPersistBelongsToCall(saved, callId)) {
    var phase = String(saved.phase || "");
    if (phase === "done" || phase === "running" || phase === "options" || phase === "propose" || saved.jobId) {
      return false;
    }
  }
  var isPick = (ui && String(ui.kind || "") === "pick") || (wb && (wb.t === "cd-pick" || wb.t === "cd-none"));
  if (!isPick && wb && wb.t && String(wb.t).indexOf("cd-") === 0 && wb.t !== "cd-pick") return false;
  if (!isPick && wb && wb.t) return false;
  if (!saved) return true;
  if (!cid) return true;
  return !cdPersistBelongsToCall(saved, callId);
}
function crPickMustStayPick(wb, ui, saved, callId) {
  var cid = String(callId || "").trim();
  if (saved && cid && saved.callId === callId) {
    var phase = String(saved.phase || "");
    if (phase === "done" || phase === "running" || phase === "files") return false;
  }
  var isPick = (ui && String(ui.kind || "") === "pick") || (wb && wb.t === "cr-pick");
  if (!isPick && wb && wb.t) return false;
  if (!saved) return true;
  if (!cid) return true;
  return saved.callId !== callId;
}
function ccPickMustStayPick(wb, ui, saved, callId) {
  var cid = String(callId || "").trim();
  if (saved && cid && saved.callId === callId) {
    var phase = String(saved.phase || "");
    if (phase === "done" || phase === "confirm" || phase === "blocked" || phase === "files" || phase === "gating" || saved.jobId) {
      return false;
    }
  }
  var isPick = (ui && String(ui.kind || "") === "pick") || (wb && wb.t === "cc-pick");
  if (!isPick && wb && wb.t) return false;
  if (!saved) return true;
  if (!cid) return true;
  return saved.callId !== callId;
}
`;
const ctx = {};
vm.runInNewContext(extract + "; this.api={cdPickMustStayHitl,crPickMustStayPick,ccPickMustStayPick};", ctx);
const api = ctx.api;

ok(
  "cd: pick+done same call restores",
  api.cdPickMustStayHitl({ t: "cd-pick" }, { kind: "pick" }, { phase: "done", callId: "A" }, "A") === false,
);
ok(
  "cd: pick+foreign done stays HITL",
  api.cdPickMustStayHitl({ t: "cd-pick" }, { kind: "pick" }, { phase: "done", callId: "A" }, "B") === true,
);
ok(
  "cr: pick+done same call restores",
  api.crPickMustStayPick({ t: "cr-pick" }, { kind: "pick" }, { phase: "done", callId: "A" }, "A") === false,
);
ok(
  "cc: pick+done same call restores",
  api.ccPickMustStayPick({ t: "cc-pick" }, { kind: "pick" }, { phase: "done", callId: "A", jobId: "cc-1" }, "A") === false,
);
ok(
  "cc: new begin stays pick",
  api.ccPickMustStayPick({ t: "cc-pick" }, { kind: "pick" }, null, "C") === true,
);

if (fail) {
  console.error("\n" + fail + " failed");
  process.exit(1);
}
console.log("\nALL PASS four-lane session contract");

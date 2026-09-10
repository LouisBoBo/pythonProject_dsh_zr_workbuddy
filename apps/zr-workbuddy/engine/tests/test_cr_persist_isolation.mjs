/**
 * 审码卡 localStorage：刷新恢复 done/files；新 begin 不吞旧报告。
 * 运行：node apps/zr-workbuddy/engine/tests/test_cr_persist_isolation.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(
  path.resolve(__dirname, "../../plugins/mes-bridge/lib/client.js"),
  "utf8",
);

if (!src.includes('CR_UI_REV = "2026-09-10o-cr-session"')) {
  console.error("FAIL: CR_UI_REV missing");
  process.exit(1);
}
if (!src.includes("wb-cr-card:")) {
  console.error("FAIL: wb-cr-card prefix missing");
  process.exit(1);
}
if (!src.includes("crPersistSaveCard")) {
  console.error("FAIL: crPersistSaveCard missing");
  process.exit(1);
}

const extract = `
function crPersistBelongsToCall(saved, callId) {
  if (!saved || typeof saved !== "object") return false;
  var cid = String(callId || "").trim();
  if (!cid) return false;
  return String(saved.callId || "").trim() === cid;
}
function crPickMustStayPick(wb, ui, saved, callId) {
  var cid = String(callId || "").trim();
  if (saved && cid && crPersistBelongsToCall(saved, callId)) {
    var phase = String(saved.phase || "");
    if (phase === "done" || phase === "running" || phase === "files") return false;
  }
  var isPick = (ui && String(ui.kind || "") === "pick") || (wb && wb.t === "cr-pick");
  if (!isPick && wb && wb.t && String(wb.t).indexOf("cr-") === 0 && wb.t !== "cr-pick") return false;
  if (!isPick && wb && wb.t) return false;
  if (!saved) return true;
  if (!cid) return true;
  return !crPersistBelongsToCall(saved, callId);
}
`;
const ctx = {};
vm.runInNewContext(extract + "; this.api={crPickMustStayPick};", ctx);
const done = { phase: "done", callId: "call-A", report: "报告" };
function check(n, c) {
  if (!c) {
    console.error("FAIL:", n);
    process.exit(1);
  }
  console.log("OK:", n);
}
check(
  "cr-pick + same call done restores",
  ctx.api.crPickMustStayPick({ t: "cr-pick" }, { kind: "pick" }, done, "call-A") === false,
);
check(
  "foreign done stays pick",
  ctx.api.crPickMustStayPick({ t: "cr-pick" }, { kind: "pick" }, done, "call-B") === true,
);
console.log("\nALL PASS");

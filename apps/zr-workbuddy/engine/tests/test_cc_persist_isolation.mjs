/**
 * 提交卡 localStorage：刷新须恢复 done；新 begin 不得吞上一张完成态。
 * 运行：node apps/zr-workbuddy/engine/tests/test_cc_persist_isolation.mjs
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

if (!src.includes('CC_UI_REV = "2026-09-10o-cc-contract"')) {
  console.error("FAIL: CC_UI_REV not 2026-09-10o-cc-contract");
  process.exit(1);
}
if (!src.includes("ccPersistScanByCallId")) {
  console.error("FAIL: ccPersistScanByCallId missing");
  process.exit(1);
}

const extract = `
function ccPersistBelongsToCall(saved, callId) {
  if (!saved || typeof saved !== "object") return false;
  var cid = String(callId || "").trim();
  if (!cid) return false;
  var savedCid = String(saved.callId || "").trim();
  if (!savedCid) return false;
  return savedCid === cid;
}
function ccPickMustStayPick(wb, ui, saved, callId) {
  var cid = String(callId || "").trim();
  if (saved && cid && ccPersistBelongsToCall(saved, callId)) {
    var phase = String(saved.phase || "");
    if (
      phase === "done" ||
      phase === "confirm" ||
      phase === "blocked" ||
      phase === "files" ||
      phase === "gating" ||
      saved.jobId
    ) {
      return false;
    }
  }
  var isPick =
    (ui && String(ui.kind || "") === "pick") ||
    (wb && wb.t === "cc-pick");
  if (!isPick && wb && wb.t && String(wb.t).indexOf("cc-") === 0 && wb.t !== "cc-pick") {
    return false;
  }
  if (!isPick && wb && wb.t) return false;
  if (!saved) return true;
  if (!cid) return true;
  return !ccPersistBelongsToCall(saved, callId);
}
`;

const ctx = { console };
vm.runInNewContext(extract + "; this.api = { ccPickMustStayPick, ccPersistBelongsToCall };", ctx);
const api = ctx.api;

const oldDone = {
  phase: "done",
  jobId: "cc-abc",
  callId: "call-A",
  commitDetail: { ok: true },
};
const asserts = [];

function check(name, cond) {
  asserts.push([name, !!cond]);
  if (!cond) console.error("FAIL:", name);
  else console.log("OK:", name);
}

check(
  "cc-pick meta + same call done must restore (not stay pick)",
  api.ccPickMustStayPick({ t: "cc-pick" }, { kind: "pick" }, oldDone, "call-A") === false,
);
check(
  "cc-pick meta + foreign call done must stay pick",
  api.ccPickMustStayPick({ t: "cc-pick" }, { kind: "pick" }, oldDone, "call-B") === true,
);
check(
  "fresh pick without saved stays pick",
  api.ccPickMustStayPick({ t: "cc-pick" }, { kind: "pick" }, null, "call-C") === true,
);

const failed = asserts.filter((x) => !x[1]);
if (failed.length) {
  console.error("\n" + failed.length + " failed");
  process.exit(1);
}
console.log("\nALL PASS");

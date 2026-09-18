import { pendingAnnouncement, buildMessage, Cfg } from "../_shared/momentum.ts";
const cfg: Cfg = { key:"t", label:"T", stateId:99, portfolio:"x", cur:"$", page:"p" };
const picks = [{ ticker: "AAA", name: "A" }];
const cases = ["2027-01-01","2026-12-25","2026-11-02","2026-10-01","2027-12-27"];
for (const d of cases) {
  const msg = buildMessage(cfg, pendingAnnouncement({
    last_rebalance: "2020-01-01", holdings: picks,
    pending_signal: { for_month: d.slice(0,7), computed_date: "x", execute_on: d, regime_ok: true, picks },
  })!);
  const line = msg.split("\n").find(l => l.includes("Buy at the open"))!.replace(/<[^>]+>/g,"");
  console.log(`  execute_on ${d} -> ${line}`);
}

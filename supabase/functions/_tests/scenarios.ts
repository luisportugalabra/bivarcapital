import { pendingAnnouncement, buildMessage, Cfg } from "../_shared/momentum.ts";

const cfg: Cfg = { key: "t", label: "Test Momentum", stateId: 99,
  portfolio: "x.json", cur: "$", page: "https://example.com" };
const nowMonth = new Date().toISOString().slice(0, 7);
const picks = [{ ticker: "AAA", name: "Alpha Co", sector: "Tech" },
               { ticker: "BBB", name: "Beta Co", sector: "Industrials" }];

const cases: [string, any, string][] = [
  ["fim de mes numa sexta (exec na 2a feira)",
   { last_rebalance: "2026-10-01", holdings: picks,
     pending_signal: { for_month: "2026-11", computed_date: "2026-10-30",
                       execute_on: "2026-11-02", regime_ok: true, picks } },
   "pending 2026-11, buy Monday 2 November"],
  ["fim de mes numa 3a feira",
   { last_rebalance: "2026-09-01", holdings: picks,
     pending_signal: { for_month: "2026-07", computed_date: "2026-06-30",
                       execute_on: "2026-07-01", regime_ok: true, picks } },
   "pending 2026-07"],
  ["regime CASH no lock-in (USA, regime_ok=false)",
   { last_rebalance: "2026-10-01", holdings: picks,
     pending_signal: { for_month: "2026-11", computed_date: "2026-10-30",
                       execute_on: "2026-11-02", regime_ok: false, picks } },
   "DEFENSIVE, zero picks"],
  ["regime CASH no lock-in (DE/CA, regime='defensive')",
   { last_rebalance: "2026-10-01", holdings: picks,
     pending_signal: { for_month: "2026-11", computed_date: "2026-10-30",
                       execute_on: "2026-11-02", regime: "defensive", picks: [] } },
   "DEFENSIVE, zero picks"],
  ["lock-in antigo sem campo regime",
   { last_rebalance: "2026-10-01", holdings: picks,
     pending_signal: { for_month: "2026-11", execute_on: "2026-11-02", picks } },
   "assume momentum (so eram escritos com regime on)"],
  ["meio do mes, sem pending -> SILENCIO",
   { last_rebalance: "2026-08-03", holdings: picks, pending_signal: null },
   "null"],
  ["lock-in falhou mas rebalance aconteceu -> fallback",
   { last_rebalance: `${nowMonth}-01`, holdings: picks, pending_signal: null },
   "executed, com aviso de atraso"],
  ["fallback com regime cash (holdings vazios, USA)",
   { last_rebalance: `${nowMonth}-01`, holdings: [], pending_signal: null },
   "executed + DEFENSIVE"],
  ["rebalance de mes anterior, sem pending -> SILENCIO",
   { last_rebalance: "2020-01-02", holdings: picks, pending_signal: null },
   "null"],
];

let fails = 0;
for (const [name, pf, expect] of cases) {
  const a = pendingAnnouncement(pf);
  const head = a ? buildMessage(cfg, a).split("\n")[0].replace(/<\/?b>/g, "") : "(nada enviado)";
  const detail = a ? `kind=${a.kind} month=${a.month} cash=${a.cash} picks=${a.picks.length} exec=${a.executeOn}` : "null";
  console.log(`\n▸ ${name}`);
  console.log(`   esperado: ${expect}`);
  console.log(`   obtido:   ${detail}`);
  console.log(`   assunto:  ${head}`);
  // hard invariants
  if (a && !a.cash && a.picks.length === 0) { console.log("   ✗ BUG: nao-cash com zero picks"); fails++; }
  if (a && a.cash && a.picks.length > 0)    { console.log("   ✗ BUG: cash com picks"); fails++; }
  if (a && !/^\d{4}-\d{2}$/.test(a.month))  { console.log("   ✗ BUG: mes mal formado"); fails++; }
}

console.log("\n=== mensagem completa (caso sexta -> segunda) ===");
console.log(buildMessage(cfg, pendingAnnouncement(cases[0][1])).replace(/<[^>]+>/g, ""));
console.log("\n=== mensagem completa (caso cash) ===");
console.log(buildMessage(cfg, pendingAnnouncement(cases[2][1])).replace(/<[^>]+>/g, ""));
console.log(`\nfalhas de invariante: ${fails}`);
if (fails) Deno.exit(1);

// --- fallback window ---
const iso = (d: Date) => d.toISOString().slice(0, 10);
const daysAgo = (n: number) => iso(new Date(Date.now() - n * 86400000));
console.log("\n=== janela do fallback (sem pending_signal) ===");
for (const n of [0, 1, 2, 4, 5, 10, 17]) {
  const a = pendingAnnouncement({ last_rebalance: daysAgo(n), holdings: picks, pending_signal: null });
  const want = n <= 4;
  const got = a !== null;
  console.log(`   rebalance ha ${String(n).padStart(2)} dias -> ${got ? "ENVIA" : "silencio"}  ${got === want ? "✓" : "✗"}`);
}

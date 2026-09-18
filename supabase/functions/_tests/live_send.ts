import { handle, Cfg } from "../_shared/momentum.ts";

const cfgs: Cfg[] = [
  { key: "usa", label: "USA Momentum", stateId: 1,
    portfolio: "momentum-portfolio.json", cur: "$",
    page: "https://bivarcapital.com/momentum.html" },
  { key: "canada", label: "Canada Momentum", stateId: 3,
    portfolio: "canada-momentum-portfolio.json", cur: "C$",
    page: "https://bivarcapital.com/canada-momentum.html" },
  { key: "germany", label: "Germany Momentum", stateId: 4,
    portfolio: "germany-momentum-portfolio.json", cur: "€",
    page: "https://bivarcapital.com/germany-momentum.html" },
];

// 1) auth must actually be enforced
const noAuth = await handle(new Request("http://x/?test=1"), cfgs[0]);
console.log(`gate de autorizacao sem header: HTTP ${noAuth.status} ${noAuth.status === 401 ? "✓" : "✗ ESPERAVA 401"}`);

const badAuth = await handle(new Request("http://x/?test=1",
  { headers: { Authorization: "Bearer errado" } }), cfgs[0]);
console.log(`gate de autorizacao com segredo errado: HTTP ${badAuth.status} ${badAuth.status === 401 ? "✓" : "✗ ESPERAVA 401"}`);

// 2) real send, through the exact deployed code path
const secret = Deno.env.get("CRON_SECRET")!;
for (const cfg of cfgs) {
  const r = await handle(
    new Request("http://x/?test=1", { headers: { Authorization: `Bearer ${secret}` } }),
    cfg);
  console.log(`${cfg.key.padEnd(8)} HTTP ${r.status}  ${await r.text()}`);
}

// 3) a normal (non-test) run must stay silent mid-month
console.log("\n--- corrida normal a meio do mes (nao deve enviar nada) ---");
for (const cfg of cfgs) {
  const r = await handle(
    new Request("http://x/", { headers: { Authorization: `Bearer ${secret}` } }),
    cfg);
  console.log(`${cfg.key.padEnd(8)} HTTP ${r.status}  ${await r.text()}`);
}

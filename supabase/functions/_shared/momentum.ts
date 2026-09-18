// Shared delivery logic for the three monthly momentum alerts.
//
// The alert is driven entirely by the data the signal job publishes, never by
// the cron's firing date. The signal job locks in `pending_signal` on the last
// trading day of the month (it knows the real trading calendar; this function
// does not), so a daily cron that reads it can never land on the wrong day:
// whichever morning it first sees a pending signal is, by construction, the
// morning before the rebalance. Weekends and exchange holidays need no special
// handling here, and a cron run that is skipped or delayed just sends later
// that day instead of not at all.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const BOT_TOKEN = "8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI";
const ADMIN_CHAT_ID = 5151262026;
const RAW = "https://raw.githubusercontent.com/luisportugalabra/bivarcapital/main";
// How long after a rebalance a missed-lock-in alert may still go out.
const FALLBACK_WINDOW_DAYS = 4;

export interface Cfg {
  key: string;        // "usa" | "canada" | "germany"
  label: string;      // headline name
  stateId: number;    // row in momentum_signal_state
  portfolio: string;  // portfolio JSON filename
  cur: string;        // currency symbol
  page: string;       // strategy page URL
}

const sb = () =>
  createClient(SUPABASE_URL, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "");

async function sendTelegram(chatId: number, text: string) {
  const r = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId, text, parse_mode: "HTML", disable_web_page_preview: true,
    }),
  });
  if (!r.ok) throw new Error(`telegram ${r.status}: ${await r.text()}`);
}

// Fixed-date closures that every one of the three exchanges observes. The
// signal job's `execute_on` skips weekends but knows nothing about holidays, so
// without this the New Year message would read "buy Friday 1 January" whenever
// 31 December is a weekday -- most years. This only corrects the date the
// message states; which month the rebalance belongs to is decided upstream and
// is unaffected either way.
const FIXED_CLOSURES = ["01-01", "12-25", "12-26"];

function nextOpenDay(iso: string): string {
  let d = new Date(`${iso}T12:00:00Z`);
  for (let i = 0; i < 10; i++) {
    const dow = d.getUTCDay();
    const md = d.toISOString().slice(5, 10);
    if (dow !== 0 && dow !== 6 && !FIXED_CLOSURES.includes(md)) break;
    d = new Date(d.getTime() + 86400000);
  }
  return d.toISOString().slice(0, 10);
}

function prettyDate(iso: string): string {
  const d = new Date(`${nextOpenDay(iso)}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  });
}

/** What, if anything, should be announced right now. */
export function pendingAnnouncement(pf: any) {
  const ps = pf.pending_signal;
  if (ps?.for_month) {
    // Regime is recorded differently per market: USA uses `regime_ok`,
    // Canada/Germany a `regime` string. Absent on older locked signals,
    // which were only ever written while the regime was on.
    const on = ps.regime_ok !== undefined
      ? !!ps.regime_ok
      : (ps.regime ?? "momentum") === "momentum";
    return {
      month: ps.for_month,
      picks: on ? (ps.picks || []) : [],
      cash: !on,
      executeOn: ps.execute_on || null,
      computedOn: ps.computed_date || null,
      kind: "pending",
    };
  }
  // Fallback: the lock-in run failed but the rebalance itself happened, so
  // announce the executed holdings rather than staying silent this month. This
  // is deliberately bounded to the days right after the rebalance -- an
  // unbounded "same calendar month" test would fire on every run all month,
  // and on a fresh state row that means blasting a weeks-late alert.
  const reb = String(pf.last_rebalance || "");
  // Whole calendar days, so the window boundary is not decided by the hour the
  // cron happens to run at.
  const today = Date.parse(`${new Date().toISOString().slice(0, 10)}T00:00:00Z`);
  const ageDays = reb
    ? Math.round((today - Date.parse(`${reb}T00:00:00Z`)) / 86400000)
    : Infinity;
  if (ageDays >= 0 && ageDays <= FALLBACK_WINDOW_DAYS) {
    const holdings = pf.holdings || [];
    const cash = pf.regime === undefined ? holdings.length === 0
                                         : String(pf.regime).toLowerCase() !== "momentum";
    return {
      month: reb.slice(0, 7), picks: holdings, cash, executeOn: reb,
      computedOn: null, kind: "executed",
    };
  }
  return null;
}

export function buildMessage(cfg: Cfg, a: any): string {
  const when = a.executeOn ? prettyDate(a.executeOn) : "the next trading day";
  const late = a.kind === "executed"
    ? `\n\n⚠️ Sent after the rebalance — execute at the next open.`
    : "";
  if (a.cash) {
    return `🛡 <b>${cfg.label.toUpperCase()} — DEFENSIVE</b>\n\n` +
      `The regime filter is off.\n\n` +
      `<b>Action: sell everything, hold cash.</b>\n\n` +
      `Effective at the open on ${when}.${late}\n\n${cfg.page}`;
  }
  const w = (100 / a.picks.length).toFixed(1);
  const list = a.picks.map((s: any, i: number) => {
    const bits = [s.name, s.sector].filter(Boolean).join(" · ");
    return `${i + 1}. <b>${s.ticker}</b>${bits ? `\n    ${bits}` : ""}`;
  }).join("\n");
  return `📈 <b>${cfg.label.toUpperCase()} — REBALANCE</b>\n\n` +
    `<b>Buy at the open on ${when}</b>, ${w}% each:\n\n${list}\n\n` +
    (a.computedOn ? `Signal locked in at the ${a.computedOn} close.` : "") +
    `${late}\n\n${cfg.page}`;
}

export async function handle(req: Request, cfg: Cfg): Promise<Response> {
  try {
    const url = new URL(req.url);
    const isTest = url.searchParams.get("test") === "1";
    const secret = Deno.env.get("CRON_SECRET") || "";
    if (req.headers.get("Authorization") !== `Bearer ${secret}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const localDir = Deno.env.get("LOCAL_PORTFOLIO_DIR");
    let pf: any;
    if (localDir) {
      pf = JSON.parse(await Deno.readTextFile(`${localDir}/${cfg.portfolio}`));
    } else {
      const resp = await fetch(`${RAW}/${cfg.portfolio}?t=${Date.now()}`);
      if (!resp.ok) throw new Error(`GitHub fetch failed: ${resp.status}`);
      pf = await resp.json();
    }

    let a = pendingAnnouncement(pf);
    if (isTest && !a) {
      // Nothing scheduled -- show what the current holdings message looks like.
      const holdings = pf.holdings || [];
      a = {
        month: String(pf.last_rebalance || "").slice(0, 7), picks: holdings,
        cash: holdings.length === 0, executeOn: pf.last_rebalance,
        computedOn: null, kind: "pending",
      };
    }
    if (!a) {
      return Response.json({ strategy: cfg.key, skipped: "nothing scheduled" });
    }

    const client = isTest ? null : sb();
    if (client) {
      const { data: prev } = await client.from("momentum_signal_state")
        .select("*").eq("id", cfg.stateId).maybeSingle();
      if (prev?.month === a.month) {
        return Response.json({ strategy: cfg.key, skipped: "already sent", month: a.month });
      }
    }

    const msg = (isTest ? "🧪 <b>TEST</b>\n\n" : "") + buildMessage(cfg, a);

    let chatIds: number[] = [ADMIN_CHAT_ID];
    if (client) {
      const { data: subs } = await client.from("telegram_subscribers")
        .select("chat_id").eq("status", "approved");
      chatIds = subs?.map((s: any) => s.chat_id) || [];
    }

    let sent = 0;
    for (const id of chatIds) {
      try { await sendTelegram(id, msg); sent++; }
      catch (e) { console.error(`send failed ${id}:`, e); }
    }

    // Only claim the month once a message actually went out, so a total
    // delivery failure retries on the next cron run instead of being swallowed.
    if (client && sent > 0) {
      const { error } = await client.from("momentum_signal_state").upsert({
        id: cfg.stateId, month: a.month, date: a.executeOn,
        regime: a.cash ? "cash" : "momentum",
        portfolio: JSON.stringify(a.picks.map((s: any) => s.ticker)),
        updated: new Date().toISOString(),
      });
      if (error) throw new Error(`state upsert failed: ${error.message}`);
    }

    return Response.json({ strategy: cfg.key, month: a.month, kind: a.kind, sent, test: isTest });
  } catch (e) {
    console.error(`${cfg.key} fatal:`, e);
    try { await sendTelegram(ADMIN_CHAT_ID, `⚠️ ${cfg.label} alert FAILED:\n${e}`); } catch {}
    return Response.json({ error: String(e) }, { status: 500 });
  }
}

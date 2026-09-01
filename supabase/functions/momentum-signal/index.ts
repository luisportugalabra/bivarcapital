import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN") || "";
const ADMIN_CHAT = 5151262026;
const STATE_ID = 1; // USA = row 1 in momentum_signal_state
const RAW = "https://raw.githubusercontent.com/luisportugalabra/bivarcapital/main";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

async function sendTelegram(chatId: number, text: string) {
  await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
  });
}

// Cache-busted so we never read a CDN copy from before the data workflow pushed.
async function fetchJson(name: string) {
  const r = await fetch(`${RAW}/${name}?t=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`fetch ${name} failed: ${r.status}`);
  return await r.json();
}

serve(async (req) => {
  try {
    const CRON_SECRET = Deno.env.get("CRON_SECRET") || "";
    if (req.headers.get("Authorization") !== `Bearer ${CRON_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }
    if (!BOT_TOKEN) throw new Error("TELEGRAM_BOT_TOKEN secret is not set");

    const url = new URL(req.url);
    // force=1 re-sends a month already marked as sent.
    // test=1 renders the message and sends it only to ADMIN_CHAT, without
    // touching the monthly state — a dry run that never reaches subscribers.
    const force = url.searchParams.get("force") === "1";
    const test = url.searchParams.get("test") === "1";
    const currentPeriod = new Date().toISOString().slice(0, 7); // "2026-09"

    // The site renders momentum-portfolio.json — the holdings actually bought
    // at the rebalance. Read the same file so Telegram can never disagree with
    // the site; momentum-data.json is only used for the regime line and mcaps.
    let portfolio = await fetchJson("momentum-portfolio.json");
    let data = await fetchJson("momentum-data.json");

    // Only announce once the current month's rebalance has actually landed.
    // Retry once: the data workflow pushes and calls us seconds later, so the
    // first read can still hit a stale CDN copy.
    if (portfolio.last_rebalance?.slice(0, 7) !== currentPeriod) {
      await new Promise((r) => setTimeout(r, 20000));
      portfolio = await fetchJson("momentum-portfolio.json");
      data = await fetchJson("momentum-data.json");
    }

    if (portfolio.last_rebalance?.slice(0, 7) !== currentPeriod && !test) {
      console.log(
        `USA: no rebalance for ${currentPeriod} yet ` +
          `(last_rebalance=${portfolio.last_rebalance}) — not sending`
      );
      return new Response(
        JSON.stringify({
          skipped: true,
          reason: "stale",
          last_rebalance: portfolio.last_rebalance,
          month: currentPeriod,
        }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    const holdings = portfolio.holdings || [];
    const date = portfolio.last_rebalance;
    const regime = holdings.length === 0 ? "cash" : "momentum";
    const sp500 = data.sp500;
    const ma250 = data.sp500_ma250;
    const totalEligible = data.total_eligible;

    // Monthly idempotency
    const { data: prevRow } = await sb
      .from("momentum_signal_state")
      .select("*")
      .eq("id", STATE_ID)
      .single();

    const alreadySent = (prevRow?.month || null) === currentPeriod;

    const { error: upsertErr } = test
      ? { error: null }
      : await sb.from("momentum_signal_state").upsert({
          id: STATE_ID,
          month: currentPeriod,
          date,
          regime,
          portfolio: JSON.stringify(holdings.map((h: any) => h.ticker)),
          updated: new Date().toISOString(),
        });
    if (upsertErr) throw new Error(`state upsert failed: ${upsertErr.message}`);

    if (alreadySent && !force && !test) {
      console.log("USA: already sent this month — skipping Telegram");
      return new Response(
        JSON.stringify({ regime, skipped: true, reason: "already_sent", month: currentPeriod }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    let chatIds: number[];
    if (test) {
      chatIds = [ADMIN_CHAT];
    } else {
      const { data: subscribers } = await sb
        .from("telegram_subscribers")
        .select("chat_id")
        .eq("status", "approved");
      chatIds = subscribers?.map((s: any) => s.chat_id) || [];
    }
    console.log(`USA: sending to ${chatIds.length} chat(s)${test ? " [TEST]" : ""}`);

    const banner = test ? "🧪 <b>TEST — not sent to subscribers</b>\n\n" : "";
    let msg: string;
    if (regime === "cash") {
      msg =
        banner +
        `🛡 <b>USA MOMENTUM — DEFENSIVE</b>\n\n` +
        `S&P 500 ($${sp500?.toLocaleString("en-US")}) is <b>below</b> MA250 ($${ma250?.toLocaleString("en-US")})\n\n` +
        `<b>Action: Sell all stocks → Move to cash (100%)</b>\n\n` +
        `${totalEligible} stocks screened\n` +
        `Rebalance date: ${date}\n\n` +
        `https://bivarcapital.com/momentum.html`;
    } else {
      // mcap comes from the screen; a holding kept from a previous month may
      // no longer be in the top 20, so the line degrades gracefully.
      const mcap: Record<string, number> = {};
      for (const t of data.top20 || []) mcap[t.ticker] = t.mcap_b;

      const stockList = holdings
        .map((h: any, i: number) => {
          const tail = [h.sector, mcap[h.ticker] != null ? `$${mcap[h.ticker]}B` : null]
            .filter(Boolean)
            .join(" · ");
          return `${i + 1}. <b>${h.ticker}</b> — ${h.name}` + (tail ? `\n   ${tail}` : "");
        })
        .join("\n");

      const weight = (100 / holdings.length).toFixed(1);
      msg =
        banner +
        `📈 <b>USA MOMENTUM — BUY STOCKS</b>\n\n` +
        `S&P 500 ($${sp500?.toLocaleString("en-US")}) is <b>above</b> MA250 ($${ma250?.toLocaleString("en-US")})\n\n` +
        `<b>Portfolio (equal weight ~${weight}% each):</b>\n\n` +
        `${stockList}\n\n` +
        `${totalEligible} stocks screened\n` +
        `Rebalance date: ${date}\n\n` +
        `https://bivarcapital.com/momentum.html`;
    }

    for (const chatId of chatIds) {
      try {
        await sendTelegram(chatId, msg);
        console.log(`  Sent to ${chatId}`);
      } catch (e) {
        console.error(`  Failed for ${chatId}:`, e);
      }
    }

    return new Response(
      JSON.stringify({ regime, date, sent: chatIds.length, forced: force, test }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (e) {
    console.error("Fatal error:", e);
    try {
      await sendTelegram(ADMIN_CHAT, `⚠️ USA Momentum Signal FAILED:\n${e}`);
    } catch {}
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});

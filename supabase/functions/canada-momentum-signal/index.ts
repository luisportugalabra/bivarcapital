import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN") || "";
const ADMIN_CHAT = 5151262026;
const STATE_ID = 3; // Canada = row 3 in momentum_signal_state
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

    const force = new URL(req.url).searchParams.get("force") === "1";
    const currentPeriod = new Date().toISOString().slice(0, 7);

    // The site renders canada-momentum-portfolio.json — read the same file so
    // Telegram can never disagree with the site.
    let portfolio = await fetchJson("canada-momentum-portfolio.json");
    let data = await fetchJson("canada-momentum-data.json");

    if (portfolio.last_rebalance?.slice(0, 7) !== currentPeriod) {
      await new Promise((r) => setTimeout(r, 20000));
      portfolio = await fetchJson("canada-momentum-portfolio.json");
      data = await fetchJson("canada-momentum-data.json");
    }

    if (portfolio.is_live === false) {
      console.log(`Canada: not live (${portfolio.not_live_reason}) — not sending`);
      return new Response(
        JSON.stringify({ skipped: true, reason: "not_live", detail: portfolio.not_live_reason }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    if (portfolio.last_rebalance?.slice(0, 7) !== currentPeriod) {
      console.log(
        `Canada: no rebalance for ${currentPeriod} yet ` +
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
    const regime = holdings.length === 0 ? "defensive" : "momentum";
    const tsx = portfolio.tsx ?? data.tsx;
    const ma75 = portfolio.tsx_ma75 ?? data.tsx_ma75;

    const { data: prevRow } = await sb
      .from("momentum_signal_state")
      .select("*")
      .eq("id", STATE_ID)
      .single();

    const alreadySent = (prevRow?.month || null) === currentPeriod;

    const { error: upsertErr } = await sb.from("momentum_signal_state").upsert({
      id: STATE_ID,
      month: currentPeriod,
      date,
      regime,
      portfolio: JSON.stringify(holdings.map((h: any) => h.ticker)),
      updated: new Date().toISOString(),
    });
    if (upsertErr) throw new Error(`state upsert failed: ${upsertErr.message}`);

    if (alreadySent && !force) {
      console.log("Canada: already sent this month — skipping");
      return new Response(
        JSON.stringify({ regime, skipped: true, reason: "already_sent", month: currentPeriod }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    const { data: subscribers } = await sb
      .from("telegram_subscribers")
      .select("chat_id")
      .eq("status", "approved");

    const chatIds = subscribers?.map((s: any) => s.chat_id) || [];
    console.log(`Canada: sending to ${chatIds.length} subscribers`);

    let msg: string;
    if (regime === "defensive") {
      msg =
        `🛡 <b>CANADA MOMENTUM — DEFENSIVE</b>\n\n` +
        `TSX (${tsx?.toLocaleString("en-CA")}) is <b>below</b> MA75 (${ma75?.toLocaleString("en-CA")})\n\n` +
        `<b>Action: Stay in cash (CAD)</b>\n\n` +
        `Rebalance date: ${date}\n\n` +
        `https://bivarcapital.com/canada-momentum.html`;
    } else {
      const mcap: Record<string, number> = {};
      for (const t of data.portfolio || []) mcap[t.ticker] = t.mcap_b;

      const stockList = holdings
        .map((h: any, i: number) => {
          const m = mcap[h.ticker];
          return `${i + 1}. <b>${h.ticker}</b> — ${h.name}` +
            (m != null ? `\n   C$${m.toFixed(2)}B` : "");
        })
        .join("\n");

      const weight = (100 / holdings.length).toFixed(1);
      msg =
        `📈 <b>CANADA MOMENTUM — BUY STOCKS</b>\n\n` +
        `TSX (${tsx?.toLocaleString("en-CA")}) is <b>above</b> MA75 (${ma75?.toLocaleString("en-CA")})\n\n` +
        `<b>Portfolio (${holdings.length} stocks, equal weight ~${weight}% each):</b>\n\n` +
        `${stockList}\n\n` +
        `Rebalance date: ${date}\n\n` +
        `https://bivarcapital.com/canada-momentum.html`;
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
      JSON.stringify({ regime, date, sent: chatIds.length, forced: force }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (e) {
    console.error("Fatal error:", e);
    try {
      await sendTelegram(ADMIN_CHAT, `⚠️ Canada Momentum Signal FAILED:\n${e}`);
    } catch {}
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BOT_TOKEN = "8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

async function sendTelegram(chatId: number, text: string) {
  await fetch(
    `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
    }
  );
}

serve(async (req) => {
  try {
    const CRON_SECRET = Deno.env.get("CRON_SECRET") || "";
    const authHeader = req.headers.get("Authorization");
    if (authHeader !== `Bearer ${CRON_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Fetch momentum-data.json from GitHub (always fresh)
    const resp = await fetch(
      "https://raw.githubusercontent.com/luisportugalabra/bivarcapital/main/momentum-data.json"
    );
    if (!resp.ok) throw new Error(`GitHub fetch failed: ${resp.status}`);
    const data = await resp.json();

    const date = data.date;
    const regime = data.regime;
    const sp500 = data.sp500;
    const ma250 = data.sp500_ma250;
    const portfolio = data.portfolio || [];
    const totalEligible = data.total_eligible;

    // Check if already sent this month
    const { data: prevRow } = await sb
      .from("momentum_signal_state")
      .select("*")
      .eq("id", 1)
      .single();

    // Daily idempotency during testing, switch to monthly later
    const currentPeriod = new Date().toISOString().slice(0, 10); // "2026-04-23" (daily)
    // const currentPeriod = new Date().toISOString().slice(0, 7); // "2026-04" (monthly — uncomment for production)
    const prevMonth = prevRow?.month || null;
    const alreadySent = prevMonth === currentPeriod;

    // Save state
    await sb.from("momentum_signal_state").upsert({
      id: 1,
      month: currentPeriod,
      date,
      regime,
      portfolio: JSON.stringify(portfolio.map((s: any) => s.ticker)),
      updated: new Date().toISOString(),
    });

    if (alreadySent) {
      console.log("Already sent this month — skipping Telegram");
      return new Response(
        JSON.stringify({ regime, skipped: true, month: currentMonth }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    // Get subscribers (same table as BTC, approved status)
    const { data: subscribers } = await sb
      .from("telegram_subscribers")
      .select("chat_id")
      .eq("status", "approved");

    const chatIds = subscribers?.map((s) => s.chat_id) || [];
    console.log(`Sending momentum signal to ${chatIds.length} subscribers`);

    // Build message
    let msg: string;
    if (regime === "gld") {
      msg =
        `🛡 <b>MOMENTUM SIGNAL — DEFENSIVE</b>\n\n` +
        `S&P 500 ($${sp500?.toLocaleString("en-US")}) is <b>below</b> MA250 ($${ma250?.toLocaleString("en-US")})\n\n` +
        `<b>Action: Sell all stocks → Buy GLD (100%)</b>\n\n` +
        `${totalEligible} stocks screened\n` +
        `Signal date: ${date}\n\n` +
        `https://bivarcapital.com/momentum.html`;
    } else {
      const stockList = portfolio
        .map(
          (s: any, i: number) =>
            `${i + 1}. <b>${s.ticker}</b> — ${s.name}\n   ${s.sector} · +${s.composite}% · $${s.mcap_b}B`
        )
        .join("\n");

      msg =
        `📈 <b>MOMENTUM SIGNAL — BUY STOCKS</b>\n\n` +
        `S&P 500 ($${sp500?.toLocaleString("en-US")}) is <b>above</b> MA250 ($${ma250?.toLocaleString("en-US")})\n\n` +
        `<b>Portfolio (equal weight ~14.3% each):</b>\n\n` +
        `${stockList}\n\n` +
        `${totalEligible} stocks screened\n` +
        `Signal date: ${date}\n\n` +
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
      JSON.stringify({ regime, date, sent: chatIds.length }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (e) {
    console.error("Fatal error:", e);
    try {
      await sendTelegram(5151262026, `⚠️ Momentum Signal function FAILED:\n${e}`);
    } catch {}
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});

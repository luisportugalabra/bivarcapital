import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BOT_TOKEN = "8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI";
const STATE_ID = 2; // UK = row 2 in momentum_signal_state

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

async function sendTelegram(chatId: number, text: string) {
  await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
  });
}

serve(async (req) => {
  try {
    const CRON_SECRET = Deno.env.get("CRON_SECRET") || "";
    if (req.headers.get("Authorization") !== `Bearer ${CRON_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Fetch latest signal from GitHub
    const resp = await fetch(
      "https://raw.githubusercontent.com/luisportugalabra/bivarcapital/main/uk-momentum-data.json"
    );
    if (!resp.ok) throw new Error(`GitHub fetch failed: ${resp.status}`);
    const data = await resp.json();

    const date = data.date;
    const regime = data.regime;
    const ftse = data.ftse100;
    const ma200 = data.ftse100_ma200;
    const portfolio = data.portfolio || [];

    // Monthly idempotency
    const currentPeriod = new Date().toISOString().slice(0, 7);
    const { data: prevRow } = await sb
      .from("momentum_signal_state")
      .select("*")
      .eq("id", STATE_ID)
      .single();

    const alreadySent = (prevRow?.month || null) === currentPeriod;

    await sb.from("momentum_signal_state").upsert({
      id: STATE_ID,
      month: currentPeriod,
      date,
      regime,
      portfolio: JSON.stringify(portfolio.map((s: any) => s.ticker)),
      updated: new Date().toISOString(),
    });

    if (alreadySent) {
      console.log("UK: already sent this month — skipping");
      return new Response(
        JSON.stringify({ regime, skipped: true, month: currentPeriod }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    const { data: subscribers } = await sb
      .from("telegram_subscribers")
      .select("chat_id")
      .eq("status", "approved");

    const chatIds = subscribers?.map((s: any) => s.chat_id) || [];
    console.log(`UK: sending to ${chatIds.length} subscribers`);

    let msg: string;
    if (regime === "gld" || regime === "defensive") {
      msg =
        `🛡 <b>UK MOMENTUM — DEFENSIVE</b>\n\n` +
        `FTSE 100 (${ftse?.toLocaleString("en-GB")}) is <b>below</b> MA200 (${ma200?.toLocaleString("en-GB")})\n\n` +
        `<b>Action: Stay in cash (GBP)</b>\n\n` +
        `Signal date: ${date}\n\n` +
        `https://bivarcapital.com/uk-momentum.html`;
    } else {
      const stockList = portfolio
        .map((s: any, i: number) =>
          `${i + 1}. <b>${s.ticker}</b> — ${s.name}\n   ${s.sector} · ${s.ret_6m != null ? (s.ret_6m >= 0 ? "+" : "") + s.ret_6m.toFixed(1) + "% 6M" : ""} · £${s.mcap_b?.toFixed(2)}B`
        )
        .join("\n");

      msg =
        `📈 <b>UK MOMENTUM — BUY STOCKS</b>\n\n` +
        `FTSE 100 (${ftse?.toLocaleString("en-GB")}) is <b>above</b> MA200 (${ma200?.toLocaleString("en-GB")})\n\n` +
        `<b>Portfolio (${portfolio.length} stocks, equal weight):</b>\n\n` +
        `${stockList}\n\n` +
        `Signal date: ${date}\n\n` +
        `https://bivarcapital.com/uk-momentum.html`;
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
      await sendTelegram(5151262026, `⚠️ UK Momentum Signal FAILED:\n${e}`);
    } catch {}
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});

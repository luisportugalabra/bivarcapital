import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BOT_TOKEN = "8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI";
const GITHUB_TOKEN = Deno.env.get("GITHUB_TOKEN") || "";
const ADMIN_CHAT_ID = 5151262026;

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

async function sendTelegram(chatId: number, text: string) {
  await fetch(
    `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage?chat_id=${chatId}&text=${encodeURIComponent(text)}`
  );
}

async function fetchPrices(): Promise<number[]> {
  // Source 1: CoinMetrics
  try {
    const start = new Date(Date.now() - 220 * 86400000).toISOString().slice(0, 10);
    const resp = await fetch(
      `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD&frequency=1d&start_time=${start}&page_size=10000`
    );
    if (!resp.ok) throw new Error(`CoinMetrics ${resp.status}`);
    const data = await resp.json();
    const closes = data.data.map((d: any) => parseFloat(d.PriceUSD));
    if (closes.length >= 155) {
      console.log(`CoinMetrics: ${closes.length} closes`);
      return closes;
    }
  } catch (e) {
    console.warn("CoinMetrics failed:", e);
  }

  // Source 2: CoinGecko
  try {
    const resp = await fetch(
      "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=220&interval=daily"
    );
    if (!resp.ok) throw new Error(`CoinGecko ${resp.status}`);
    const data = await resp.json();
    const closes = data.prices.map((p: number[]) => p[1]);
    if (closes.length >= 155) {
      console.log(`CoinGecko: ${closes.length} closes`);
      return closes;
    }
  } catch (e) {
    console.warn("CoinGecko failed:", e);
  }

  throw new Error("All data sources failed");
}

async function getLivePrice(): Promise<number> {
  try {
    const resp = await fetch(
      "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    );
    const data = await resp.json();
    return data.bitcoin.usd;
  } catch {
    // fallback to last close
    return 0;
  }
}

async function updateGitHub(signalData: Record<string, any>) {
  if (!GITHUB_TOKEN) {
    console.warn("No GITHUB_TOKEN — skipping repo update");
    return;
  }
  try {
    // Get current file SHA
    const getResp = await fetch(
      "https://api.github.com/repos/luisportugalabra/bivarcapital/contents/btc-signal.json",
      { headers: { Authorization: `Bearer ${GITHUB_TOKEN}`, "User-Agent": "bivar-signal" } }
    );
    const current = await getResp.json();
    const sha = current.sha;

    // Update file
    const content = btoa(JSON.stringify(signalData, null, 2));
    await fetch(
      "https://api.github.com/repos/luisportugalabra/bivarcapital/contents/btc-signal.json",
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${GITHUB_TOKEN}`,
          "User-Agent": "bivar-signal",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: `Update BTC signal: ${signalData.signal} ${signalData.date}`,
          content,
          sha,
          committer: { name: "BTC Signal Bot", email: "bot@bivarcapital.com" },
        }),
      }
    );
    console.log("GitHub btc-signal.json updated");
  } catch (e) {
    console.error("GitHub update failed:", e);
  }
}

serve(async (req) => {
  try {
    // Auth: check cron secret
    const CRON_SECRET = Deno.env.get("CRON_SECRET") || "";
    const authHeader = req.headers.get("Authorization");
    if (authHeader !== `Bearer ${CRON_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const closes = await fetchPrices();
    const n = closes.length;

    // MA155
    const ma155 = closes.slice(n - 155).reduce((a, b) => a + b, 0) / 155;

    // RSI14
    let gains = 0, losses = 0;
    for (let i = n - 14; i < n; i++) {
      const diff = closes[i] - closes[i - 1];
      if (diff > 0) gains += diff;
      else losses -= diff;
    }
    const avgGain = gains / 14;
    const avgLoss = losses / 14;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = 100 - 100 / (1 + rs);

    // Vol20
    const rets: number[] = [];
    for (let i = n - 20; i < n; i++) {
      rets.push(closes[i] / closes[i - 1] - 1);
    }
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1);
    const vol = Math.sqrt(variance) * Math.sqrt(365);

    const price = closes[n - 1];
    const signal = rsi > 54 && price > ma155 && vol < 1.0 ? "BUY" : "CASH";
    const date = new Date().toISOString().slice(0, 10);

    // Live price for display
    let livePrice = await getLivePrice();
    if (livePrice === 0) livePrice = price;

    console.log(`Date: ${date}, Close: $${price.toFixed(0)}, Live: $${livePrice.toFixed(0)}, RSI: ${rsi.toFixed(1)}, MA155: $${ma155.toFixed(0)}, Vol: ${(vol * 100).toFixed(0)}%, Signal: ${signal}`);

    // Check previous signal from Supabase (stored in a simple key-value)
    const { data: prevRow } = await sb
      .from("btc_signal_state")
      .select("*")
      .eq("id", 1)
      .single();

    const prevSignal = prevRow?.signal || null;
    const prevDate = prevRow?.date || null;
    const alreadyRanToday = prevDate === date;

    // Save state to Supabase
    await sb.from("btc_signal_state").upsert({
      id: 1,
      date,
      price: Math.round(livePrice * 100) / 100,
      rsi: Math.round(rsi * 10) / 10,
      ma155: Math.round(ma155 * 100) / 100,
      vol: Math.round(vol * 1000) / 10,
      signal,
      updated: new Date().toISOString(),
    });

    // Update btc-signal.json in GitHub repo
    const signalData = {
      date,
      price: Math.round(livePrice * 100) / 100,
      rsi: Math.round(rsi * 10) / 10,
      ma155: Math.round(ma155 * 100) / 100,
      vol: Math.round(vol * 1000) / 10,
      signal,
      updated: new Date().toISOString(),
    };
    await updateGitHub(signalData);

    // Send Telegram (skip if already sent today with same signal)
    if (alreadyRanToday && prevSignal === signal) {
      console.log("Already sent today — skipping Telegram");
      return new Response(JSON.stringify({ signal, skipped: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Get subscribers
    const { data: subscribers } = await sb
      .from("telegram_subscribers")
      .select("chat_id")
      .eq("status", "approved");

    const chatIds = subscribers?.map((s) => s.chat_id) || [ADMIN_CHAT_ID];
    console.log(`Sending to ${chatIds.length} subscribers`);

    let tgMsg: string;
    if (prevSignal && prevSignal !== signal) {
      const emoji = signal === "BUY" ? "🟢" : "🔴";
      const action = signal === "BUY"
        ? "BUY NOW — all conditions met."
        : "SELL / GO TO CASH — conditions no longer met.";
      tgMsg = `${emoji} SIGNAL CHANGED: ${prevSignal} → ${signal}\n\nPrice: $${livePrice.toLocaleString("en-US", { maximumFractionDigits: 0 })}\nRSI14: ${rsi.toFixed(1)}\nMA155: $${ma155.toLocaleString("en-US", { maximumFractionDigits: 0 })}\nVol20: ${(vol * 100).toFixed(0)}%\n\n${action}\n\nhttps://bivarcapital.com/btc.html`;
    } else {
      const emoji = signal === "BUY" ? "🟢" : "🔴";
      const rsiIcon = rsi > 54 ? "✓" : "✗";
      const maIcon = price > ma155 ? "✓" : "✗";
      const volIcon = vol < 1.0 ? "✓" : "✗";
      tgMsg = `${emoji} Daily BTC: ${signal}\n\nPrice: $${livePrice.toLocaleString("en-US", { maximumFractionDigits: 0 })}\n${rsiIcon} RSI14: ${rsi.toFixed(1)} (>54)\n${maIcon} MA155: $${ma155.toLocaleString("en-US", { maximumFractionDigits: 0 })} (${price > ma155 ? "above" : "below"})\n${volIcon} Vol20: ${(vol * 100).toFixed(0)}% (<100%)\n\nNo change from yesterday.\nhttps://bivarcapital.com/btc.html`;
    }

    for (const chatId of chatIds) {
      try {
        await sendTelegram(chatId, tgMsg);
        console.log(`  Sent to ${chatId}`);
      } catch (e) {
        console.error(`  Failed for ${chatId}:`, e);
      }
    }

    return new Response(JSON.stringify({ signal, date, sent: chatIds.length }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("Fatal error:", e);
    // Notify admin on failure
    try {
      await sendTelegram(ADMIN_CHAT_ID, `⚠️ BTC Signal function FAILED:\n${e}`);
    } catch {}
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});

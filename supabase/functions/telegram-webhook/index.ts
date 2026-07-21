import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://efiyeiwdywodjxxnslvu.supabase.co";
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BOT_TOKEN = "8528820380:AAHNc3wBp_Nm2DCKunZurOGRRvi2e3fJ-MI";
const ADMIN_CHAT_ID = 5151262026;

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

async function sendTelegram(chatId: number, text: string) {
  await fetch(
    `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage?chat_id=${chatId}&text=${encodeURIComponent(text)}`
  );
}

serve(async (req) => {
  try {
    const body = await req.json();
    const msg = body.message;
    if (!msg || !msg.text) return new Response("ok");

    const chatId = msg.chat.id;
    const text = msg.text.trim();
    const username = msg.from?.username || "";
    const firstName = msg.from?.first_name || "";

    // /start — new user wants alerts
    if (text === "/start") {
      // Check if already exists
      const { data: existing } = await sb
        .from("telegram_subscribers")
        .select("*")
        .eq("chat_id", chatId)
        .single();

      if (existing) {
        if (existing.status === "approved") {
          await sendTelegram(chatId, "✅ You're already approved. You'll receive BTC signal alerts automatically.");
        } else {
          await sendTelegram(chatId, "⏳ Your request is pending approval.");
        }
      } else {
        // Insert new request
        await sb.from("telegram_subscribers").insert({
          chat_id: chatId,
          username: username,
          first_name: firstName,
          status: "pending",
        });

        await sendTelegram(chatId, "📩 Request sent. You'll be notified when approved.");

        // Notify admin
        await sendTelegram(
          ADMIN_CHAT_ID,
          `🔔 New alert request:\n\nName: ${firstName}\nUsername: @${username}\nChat ID: ${chatId}\n\nApprove: /approve_${chatId}\nReject: /reject_${chatId}`
        );
      }
    }

    // /approve_XXXXX — admin approves a user
    else if (text.startsWith("/approve_") && chatId === ADMIN_CHAT_ID) {
      const targetId = parseInt(text.replace("/approve_", ""));
      if (targetId) {
        await sb
          .from("telegram_subscribers")
          .update({ status: "approved" })
          .eq("chat_id", targetId);

        await sendTelegram(ADMIN_CHAT_ID, `✅ Approved chat_id ${targetId}`);
        await sendTelegram(targetId, "✅ You've been approved! You'll now receive BTC signal alerts (CASH↔BUY) daily at 00:10 UTC.");
      }
    }

    // /reject_XXXXX — admin rejects
    else if (text.startsWith("/reject_") && chatId === ADMIN_CHAT_ID) {
      const targetId = parseInt(text.replace("/reject_", ""));
      if (targetId) {
        await sb
          .from("telegram_subscribers")
          .update({ status: "rejected" })
          .eq("chat_id", targetId);

        await sendTelegram(ADMIN_CHAT_ID, `❌ Rejected chat_id ${targetId}`);
        await sendTelegram(targetId, "Your request was not approved at this time.");
      }
    }

    // /list — admin lists subscribers
    else if (text === "/list" && chatId === ADMIN_CHAT_ID) {
      const { data } = await sb.from("telegram_subscribers").select("*");
      if (data && data.length > 0) {
        let list = "📋 Subscribers:\n\n";
        for (const s of data) {
          list += `${s.status === "approved" ? "✅" : "⏳"} ${s.first_name} @${s.username} (${s.chat_id}) — ${s.status}\n`;
        }
        await sendTelegram(ADMIN_CHAT_ID, list);
      } else {
        await sendTelegram(ADMIN_CHAT_ID, "No subscribers yet.");
      }
    }

    // /status — any user checks their status
    else if (text === "/status") {
      const { data } = await sb
        .from("telegram_subscribers")
        .select("status")
        .eq("chat_id", chatId)
        .single();

      if (data) {
        await sendTelegram(chatId, `Your status: ${data.status}`);
      } else {
        await sendTelegram(chatId, "You haven't requested access yet. Send /start");
      }
    }

    return new Response("ok");
  } catch (e) {
    console.error(e);
    return new Response("error", { status: 500 });
  }
});

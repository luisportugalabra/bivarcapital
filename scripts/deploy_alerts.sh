#!/usr/bin/env bash
# Deploy the four alert functions. Run `supabase login` first (it needs a
# browser, so it cannot be scripted).
set -euo pipefail
cd "$(dirname "$0")/.."

supabase link --project-ref efiyeiwdywodjxxnslvu 2>/dev/null || true

for fn in momentum-signal canada-momentum-signal germany-momentum-signal btc-signal; do
  echo "==> $fn"
  supabase functions deploy "$fn" --project-ref efiyeiwdywodjxxnslvu
done

echo
echo "Deployed. Two steps left:"
echo "  1. Run supabase/migrations/20260918_momentum_alert_crons.sql in the SQL editor"
echo "     (nothing to edit -- it reads the bearer token off the BTC cron job)."
echo "  2. Smoke-test each one; ?test=1 sends to the admin chat only and writes nothing:"
echo
for fn in momentum-signal canada-momentum-signal germany-momentum-signal btc-signal; do
  echo "     curl -s -H \"Authorization: Bearer \$CRON_SECRET\" \\"
  echo "       'https://efiyeiwdywodjxxnslvu.supabase.co/functions/v1/$fn?test=1'"
done

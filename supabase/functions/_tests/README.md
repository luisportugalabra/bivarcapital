# Alert tests

Run from `supabase/functions/_tests/`.

```bash
# decision logic: month-ends on weekends, cash regimes, missing lock-in,
# the fallback window, and the displayed-date holiday guard
deno run --allow-net --allow-read --allow-env scenarios.ts
deno run --allow-net --allow-read --allow-env dates.ts

# end-to-end: runs the real handler against the working tree's portfolio
# JSONs and sends to the admin chat only. Touches no database and no repo.
CRON_SECRET=localtest LOCAL_PORTFOLIO_DIR="$HOME/bivarcapital" \
  deno run --allow-net --allow-read --allow-env live_send.ts

# BTC, same idea (dummy key is never used -- test mode skips the DB)
cd .. && CRON_SECRET=localtest SUPABASE_SERVICE_ROLE_KEY=dummy \
  deno run --allow-net --allow-env --allow-read btc-signal/index.ts &
curl -s -H "Authorization: Bearer localtest" "http://localhost:8000/?test=1"
```

`LOCAL_PORTFOLIO_DIR` is the only difference between a local run and production:
unset, the handler reads the portfolio JSONs from GitHub raw as it does when
deployed.

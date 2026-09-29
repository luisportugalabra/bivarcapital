-- Subscriber table for the new momentum bot (@BivarMomentumBot), separate
-- from `telegram_subscribers` which now belongs exclusively to the BTC bot
-- (@Bivarbtcbot). Same shape, so momentum-webhook and _shared/momentum.ts
-- can reuse the exact logic of telegram-webhook / btc-signal.

create table if not exists momentum_subscribers (
  id bigint generated always as identity primary key,
  chat_id bigint not null unique,
  username text,
  first_name text,
  status text not null default 'pending',
  created_at timestamptz not null default now()
);

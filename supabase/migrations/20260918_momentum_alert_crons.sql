-- Monthly momentum alerts (USA / Canada / Germany) on pg_cron.
--
-- Why daily rather than monthly: the edge function decides whether to send by
-- reading `pending_signal` out of the published portfolio, which the signal job
-- writes on the real last trading day of the month. The schedule therefore only
-- has to be "often enough, early enough" -- it never has to know which calendar
-- day the rebalance lands on, so month-ends on weekends and exchange holidays
-- need no special casing and a skipped run just sends on the next one.
--
-- The 04:00-06:00 UTC window replaces the old 00:10 UTC slot, which raced the
-- 23:00 UTC GitHub Actions signal job: at 00:10 the portfolio JSON may not have
-- been published yet. By 04:00 it has, and 04:00-06:00 is still ahead of the
-- earliest of the three opens (XETRA, 07:00 UTC in summer). Five runs give four
-- retries; once a message goes out the rest no-op on the month check in
-- momentum_signal_state.
--
-- Nothing here needs editing and no secret is handled: the command is copied
-- verbatim off the working btc-signal job with only the function name swapped.

begin;

do $$
declare
  tmpl text;
  fn   text;
  j    record;
  n    int;
begin
  select command into tmpl from cron.job where jobname = 'btc-signal-daily' limit 1;
  if tmpl is null then
    raise exception 'no btc-signal-daily job to copy the auth header from';
  end if;

  -- The swap must hit exactly one place: the URL path.
  select count(*) into n from regexp_matches(tmpl, 'functions/v1/btc-signal', 'g');
  if n <> 1 then
    raise exception 'expected exactly 1 occurrence of functions/v1/btc-signal, found %', n;
  end if;

  -- Clear any existing momentum schedule (this also removes the dead
  -- uk-momentum-signal job, whose function no longer exists, and the old
  -- momentum-signal-daily-test / canada-momentum-signal-daily 00:10 slots).
  for j in
    select jobname from cron.job where command like '%functions/v1/%momentum-signal%'
  loop
    perform cron.unschedule(j.jobname);
    raise notice 'unscheduled %', j.jobname;
  end loop;

  foreach fn in array array['momentum-signal', 'canada-momentum-signal', 'germany-momentum-signal']
  loop
    perform cron.schedule(
      fn || '-alert',
      '*/30 4-6 * * *',
      replace(tmpl, 'functions/v1/btc-signal', 'functions/v1/' || fn));
    raise notice 'scheduled %-alert', fn;
  end loop;
end $$;

-- Seed the idempotency rows for the current month so deploying this does not
-- fire a backdated alert for a rebalance that already happened. The table
-- carries CHECK (id IN (1,2,3)): 1 = USA, 2 = Germany (reusing the row the
-- retired UK sleeve held), 3 = Canada.
insert into momentum_signal_state (id, month, updated)
values (1, to_char(now(), 'YYYY-MM'), now()),
       (2, to_char(now(), 'YYYY-MM'), now()),
       (3, to_char(now(), 'YYYY-MM'), now())
on conflict (id) do update set month = excluded.month, updated = excluded.updated;

commit;

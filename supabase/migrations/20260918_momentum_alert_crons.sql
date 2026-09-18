-- Monthly momentum alerts (USA / Canada / Germany) on pg_cron.
--
-- Why daily rather than monthly: the edge function decides whether to send by
-- reading `pending_signal` out of the published portfolio, which the signal job
-- writes on the real last trading day of the month. The schedule therefore only
-- has to be "often enough, early enough" -- it never has to know which calendar
-- day the rebalance lands on, so month-ends on weekends and exchange holidays
-- need no special casing and a skipped run just sends on the next one.
--
-- The 04:00-06:00 UTC window sits after the 23:00 UTC signal job has published
-- and before the earliest open of the three (XETRA, 07:00 UTC in summer).
-- Five runs give four retries; once a message goes out the rest no-op on the
-- month check in momentum_signal_state.
--
-- Nothing in here needs editing: the bearer token is lifted out of the existing
-- BTC cron job rather than pasted in, so the secret is never handled by hand.

begin;

do $$
declare
  auth   text;
  fn     text;
  base   text := 'https://efiyeiwdywodjxxnslvu.supabase.co/functions/v1/';
  j      record;
begin
  -- 1. Reuse the Authorization header the working BTC job already carries.
  select (regexp_match(command, '''(Bearer [^'']+)'''))[1]
    into auth
    from cron.job
   where command like '%btc-signal%'
   limit 1;

  if auth is null then
    raise exception 'could not read the bearer token from the btc-signal cron job '
                    '-- check: select jobname, command from cron.job;';
  end if;

  -- 2. Drop any existing schedule pointing at the momentum alert functions, so
  --    this is idempotent and clears the old monthly-only jobs without needing
  --    to know their names.
  for j in
    select jobname from cron.job
     where command like '%momentum-signal%'
        or command like '%canada-momentum-signal%'
        or command like '%germany-momentum-signal%'
        or command like '%uk-momentum-signal%'
  loop
    perform cron.unschedule(j.jobname);
    raise notice 'unscheduled %', j.jobname;
  end loop;

  -- 3. One independent job per strategy, so a failure in one cannot stop the
  --    others.
  foreach fn in array array['momentum-signal', 'canada-momentum-signal', 'germany-momentum-signal']
  loop
    perform cron.schedule(
      fn || '-alert',
      '*/30 4-6 * * *',
      format(
        $q$select net.http_post(
              url    := %L,
              headers:= jsonb_build_object('Content-Type', 'application/json',
                                           'Authorization', %L),
              timeout_milliseconds := 30000
            );$q$,
        base || fn, auth)
    );
    raise notice 'scheduled %-alert', fn;
  end loop;
end $$;

-- 4. Seed the idempotency rows for the current month so deploying this does not
--    fire a backdated alert for a rebalance that already happened. Germany
--    (id 4) has no row yet; USA (1) and Canada (3) may already.
insert into momentum_signal_state (id, month, updated)
values (1, to_char(now(), 'YYYY-MM'), now()),
       (3, to_char(now(), 'YYYY-MM'), now()),
       (4, to_char(now(), 'YYYY-MM'), now())
on conflict (id) do update set month = excluded.month, updated = excluded.updated;

commit;

-- Verify:
--   select jobname, schedule, active from cron.job order by jobname;
--   select id, month, updated from momentum_signal_state order by id;

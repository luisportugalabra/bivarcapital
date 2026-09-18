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

begin;

-- 1. Secrets. Replace the placeholder once, here, before running.
--    (Skip this block if vault already holds these from the BTC setup.)
select vault.create_secret('REPLACE_WITH_CRON_SECRET', 'cron_secret', 'Bearer token for scheduled edge functions')
where not exists (select 1 from vault.decrypted_secrets where name = 'cron_secret');

-- 2. Drop any existing schedule pointing at the momentum alert functions, so
--    this migration is idempotent and clears out the old monthly-only jobs
--    without needing to know what they were named.
do $$
declare j record;
begin
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
end $$;

-- 3. Reschedule, one independent job per strategy, so a failure in one cannot
--    stop the others.
do $$
declare
  secret text := (select decrypted_secret from vault.decrypted_secrets where name = 'cron_secret');
  fn     text;
  base   text := 'https://efiyeiwdywodjxxnslvu.supabase.co/functions/v1/';
begin
  if secret is null then
    raise exception 'vault secret cron_secret is missing -- set it in step 1 first';
  end if;

  foreach fn in array array['momentum-signal', 'canada-momentum-signal', 'germany-momentum-signal']
  loop
    perform cron.schedule(
      fn || '-alert',
      '*/30 4-6 * * *',
      format(
        $q$select net.http_post(
              url    := %L,
              headers:= jsonb_build_object(
                          'Content-Type',  'application/json',
                          'Authorization', %L),
              timeout_milliseconds := 30000
            );$q$,
        base || fn, 'Bearer ' || secret)
    );
  end loop;
end $$;

commit;

-- 4. Seed the idempotency rows for the current month so deploying this does not
--    fire a backdated alert for a rebalance that already happened. Germany
--    (id 4) has no row yet; USA (1) and Canada (3) may already.
insert into momentum_signal_state (id, month, updated)
values (1, to_char(now(), 'YYYY-MM'), now()),
       (3, to_char(now(), 'YYYY-MM'), now()),
       (4, to_char(now(), 'YYYY-MM'), now())
on conflict (id) do update set month = excluded.month, updated = excluded.updated;

-- Verify:
--   select jobname, schedule, active from cron.job order by jobname;
--   select * from momentum_signal_state order by id;

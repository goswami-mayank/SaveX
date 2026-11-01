begin;
-- Run in Supabase SQL Editor. Transactional, preserves existing profiles and SMS history.
create table if not exists public.users (
 id uuid primary key references auth.users(id) on delete cascade,
 name text, whatsapp_number text,
 created_at timestamptz not null default now(),
 constraint users_whatsapp_format check (whatsapp_number is null or whatsapp_number ~ '^\+[1-9][0-9]{7,14}$')
);
do $$ begin
 if to_regclass('public.profiles') is not null then
  execute $profile$
    insert into public.users(id,name,whatsapp_number,created_at)
    select id,name,case when phone ~ '^\+[1-9][0-9]{7,14}$' then phone else null end,created_at
    from public.profiles on conflict(id) do nothing
  $profile$;
 end if;
end $$;
-- Ensure existing Supabase Auth accounts without a legacy profile have a user row.
insert into public.users(id,name,whatsapp_number)
select id, raw_user_meta_data->>'name',
 case when (raw_user_meta_data->>'phone') ~ '^\+[1-9][0-9]{7,14}$' then raw_user_meta_data->>'phone' else null end
from auth.users on conflict(id) do nothing;
create table if not exists public.items (
 id bigint generated always as identity primary key,
 user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 name text not null check(length(trim(name)) between 1 and 200),
 bought_date date not null, shelf_days integer not null check(shelf_days between 0 and 3650),
 expiry_date date not null, location text not null check(location in ('fridge','freezer','pantry','other')),
 constraint items_expiry_matches_shelf check (expiry_date = bought_date + shelf_days),
 status text not null default 'active' check(status in ('active','used','expired')),
 created_at timestamptz not null default now()
);
create table if not exists public.alerts_log (
 id bigint generated always as identity primary key,
 user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 item_id bigint not null references public.items(id) on delete cascade,
 level text not null check(level in ('slight','moderate','high')),
 channel text not null, message text,
 sent_at timestamptz not null default now(), is_read boolean not null default false
);
-- Upgrade alert tables from the PDF schema while preserving historical records.
alter table public.alerts_log add column if not exists user_id uuid;
alter table public.alerts_log add column if not exists message text;
update public.alerts_log a set user_id=i.user_id from public.items i where a.item_id=i.id and a.user_id is null;
alter table public.alerts_log alter column user_id set default auth.uid();
alter table public.alerts_log alter column user_id set not null;
do $$ begin
 if not exists(select 1 from pg_constraint where conrelid='public.alerts_log'::regclass and conname='alerts_log_domain_user_fk') then
  alter table public.alerts_log add constraint alerts_log_domain_user_fk foreign key(user_id) references public.users(id) on delete cascade not valid;
 end if;
 if not exists(select 1 from pg_constraint where conrelid='public.items'::regclass and conname='items_expiry_matches_shelf') then
  alter table public.items add constraint items_expiry_matches_shelf check(expiry_date=bought_date+shelf_days) not valid;
 end if;
end $$;
alter table public.alerts_log drop constraint if exists alerts_log_channel_check;
alter table public.alerts_log add constraint alerts_log_channel_check check(channel in ('app','whatsapp','sms','call_mock'));
alter table public.alerts_log add column if not exists delivery_status text not null default 'sent' check(delivery_status in ('pending','sent','failed','unknown'));
-- Existing item ownership references auth.users. Add the domain users relationship too.
do $$ begin
 if not exists(select 1 from pg_constraint where conrelid='public.items'::regclass and conname='items_domain_user_fk') then
  alter table public.items add constraint items_domain_user_fk foreign key(user_id) references public.users(id) on delete cascade not valid;
 end if;
end $$;
create index if not exists items_user_expiry_idx on public.items(user_id,status,expiry_date);
create index if not exists alerts_user_sent_idx on public.alerts_log(user_id,sent_at desc);
alter table public.users enable row level security;
alter table public.items enable row level security;
alter table public.alerts_log enable row level security;
drop policy if exists "own user" on public.users;
create policy "own user" on public.users for all to authenticated using(auth.uid()=id) with check(auth.uid()=id);
drop policy if exists "own items" on public.items;
create policy "own items" on public.items for all to authenticated using(auth.uid()=user_id) with check(auth.uid()=user_id);
drop policy if exists "own alerts" on public.alerts_log;
create policy "own alerts" on public.alerts_log for all to authenticated using(auth.uid()=user_id) with check(auth.uid()=user_id and exists(select 1 from public.items where id=item_id and user_id=auth.uid()));
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path=public as $$
begin
 insert into public.users(id,name,whatsapp_number) values(new.id,new.raw_user_meta_data->>'name',new.raw_user_meta_data->>'phone') on conflict(id) do nothing;
 return new;
end; $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();
grant select,insert,update,delete on public.users,public.items,public.alerts_log to authenticated;
grant usage,select on all sequences in schema public to authenticated;
-- Household objects carry location/category and an observation time, without food expiry.
create table if not exists public.household_items (
 id bigint generated always as identity primary key,
 user_id uuid not null default auth.uid() references public.users(id) on delete cascade,
 name text not null check(length(trim(name)) between 1 and 200),
 category text not null check(length(trim(category)) between 1 and 100),
 location text not null check(length(trim(location)) between 1 and 200),
 recorded_at timestamptz not null default now(),
 created_at timestamptz not null default now()
);
create index if not exists household_user_recorded_idx on public.household_items(user_id,recorded_at desc);
alter table public.household_items enable row level security;
drop policy if exists "own household items" on public.household_items;
create policy "own household items" on public.household_items for all to authenticated using(auth.uid()=user_id) with check(auth.uid()=user_id);
grant select,insert,update,delete on public.household_items to authenticated;
grant usage,select on all sequences in schema public to authenticated;
-- Refresh Supabase REST schema cache after the transaction commits.

-- Notification queue migration, also available separately under migrations/.
-- Persistent scheduled alerts; historical alert rows remain unchanged.
create table if not exists public.notification_jobs (
 id bigint generated always as identity primary key,
 user_id uuid not null references public.users(id) on delete cascade,
 item_id bigint not null references public.items(id) on delete cascade,
 expiry_snapshot date not null,
 local_day date not null,
 slot smallint not null check(slot between 1 and 4),
 channel text not null check(channel in ('app','sms','call_mock')),
 level text not null check(level in ('slight','moderate','high')),
 scheduled_at timestamptz not null,
 status text not null default 'pending' check(status in ('pending','processing','sent','failed','unknown','skipped','cancelled')),
 claimed_at timestamptz,
 created_at timestamptz not null default now(),
 unique(item_id,expiry_snapshot,local_day,slot,channel)
);
create index if not exists notification_jobs_due_idx on public.notification_jobs(status,scheduled_at);
create index if not exists notification_jobs_user_idx on public.notification_jobs(user_id,scheduled_at desc);
alter table public.notification_jobs enable row level security;
drop policy if exists "own notification jobs" on public.notification_jobs;
create policy "own notification jobs" on public.notification_jobs for select to authenticated using(auth.uid()=user_id);
grant select on public.notification_jobs to authenticated;
grant select,insert,update,delete on public.notification_jobs to service_role;
grant usage,select on sequence public.notification_jobs_id_seq to service_role;
-- Replace the old once-per-threshold uniqueness with once-per-scheduled-job uniqueness.
alter table public.alerts_log drop constraint if exists alerts_log_item_id_level_channel_key;
drop index if exists public.alerts_log_item_level_channel_uidx;
alter table public.alerts_log add column if not exists job_id bigint references public.notification_jobs(id) on delete set null;
create unique index if not exists alerts_log_job_uidx on public.alerts_log(job_id) where job_id is not null;
alter table public.alerts_log drop constraint if exists alerts_log_channel_check;
alter table public.alerts_log add constraint alerts_log_channel_check check(channel in ('app','whatsapp','sms','call_mock'));

create or replace function public.enqueue_notification_jobs(p_now timestamptz, p_timezone text, p_user_id uuid default null)
returns integer language plpgsql security definer set search_path=public,pg_temp as $$
declare today_local date := (p_now at time zone p_timezone)::date; added integer;
begin
 update public.items set status='expired'
 where status='active' and expiry_date < today_local and (p_user_id is null or user_id=p_user_id);
 update public.notification_jobs j set status='cancelled' from public.items i
 where j.item_id=i.id and j.status='pending' and (p_user_id is null or j.user_id=p_user_id)
   and (i.status <> 'active' or i.expiry_date <> j.expiry_snapshot);
 with eligible as (
  select i.id,i.user_id,i.expiry_date,(i.expiry_date-today_local) as days,
   case when (i.expiry_date-today_local)=0 then array[9,12,16,20]
        when (i.expiry_date-today_local) between 1 and 3 then array[9,13,18]
        else array[9] end as hours
  from public.items i
  where i.status='active' and (i.expiry_date-today_local) between 0 and 7
    and (p_user_id is null or i.user_id=p_user_id)
 ), slots as (
  select e.*,s.hour,s.ordinality::smallint as slot from eligible e cross join lateral unnest(e.hours) with ordinality as s(hour,ordinality)
 ), planned as (
  select s.*,c.channel from slots s cross join (values ('app'),('sms')) as c(channel)
  union all
  select s.*,'call_mock' from slots s where s.days=0 and s.slot=1
 )
 insert into public.notification_jobs(user_id,item_id,expiry_snapshot,local_day,slot,channel,level,scheduled_at)
 select user_id,id,expiry_date,today_local,slot,channel,
   case when days<=1 then 'high' when days<=3 then 'moderate' else 'slight' end,
   (today_local::timestamp + make_interval(hours => hour)) at time zone p_timezone
 from planned on conflict(item_id,expiry_snapshot,local_day,slot,channel) do nothing;
 get diagnostics added = row_count;
 return added;
end $$;

create or replace function public.claim_notification_job(p_now timestamptz, p_sms_enabled boolean, p_user_id uuid default null)
returns setof public.notification_jobs language plpgsql security definer set search_path=public,pg_temp as $$
begin
 -- Never send a burst of missed reminders or silently retry uncertain SMS deliveries.
 update public.notification_jobs set status='skipped' where status='pending' and scheduled_at < p_now - interval '30 minutes' and (p_user_id is null or user_id=p_user_id);
 update public.notification_jobs set status=case when channel='sms' then 'unknown' else 'pending' end, claimed_at=null
 where status='processing' and claimed_at < p_now - interval '5 minutes' and (p_user_id is null or user_id=p_user_id);
 return query with candidate as (
  select j.id from public.notification_jobs j join public.items i on i.id=j.item_id
  where j.status='pending' and j.scheduled_at<=p_now and j.scheduled_at>=p_now-interval '30 minutes'
    and i.status='active' and i.expiry_date=j.expiry_snapshot
    and (p_sms_enabled or j.channel<>'sms') and (p_user_id is null or j.user_id=p_user_id)
  order by j.scheduled_at,j.id for update of j skip locked limit 1
 ) update public.notification_jobs j set status='processing',claimed_at=p_now from candidate c where j.id=c.id returning j.*;
end $$;

create or replace function public.finish_notification_job(p_job_id bigint, p_status text, p_message text)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare job public.notification_jobs%rowtype;
begin
 if p_status not in ('sent','failed','unknown','skipped') then raise exception 'Invalid status'; end if;
 update public.notification_jobs set status=p_status where id=p_job_id and status='processing' returning * into job;
 if not found then return false; end if;
 if p_status <> 'skipped' then
  insert into public.alerts_log(user_id,item_id,level,channel,message,delivery_status,job_id)
  values(job.user_id,job.item_id,job.level,job.channel,p_message,p_status,job.id)
  on conflict(job_id) where job_id is not null do nothing;
 end if;
 return true;
end $$;
revoke all on function public.enqueue_notification_jobs(timestamptz,text,uuid) from public,anon,authenticated;
revoke all on function public.claim_notification_job(timestamptz,boolean,uuid) from public,anon,authenticated;
revoke all on function public.finish_notification_job(bigint,text,text) from public,anon,authenticated;
grant execute on function public.enqueue_notification_jobs(timestamptz,text,uuid) to service_role;
grant execute on function public.claim_notification_job(timestamptz,boolean,uuid) to service_role;
grant execute on function public.finish_notification_job(bigint,text,text) to service_role;

-- Current reminder cadence.
-- Schedule the requested local-time cadence. Existing job history is preserved.
-- Reconcile pending jobs separately when upgrading an already-running queue.
create or replace function public.notification_schedule(p_start timestamptz,p_local_day date,p_expiry date,p_timezone text)
returns table(slot smallint, scheduled_at timestamptz)
language plpgsql stable set search_path=public,pg_temp as $$
declare
 days_left integer := p_expiry-p_local_day;
 day_start timestamptz := p_local_day::timestamp at time zone p_timezone;
 anchor timestamptz := greatest(p_start, day_start);
 offsets integer[];
 candidate timestamptz;
 index_no integer;
begin
 if days_left < 0 or days_left > 7 then return; end if;
 if days_left between 4 and 7 then
  slot := 1; scheduled_at := (p_local_day::timestamp + interval '10 hours') at time zone p_timezone;
  if scheduled_at >= p_start then return next; end if;
  return;
 end if;
 offsets := case when days_left=0 then array[10,60,240,720] else array[10,60,240] end;
 for index_no in 1..array_length(offsets,1) loop
  candidate := anchor + make_interval(mins => offsets[index_no]);
  if (candidate at time zone p_timezone)::date = p_local_day then
   slot := index_no::smallint; scheduled_at := candidate; return next;
  end if;
 end loop;
end $$;

create or replace function public.enqueue_notification_jobs(p_now timestamptz, p_timezone text, p_user_id uuid default null)
returns integer language plpgsql security definer set search_path=public,pg_temp as $$
declare today_local date := (p_now at time zone p_timezone)::date; added integer;
begin
 update public.items set status='expired'
 where status='active' and expiry_date < today_local and (p_user_id is null or user_id=p_user_id);
 update public.notification_jobs j set status='cancelled' from public.items i
 where j.item_id=i.id and j.status='pending' and (p_user_id is null or j.user_id=p_user_id)
   and (i.status <> 'active' or i.expiry_date <> j.expiry_snapshot);
 with slots as (
  select i.id,i.user_id,i.expiry_date,(i.expiry_date-today_local) as days,s.slot,s.scheduled_at
  from public.items i
  cross join lateral public.notification_schedule(i.created_at,today_local,i.expiry_date,p_timezone) s
  where i.status='active' and (i.expiry_date-today_local) between 0 and 7
    and (p_user_id is null or i.user_id=p_user_id)
 ), planned as (
  select s.*,c.channel from slots s cross join (values ('app'),('sms')) as c(channel)
  union all
  select s.*,'call_mock' from slots s where s.days=0 and s.slot=1
 )
 insert into public.notification_jobs(user_id,item_id,expiry_snapshot,local_day,slot,channel,level,scheduled_at)
 select user_id,id,expiry_date,today_local,slot,channel,
   case when days<=1 then 'high' when days<=3 then 'moderate' else 'slight' end,scheduled_at
 from planned on conflict(item_id,expiry_snapshot,local_day,slot,channel) do nothing;
 get diagnostics added = row_count;
 return added;
end $$;

-- No outbound delivery or table mutation is performed by this preview.
create or replace function public.preview_notification_schedule(p_start timestamptz,p_local_day date,p_expiry date,p_timezone text)
returns table(slot smallint, scheduled_at timestamptz)
language sql stable security definer set search_path=public,pg_temp as $$
 select * from public.notification_schedule(p_start,p_local_day,p_expiry,p_timezone)
$$;
revoke all on function public.notification_schedule(timestamptz,date,date,text) from public,anon,authenticated;
revoke all on function public.preview_notification_schedule(timestamptz,date,date,text) from public,anon,authenticated;
grant execute on function public.preview_notification_schedule(timestamptz,date,date,text) to service_role;

-- Preserve the original optional WhatsApp channel.
-- Preserve the original WhatsApp channel alongside the requested SMS channel.
alter table public.notification_jobs drop constraint if exists notification_jobs_channel_check;
alter table public.notification_jobs add constraint notification_jobs_channel_check check(channel in ('app','sms','whatsapp','call_mock'));
create or replace function public.enqueue_notification_jobs(p_now timestamptz, p_timezone text, p_user_id uuid default null)
returns integer language plpgsql security definer set search_path=public,pg_temp as $$
declare today_local date := (p_now at time zone p_timezone)::date; added integer;
begin
 update public.items set status='expired'
 where status='active' and expiry_date < today_local and (p_user_id is null or user_id=p_user_id);
 update public.notification_jobs j set status='cancelled' from public.items i
 where j.item_id=i.id and j.status='pending' and (p_user_id is null or j.user_id=p_user_id)
   and (i.status <> 'active' or i.expiry_date <> j.expiry_snapshot);
 with slots as (
  select i.id,i.user_id,i.expiry_date,(i.expiry_date-today_local) as days,s.slot,s.scheduled_at
  from public.items i
  cross join lateral public.notification_schedule(i.created_at,today_local,i.expiry_date,p_timezone) s
  where i.status='active' and (i.expiry_date-today_local) between 0 and 7
    and (p_user_id is null or i.user_id=p_user_id)
 ), planned as (
  select s.*,c.channel from slots s cross join (values ('app'),('sms'),('whatsapp')) as c(channel)
  union all
  select s.*,'call_mock' from slots s where s.days=0 and s.slot=1
 )
 insert into public.notification_jobs(user_id,item_id,expiry_snapshot,local_day,slot,channel,level,scheduled_at)
 select user_id,id,expiry_date,today_local,slot,channel,
   case when days<=1 then 'high' when days<=3 then 'moderate' else 'slight' end,scheduled_at
 from planned on conflict(item_id,expiry_snapshot,local_day,slot,channel) do nothing;
 get diagnostics added = row_count;
 return added;
end $$;


create or replace function public.claim_notification_job_v2(p_now timestamptz, p_sms_enabled boolean, p_user_id uuid default null, p_whatsapp_enabled boolean default false)
returns setof public.notification_jobs language plpgsql security definer set search_path=public,pg_temp as $$
begin
 -- Never send a burst of missed reminders or silently retry uncertain SMS deliveries.
 update public.notification_jobs set status='skipped' where status='pending' and scheduled_at < p_now - interval '30 minutes' and (p_user_id is null or user_id=p_user_id);
 update public.notification_jobs set status=case when channel in ('sms','whatsapp') then 'unknown' else 'pending' end, claimed_at=null
 where status='processing' and claimed_at < p_now - interval '5 minutes' and (p_user_id is null or user_id=p_user_id);
 return query with candidate as (
  select j.id from public.notification_jobs j join public.items i on i.id=j.item_id
  where j.status='pending' and j.scheduled_at<=p_now and j.scheduled_at>=p_now-interval '30 minutes'
    and i.status='active' and i.expiry_date=j.expiry_snapshot
    and (p_sms_enabled or j.channel<>'sms') and (p_whatsapp_enabled or j.channel<>'whatsapp') and (p_user_id is null or j.user_id=p_user_id)
  order by j.scheduled_at,j.id for update of j skip locked limit 1
 ) update public.notification_jobs j set status='processing',claimed_at=p_now from candidate c where j.id=c.id returning j.*;
end $$;

revoke all on function public.claim_notification_job_v2(timestamptz,boolean,uuid,boolean) from public,anon,authenticated;
grant execute on function public.claim_notification_job_v2(timestamptz,boolean,uuid,boolean) to service_role;

-- Restore unsent jobs when an item is reactivated.
-- Re-enable previously cancelled, unsent slots if an item is restored.
create or replace function public.enqueue_notification_jobs(p_now timestamptz, p_timezone text, p_user_id uuid default null)
returns integer language plpgsql security definer set search_path=public,pg_temp as $$
declare today_local date := (p_now at time zone p_timezone)::date; added integer;
begin
 update public.items set status='expired'
 where status='active' and expiry_date < today_local and (p_user_id is null or user_id=p_user_id);
 update public.notification_jobs j set status='cancelled' from public.items i
 where j.item_id=i.id and j.status='pending' and (p_user_id is null or j.user_id=p_user_id)
   and (i.status <> 'active' or i.expiry_date <> j.expiry_snapshot);
 with slots as (
  select i.id,i.user_id,i.expiry_date,(i.expiry_date-today_local) as days,s.slot,s.scheduled_at
  from public.items i
  cross join lateral public.notification_schedule(i.created_at,today_local,i.expiry_date,p_timezone) s
  where i.status='active' and (i.expiry_date-today_local) between 0 and 7
    and (p_user_id is null or i.user_id=p_user_id)
 ), planned as (
  select s.*,c.channel from slots s cross join (values ('app'),('sms'),('whatsapp')) as c(channel)
  union all
  select s.*,'call_mock' from slots s where s.days=0 and s.slot=1
 )
 insert into public.notification_jobs(user_id,item_id,expiry_snapshot,local_day,slot,channel,level,scheduled_at)
 select user_id,id,expiry_date,today_local,slot,channel,
   case when days<=1 then 'high' when days<=3 then 'moderate' else 'slight' end,scheduled_at
 from planned on conflict(item_id,expiry_snapshot,local_day,slot,channel) do update set status='pending',scheduled_at=excluded.scheduled_at where notification_jobs.status='cancelled';
 get diagnostics added = row_count;
 return added;
end $$;

notify pgrst, 'reload schema';
commit;

-- Persistent scheduled alerts; historical alert rows remain unchanged.
begin;
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
notify pgrst,'reload schema';
commit;

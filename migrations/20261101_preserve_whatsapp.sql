-- Preserve the original WhatsApp channel alongside the requested SMS channel.
begin;
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
notify pgrst,'reload schema';
commit;

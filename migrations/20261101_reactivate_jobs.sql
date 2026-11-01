-- Re-enable previously cancelled, unsent slots if an item is restored.
begin;
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

notify pgrst,'reload schema';
commit;

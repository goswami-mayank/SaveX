-- Schedule the requested local-time cadence. Existing job history is preserved.
-- Reconcile pending jobs separately when upgrading an already-running queue.
begin;
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
notify pgrst,'reload schema';
commit;

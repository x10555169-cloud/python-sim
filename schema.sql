-- =========================================================
-- Python 課堂模擬：Supabase 資料表
-- Supabase 後台 → SQL Editor → 貼上整份 → Run（重複執行也安全）
-- =========================================================

-- 1) 生產歷程事件紀錄表（欄位同老師的 Excel）
--    若老師的專案已經有 event 表，這段會自動略過
create table if not exists public.event (
  id                uuid primary key default gen_random_uuid(),
  group_id          text not null,          -- G01~G12
  product_id        text not null,          -- TEST1-P01（測試）/ P01（正式）
  station_id        text not null,          -- ST01~ST09
  part_no           text,
  wip_before_start  int,                    -- 開工瞬間齊套數（起點站 9999）
  start_time        timestamptz,
  finish_time       timestamptz,
  duration_sec      numeric,                -- Cycle Time
  wip_after_finish  int,
  status            text default 'COMPLETED'
);

-- 2) 重播用的 event 表（Python 把 Excel 逐批寫進來，模擬現場生產；不會動到正式 event）
create table if not exists public.event_replay (like public.event including all);

-- 3) Python 模擬結果（只有後端用 secret key 寫入）
create table if not exists public.sim_results (
  id          bigint generated always as identity primary key,
  run_id      text,
  tick        int,
  message     text not null,     -- 目標一：Python 送出的文字
  data        jsonb,             -- 目標二：各組分析結果
  created_at  timestamptz not null default now()
);

-- 4) 模擬狀態（只有一列 id = 1，服務重啟後用來恢復）
create table if not exists public.sim_status (
  id          int primary key default 1 check (id = 1),
  running     boolean not null default false,
  run_id      text,
  tick        int not null default 0,
  replay_pos  int not null default 0,
  started_at  timestamptz,
  message     text,
  updated_at  timestamptz not null default now()
);
alter table public.sim_status add column if not exists paused    boolean not null default false;
alter table public.sim_status add column if not exists paused_at timestamptz;
insert into public.sim_status (id) values (1) on conflict (id) do nothing;

-- ---------------------------------------------------------
-- 存取政策（RLS）
--   publishable key（網頁）：只能讀
--   secret key（Render 後端）：略過 RLS，可寫
-- ---------------------------------------------------------
alter table public.event_replay enable row level security;
alter table public.sim_results  enable row level security;
alter table public.sim_status   enable row level security;

drop policy if exists "public read" on public.event_replay;
drop policy if exists "public read" on public.sim_results;
drop policy if exists "public read" on public.sim_status;
create policy "public read" on public.event_replay for select to anon, authenticated using (true);
create policy "public read" on public.sim_results  for select to anon, authenticated using (true);
create policy "public read" on public.sim_status   for select to anon, authenticated using (true);
-- 註：正式 event 表的權限沿用老師原本的設定，這裡不更動。

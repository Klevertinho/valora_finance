create extension if not exists "pgcrypto";

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  email text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.businesses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text,
  owner_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.business_members (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'owner',
  created_at timestamptz default now(),
  unique (business_id, user_id)
);

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  type text not null check (type in ('income', 'expense')),
  description text not null,
  category text,
  amount numeric(12,2) not null,
  date date not null,
  source text,
  source_id uuid,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  name text not null,
  category text,
  quantity integer not null default 0,
  min_quantity integer not null default 0,
  cost_price numeric(12,2) not null default 0,
  sale_price numeric(12,2) not null default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.sales (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  product_id uuid references public.products(id) on delete set null,
  description text not null,
  category text,
  quantity integer not null default 1,
  amount numeric(12,2) not null,
  date date not null,
  created_at timestamptz default now()
);

create table if not exists public.daily_closings (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  date date not null,
  total_income numeric(12,2) not null default 0,
  total_expense numeric(12,2) not null default 0,
  net_result numeric(12,2) not null default 0,
  products_sold integer not null default 0,
  notes text,
  created_at timestamptz default now(),
  unique (business_id, date)
);

create table if not exists public.settings (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade unique,
  company_name text,
  business_type text,
  demo_loaded boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.profiles enable row level security;
alter table public.businesses enable row level security;
alter table public.business_members enable row level security;
alter table public.transactions enable row level security;
alter table public.products enable row level security;
alter table public.sales enable row level security;
alter table public.daily_closings enable row level security;
alter table public.settings enable row level security;

create policy "Users can read own profile" on public.profiles for select using (auth.uid() = id);
create policy "Users can update own profile" on public.profiles for update using (auth.uid() = id);
create policy "Users can insert own profile" on public.profiles for insert with check (auth.uid() = id);

create policy "Members can read businesses" on public.businesses for select using (exists (select 1 from public.business_members bm where bm.business_id = businesses.id and bm.user_id = auth.uid()));
create policy "Owners can insert businesses" on public.businesses for insert with check (owner_id = auth.uid());
create policy "Owners can update businesses" on public.businesses for update using (owner_id = auth.uid());

create policy "Members can read business members" on public.business_members for select using (exists (select 1 from public.business_members bm where bm.business_id = business_members.business_id and bm.user_id = auth.uid()));
create policy "Users can insert own membership" on public.business_members for insert with check (user_id = auth.uid());

create policy "Members can manage transactions" on public.transactions for all using (exists (select 1 from public.business_members bm where bm.business_id = transactions.business_id and bm.user_id = auth.uid())) with check (exists (select 1 from public.business_members bm where bm.business_id = transactions.business_id and bm.user_id = auth.uid()));
create policy "Members can manage products" on public.products for all using (exists (select 1 from public.business_members bm where bm.business_id = products.business_id and bm.user_id = auth.uid())) with check (exists (select 1 from public.business_members bm where bm.business_id = products.business_id and bm.user_id = auth.uid()));
create policy "Members can manage sales" on public.sales for all using (exists (select 1 from public.business_members bm where bm.business_id = sales.business_id and bm.user_id = auth.uid())) with check (exists (select 1 from public.business_members bm where bm.business_id = sales.business_id and bm.user_id = auth.uid()));
create policy "Members can manage daily closings" on public.daily_closings for all using (exists (select 1 from public.business_members bm where bm.business_id = daily_closings.business_id and bm.user_id = auth.uid())) with check (exists (select 1 from public.business_members bm where bm.business_id = daily_closings.business_id and bm.user_id = auth.uid()));
create policy "Members can manage settings" on public.settings for all using (exists (select 1 from public.business_members bm where bm.business_id = settings.business_id and bm.user_id = auth.uid())) with check (exists (select 1 from public.business_members bm where bm.business_id = settings.business_id and bm.user_id = auth.uid()));

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  email text not null unique,
  password_hash text not null,
  nama text,
  role text not null default 'user' check (role in ('user','admin'))
);

create table if not exists analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  nama text not null,
  status text not null default 'draf',
  stage text,
  config jsonb default '{}'::jsonb,
  files jsonb default '{}'::jsonb,
  stats jsonb default '{}'::jsonb,
  error text,
  log_tail text
);

create table if not exists variants (
  id bigint generated always as identity primary key,
  created_at timestamptz default now(),
  analysis_id uuid not null references analyses(id) on delete cascade,
  chrom text, posisi bigint, ref text, alt text,
  tipe text, qual real, depth int,
  gen text, efek text, impact text
);
create index if not exists variants_analysis_id_idx on variants (analysis_id);

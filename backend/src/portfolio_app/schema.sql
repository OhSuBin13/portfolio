create table if not exists schema_migrations (
  version integer primary key,
  applied_at text not null default current_timestamp
);

create table if not exists accounts (
  id integer primary key,
  name text not null,
  type text not null check (type in ('cash','savings','brokerage','debt')),
  currency text not null check (currency in ('USD','KRW')) default 'KRW',
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists assets (
  id integer primary key,
  symbol text,
  name text not null,
  type text not null check (type in ('cash','savings','stock_etf','debt')),
  currency text not null check (currency in ('USD','KRW')) default 'KRW',
  market text,
  manual_price_krw real,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create unique index if not exists idx_assets_symbol_market
on assets(symbol, market)
where symbol is not null;

create table if not exists holdings (
  id integer primary key,
  account_id integer not null references accounts(id) on delete cascade,
  asset_id integer not null references assets(id) on delete cascade,
  quantity real not null default 0,
  average_cost real,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique(account_id, asset_id)
);

create table if not exists transactions (
  id integer primary key,
  occurred_on text not null,
  type text not null check (
    type in ('deposit','withdrawal','buy','sell','dividend','interest','fee','debt_payment','adjustment')
  ),
  account_id integer references accounts(id) on delete set null,
  asset_id integer references assets(id) on delete set null,
  quantity real,
  amount real not null default 0,
  currency text not null check (currency in ('USD','KRW')) default 'KRW',
  fx_rate_to_krw real,
  memo text not null default '',
  created_at text not null default current_timestamp
);

create table if not exists price_snapshots (
  id integer primary key,
  asset_id integer not null references assets(id) on delete cascade,
  source text not null,
  price real not null,
  currency text not null check (currency in ('USD','KRW')) default 'KRW',
  price_krw real not null,
  fetched_at text not null,
  status text not null default 'ok' check (status in ('ok','stale','failed','manual')),
  error_message text not null default ''
);

create table if not exists fx_rates (
  id integer primary key,
  base_currency text not null check (base_currency in ('USD','KRW')),
  quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
  rate real not null,
  source text not null,
  fetched_at text not null,
  unique(base_currency, quote_currency, fetched_at)
);

create table if not exists goals (
  id integer primary key,
  name text not null,
  type text not null check (type in ('net_worth','monthly_income')),
  target_amount_krw real not null,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists backups (
  id integer primary key,
  path text not null,
  reason text not null,
  created_at text not null default current_timestamp
);

create table if not exists settings (
  key text primary key,
  value text not null,
  updated_at text not null default current_timestamp
);

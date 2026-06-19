create table if not exists schema_migrations (
  version integer primary key,
  applied_at text not null default current_timestamp
);

create table if not exists accounts (
  id integer primary key,
  name text not null,
  type text not null check (type in ('cash','savings','brokerage','debt')),
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

create index if not exists idx_transactions_summary_holding_fx
on transactions(account_id, asset_id, occurred_on desc, id desc)
where fx_rate_to_krw is not null;

create index if not exists idx_transactions_summary_income_month
on transactions(occurred_on, id)
where type in ('dividend', 'interest');

create index if not exists idx_transactions_summary_usd_fx
on transactions(occurred_on desc, id desc)
where currency = 'USD'
  and fx_rate_to_krw is not null
  and fx_rate_to_krw > 0;

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

create index if not exists idx_price_snapshots_summary_asset_latest
on price_snapshots(asset_id, fetched_at desc, id desc)
where status in ('ok', 'manual', 'stale');

create table if not exists fx_rates (
  id integer primary key,
  base_currency text not null check (base_currency in ('USD','KRW')),
  quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
  rate real not null,
  source text not null,
  fetched_at text not null,
  change_percent real,
  unique(base_currency, quote_currency, fetched_at)
);

create index if not exists idx_fx_rates_summary_pair_latest
on fx_rates(base_currency, quote_currency, fetched_at desc, id desc);

create table if not exists goals (
  id integer primary key,
  name text not null,
  type text not null check (type in ('net_worth','monthly_income')),
  target_amount_krw real not null check (target_amount_krw > 0),
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

create table if not exists portfolio_snapshots (
  id integer primary key,
  snapshot_date text not null unique,
  net_worth_krw real not null,
  gross_assets_krw real not null check (gross_assets_krw >= 0),
  debt_krw real not null check (debt_krw >= 0),
  monthly_income_krw real not null default 0 check (monthly_income_krw >= 0),
  asset_mix_json text not null default '{}',
  source text not null check (source in ('scheduled','manual','market_sync','import')),
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

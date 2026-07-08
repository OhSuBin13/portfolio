# Current Implementation Flow

Date: 2026-07-07
Status: Toss-based portfolio runtime with local support tables

이 문서는 현재 checkout 기준으로 애플리케이션이 어떤 기능 흐름으로 동작하는지
정리한다. 세부 Toss API 경계는 `docs/toss-open-api-integration.md`, 테이블 구조는
`docs/db_erd.md`를 함께 참고한다.

## 1. Runtime Composition

백엔드 진입점은 `backend/src/portfolio_app/main.py`의 `create_app()`이다.

앱 시작 시 다음 순서로 공통 준비가 진행된다.

1. `Settings`를 읽고 `data_dir`, `backup_dir`를 준비한다.
2. SQLite에 연결한 뒤 `migrate()`로 schema version 18까지 적용한다.
3. 기존 DB 파일이 있으면 시작 백업을 생성한다.
4. FastAPI 앱을 만들고 CORS, validation error handler, `/health`를 등록한다.
5. `app.state`에 설정, Toss 인증 클라이언트, Toss 계좌 캐시, DB 경로를 저장한다.
6. 등록된 라우터만 외부 API로 노출한다.

현재 등록된 라우터는 다음뿐이다.

| Router | Prefix | 역할 |
| --- | --- | --- |
| `summary` | `/api/summary` | 선택 Toss 계좌의 보유자산, buying power, FX를 합산한 요약 |
| `toss_portfolio` | `/api/toss` | Toss 계좌, 보유종목, buying power, 주문내역, 캔들, 차트 메모 |
| `growth_history` | `/api/growth` | 계좌별 수동 월간 성장 기록과 연간 성장 기록 |
| `goals` | `/api/goals` | 순자산/월 소득 목표 저장과 조회 |
| `backups` | `/api/backups` | SQLite 백업 파일과 메타데이터 조회 |

`accounts`, `assets`, `transactions`, `market_data` API 모듈은 제품 코드에서 제거되었다.
따라서 현재 사용자 화면의 런타임 흐름은 로컬 원장 API가 아니라 Toss 계좌 기반 API가
중심이다.

프론트엔드는 `frontend/src/App.tsx`에서 별도 URL router 없이 화면 상태를 전환한다.
`AppShell`의 현재 화면은 `dashboard`, `holdings`, `charts`, `orders`, `growth`,
`goals`, `settings`이다.

## 2. Common API Flow

프론트 공통 API helper는 `frontend/src/api.ts`에 있다.

- `VITE_API_BASE`가 있으면 그 값을 쓰고, 없으면 `http://127.0.0.1:8000`을 사용한다.
- `apiGet`, `apiPost`, `apiPut`, `apiDelete`가 FastAPI 응답의 `detail`을 사람이 읽을
  수 있는 에러 메시지로 변환한다.
- 여러 화면은 먼저 `/api/toss/accounts`로 Toss 계좌 목록을 가져오고, 선택된
  `account_seq`를 이후 요청의 기준으로 사용한다.

Toss API 인증과 rate-limit 완화는 백엔드에서 처리된다.

- `TossAuthClient`가 OAuth access token을 캐시한다.
- `TossAccountsCache`가 `/api/toss/accounts` 결과를 짧게 캐시한다.
- Toss 요청 helper는 `429` 응답을 한 번 재시도한다.
- Toss API key와 secret은 프론트로 전달하지 않는다.

## 3. Feature Flows

### Dashboard Summary

화면: `frontend/src/components/Dashboard.tsx`

주요 흐름:

1. `/api/toss/accounts`로 계좌 목록을 가져온다.
2. 선택된 `account_seq`로 `/api/summary?account_seq=...`를 호출한다.
3. 백엔드는 Toss 보유종목, KRW/USD buying power, 필요한 USD/KRW 환율을 가져온다.
4. USD 자산과 USD buying power는 같은 USD/KRW 환율로 KRW 평가액을 계산한다.
5. 순자산, 현금, 주식/ETF 비중, 자산 배분, 목표 진행률을 응답한다.

현재 brokerage slice에서는 부채와 거래 기반 월 소득을 모델링하지 않는다. 따라서
gross assets와 net worth는 같은 값이고, monthly income은 `0`으로 계산된다.

### Holdings

화면: `frontend/src/components/HoldingsPage.tsx`

주요 흐름:

1. `/api/toss/accounts`로 계좌를 선택한다.
2. 선택 계좌에 대해 `/api/toss/holdings`와 `/api/toss/buying-power`를 병렬로 호출한다.
3. 보유종목과 KRW/USD buying power를 읽기 전용으로 표시한다.

이 화면은 수기 계좌 생성, 수기 자산 생성, 거래 입력을 제공하지 않는다.

### Order History And Import

화면: `frontend/src/components/OrderHistoryPage.tsx`

주요 흐름:

1. `/api/toss/accounts`로 계좌를 선택한다.
2. 기간과 심볼 필터로 `/api/toss/orders`를 조회한다. 저장된 주문의 Toss 체결 상태는
   표에 표시하지만, 화면에서 OPEN/CLOSED import 상태 필터로 조회하지 않는다.
3. 주문 가져오기는 `/api/toss/order-imports` POST로 시작하며, 현재 화면은 `CLOSED`
   import를 요청한다.
4. 백엔드는 Toss 주문 목록 API를 cursor 기반으로 반복 호출한다.
5. 가져온 주문은 `toss_orders`에 `(account_seq, order_id)` 기준으로 upsert한다.
6. 가져오기 실행 상태는 `toss_order_import_runs`에 `running`, `success`, `failed`로 남긴다.

저장된 Toss 주문내역은 읽기 전용 캐시다. 현재 보유자산 평가나 성장 기록 계산의
원천으로 사용하지 않는다.

### Charts And Trade Markers

화면: `frontend/src/components/ChartsPage.tsx`

주요 흐름:

1. `/api/toss/accounts`로 계좌를 선택한다.
2. `/api/toss/holdings`로 선택 계좌의 보유종목을 가져온다.
3. 선택 종목에 대해 캔들, 주문내역, 차트 마커 메모를 함께 가져온다.
4. 캔들은 `/api/toss/candles?symbol=...&interval=1d&limit=1000`으로 요청한다.
5. 주문내역은 매수, 추가매수, 일부 매도 marker로 변환한다.
6. marker memo는 `/api/toss/chart-marker-memos`로 저장하거나 삭제한다.

캔들은 Toss market data에서 가져오고, marker memo만 로컬 SQLite에 저장한다.
차트 화면은 캔들 집계, 이동평균, 거래량 표시, zoom/pan 같은 화면 상태를 프론트에서
계산한다.

### Growth History

화면: `frontend/src/components/GrowthHistoryPage.tsx`

주요 흐름:

1. `/api/toss/accounts`로 계좌를 선택한다.
2. `/api/growth/month-history?account_seq=...`와 `/api/growth/annual-history?account_seq=...`
   를 읽는다.
3. 사용자가 월별 순자산과 월 배당금을 직접 저장한다.
4. 저장은 `/api/growth/month-history/{year}/{month}?account_seq=...` PUT으로 처리한다.
5. 삭제는 같은 경로의 DELETE로 처리한다.
6. "현재 순자산 채우기"는 `/api/summary`를 호출해 현재 Toss 기반 순자산을 폼에 넣는다.

월간 성장률은 직전 달 기록이 있을 때만 계산된다. 연간 성장률은 각 연도에서 마지막으로
저장된 월을 기준으로 전년 대비 값을 계산한다.

### S&P 500 Proxy

화면: `frontend/src/components/GrowthHistoryPage.tsx`

주요 흐름:

1. `sp500_proxy_prices`는 VOO 연말 가격을 저장한다.
2. fresh schema는 2021~2025 VOO 값을 seed한다.
3. 사용자는 `/api/growth/sp500-proxy-prices/{year}` PUT으로 연도별 가격을 수정할 수 있다.
4. 연간 성장 기록은 해당 연도와 전년도 VOO 가격 비율로 benchmark 수익률을 붙인다.
5. 아직 끝나지 않은 현재 연도에는 benchmark 값을 표시하지 않는다.

### Goals

화면: `frontend/src/components/GoalsPage.tsx`

주요 흐름:

1. `/api/goals` GET으로 목표 목록을 가져온다.
2. `/api/goals` POST로 목표를 생성한다.
3. 목표 타입은 `net_worth`, `monthly_income`만 허용한다.
4. 대시보드 요약에서는 현재 `PortfolioSummary` 값과 목표를 비교해 진행률을 계산한다.

목표는 로컬 SQLite에 저장된다. 목표 진행률은 저장된 목표 금액과 런타임 summary 값을
비교해 계산되므로 Toss 보유자산, buying power, FX 계산 결과에 의존한다.

### Backups And Settings

화면: `frontend/src/components/SettingsPage.tsx`

주요 흐름:

1. 앱 시작 시 DB 파일이 있으면 startup backup을 만든다.
2. lifespan task가 설정된 interval에 따라 periodic backup을 만든다.
3. `/api/backups` GET은 백업 디렉터리와 DB 기록을 reconcile한 뒤 목록을 반환한다.
4. Settings 화면은 백업 상태와 Toss API credential 설정 안내를 표시한다.

백업 파일은 서비스가 소유한 파일명 규칙을 따르며, 기록과 실제 파일 상태가 어긋나면
조회 시 정리된다.

## 4. Local Persistence Boundary

현재 fresh schema에 남는 주요 테이블은 다음이다.

- `schema_migrations`
- `settings`
- `fx_rates`
- `goals`
- `backups`
- `toss_order_import_runs`
- `toss_orders`
- `chart_marker_memos`
- `growth_month_history`
- `sp500_proxy_prices`

Toss 계좌와 Toss 보유종목은 로컬 source-of-truth 테이블로 저장하지 않는다. 읽기 시점에
Toss API에서 가져오며, 로컬 DB는 목표, 백업, 성장 기록, 주문내역 캐시, 차트 메모,
benchmark 가격처럼 앱 보조 데이터를 보관한다.

CAN SLIM 분석 기능과 cache table은 현재 구현 흐름에서 제거되었다. migration v17은
기존 DB에 남아 있을 수 있는 `canslim_cache_entries`를 drop한다.

## 5. Removed Legacy Boundary

다음 제품 코드 영역은 현재 앱에서 제거되었다.

- `/api/accounts`
- `/api/assets`
- `/api/transactions`
- `/api/market-data`
- local holdings, transactions, price snapshots, portfolio snapshots 관련 repository/service 코드
- stock metadata lookup service
- market sync scheduler

마이그레이션 코드는 오래된 SQLite 파일을 v18로 올려야 하므로 과거 로컬 원장 테이블
DDL과 drop 경로를 일부 보존한다. 테스트 fixture 역시 migration 호환성 검증을 위해
과거 테이블 정의를 포함할 수 있다. 향후 현금, 예금, 부채, 수기 조정, 거래 기반 원장
기능을 다시 도입하려면 현재 Toss-only 흐름에 단순히 연결하기보다 별도 product/schema
설계를 먼저 해야 한다.

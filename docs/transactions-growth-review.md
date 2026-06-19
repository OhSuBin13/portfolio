# 거래와 성장기록 리뷰

작성일: 2026-06-19

이 문서는 현재 포트폴리오 앱을 `transactions`와 `growth` 흐름 중심으로
검토한 결과를 정리한다. 대상은 거래 생성/검증, 보유자산 반영, 성장기록
계산, 시세 동기화 후 스냅샷 생성, 관련 프론트 화면과 테스트이다.

## 1. 요약

거래 서비스는 현재 구조가 비교적 안정적이다. `TransactionCreate`는
공유 `TransactionType`/`Currency` 타입을 사용하고, 거래 불변식은
`services/transactions.py`에서 처리된다. 매수/매도 수량, 외화 환율,
자산 유형별 허용 거래, rollback 테스트가 함께 있어 서비스 레벨 회귀망도
잘 잡혀 있다.

성장기록은 정책 결정이 더 필요하다. 특히 스냅샷이 충분하지 않은 기간을
수익률로 계산하는 방식과, market sync가 이미 존재하는 당일 스냅샷을
갱신하지 않는 정책은 실제 사용자 화면에서 오해를 만들 수 있다.

우선순위는 다음과 같다.

1. 기간 내 스냅샷이 1개뿐일 때 성장률이 왜곡된다.
2. market sync 이후 당일 성장 스냅샷 갱신 정책이 최신 평가액 기대와
   충돌할 수 있다.
3. API 레벨 테스트가 현재 `TestClient` 요청 단계에서 멈춰 회귀 검증
   신뢰도가 낮다.
4. 거래 입력 화면에서 매수/매도 외 타입의 수량 입력값이 조용히 버려진다.

## 2. 단일 스냅샷 기간의 성장률 왜곡

### 현재 동작

`backend/src/portfolio_app/services/growth.py`의 `build_growth_history()`는
기간별 스냅샷을 모은 뒤 첫 스냅샷을 시작값, 마지막 스냅샷을 종료값으로
사용한다.

```text
profit_krw = ending_net_worth_krw - starting_net_worth_krw - external_cash_flow_krw
growth_rate = profit_krw / starting_net_worth_krw
```

기간 안에 스냅샷이 하나뿐이면 시작과 종료가 같은 스냅샷이 된다. 그런데
현금흐름 조회는 `starting.snapshot_date`부터 `ending.snapshot_date + 1 day`
미만까지 포함하므로, 같은 날짜의 입출금도 기간 현금흐름으로 잡힌다.

### 재현 예시

2026-06-19에 100만 원 입금 후 같은 날 순자산 100만 원 스냅샷 하나만 있는
경우 현재 계산 결과는 다음과 같다.

```text
starting_net_worth_krw = 1,000,000
ending_net_worth_krw = 1,000,000
external_cash_flow_krw = 1,000,000
profit_krw = -1,000,000
growth_rate = -1.0
```

실제 의미는 "수익률을 계산하기에는 baseline이 부족함"에 가깝지만, 화면에는
-100% 손실처럼 보일 수 있다.

### 개선 방향

단기적으로는 기간 내 스냅샷이 2개 미만인 경우 성장률 행을 숨기거나
`growth_rate = null`로 반환하는 편이 안전하다.

정책적으로는 다음 중 하나를 선택해야 한다.

1. 일마감 스냅샷 모델
   - 스냅샷은 해당 날짜 거래가 모두 반영된 값으로 본다.
   - 현금흐름 구간은 `(starting_date, ending_date]`로 계산한다.
2. timestamp 기반 모델
   - `portfolio_snapshots`에 `snapshot_at`을 추가한다.
   - 거래와 스냅샷을 시각 기준으로 비교한다.

현재 앱이 일별 기록 중심이라면 1번이 구현 비용이 낮다.

## 3. Market sync 스냅샷 갱신 정책

### 현재 동작

`backend/src/portfolio_app/api/market_data.py`의
`sync_market_data_for_settings()`는 시세 동기화 후 다음과 같이 성장 스냅샷을
생성한다.

```python
create_or_refresh_today_snapshot(db, source="market_sync", refresh=False)
```

`backend/src/portfolio_app/services/growth.py`의
`create_or_refresh_today_snapshot()`은 같은 날짜 스냅샷이 있고
`refresh=False`이면 기존 row를 그대로 반환한다.

### 문제

오전에 사용자가 수동 스냅샷을 만들거나 자동 market sync가 stale 가격으로
스냅샷을 만든 뒤, 이후 시세 동기화가 성공해도 당일 성장기록의 순자산은
갱신되지 않는다.

대시보드 요약은 최신 `price_snapshots`를 사용할 수 있지만, 성장기록은 오래된
당일 스냅샷을 계속 보여줄 수 있다. 사용자 입장에서는 "시세 동기화 성공"과
"성장기록 최신화"가 분리되어 보이지 않기 때문에 혼란이 생길 수 있다.

### 개선 방향

스냅샷 source별 갱신 정책을 명시하는 것이 좋다.

- `manual`: 사용자가 만든 값이므로 덮어쓰기 전 확인이 필요하다.
- `import`: 가져오기 기준 스냅샷으로 보존하는 편이 안전하다.
- `market_sync`: 자동 계산 결과이므로 같은 날 재동기화 시 갱신해도 자연스럽다.
- `scheduled`: 일마감 배치인지 장중 자동 갱신인지에 따라 정책을 정한다.

단기적으로는 market sync 경로에서 `refresh=True`를 쓰거나, 기존 row의 source가
`market_sync` 또는 `scheduled`일 때만 갱신하는 방식을 검토한다.

## 4. API 테스트 실행 리스크

### 현재 증상

서비스 레벨 테스트는 통과하지만 API 레벨 테스트 일부가 현재 실행 환경에서
첫 요청 단계에 진입한 뒤 멈춘다.

재현된 명령:

```bash
timeout 20 .venv/bin/python -m pytest backend/tests/test_growth_api.py
```

결과는 5개 테스트 collect 후 첫 테스트 실행 위치에서 timeout이다.
`backend/tests/test_api.py` 일부와 `backend/tests/test_goals.py`의 단일
API 테스트도 같은 방식으로 멈췄다. 단순히 성장 API만의 문제라기보다는
현재 `TestClient`/runtime 조합 또는 app lifespan 진입 방식의 문제로 보는
편이 맞다.

### 영향

거래/성장 서비스 테스트가 충분히 있어 핵심 계산 로직은 확인할 수 있지만,
FastAPI request/response 계약과 예외 변환, OpenAPI schema 같은 API 표면의
회귀 검증 신뢰도는 낮아진다.

### 개선 방향

다음 중 하나를 별도 작업으로 확인한다.

- 테스트용 app factory에서 자동 scheduler/lifespan 의존성을 명확히 끈다.
- `TestClient(app)` 생성과 첫 요청 사이에서 멈추는 원인을 Starlette/httpx
  버전 조합까지 포함해 확인한다.
- API 테스트 fixture를 공통화해 모든 테스트가 같은 설정을 사용하게 한다.

## 5. 거래 입력 화면의 수량 필드

### 현재 동작

`frontend/src/components/TransactionsPage.tsx`는 매수/매도일 때만 수량을
payload에 넣고, 그 외 거래 타입은 `quantity = null`로 전송한다.

```text
needsQuantity = type === "buy" || type === "sell"
quantity = needsQuantity ? quantityValue : null
```

하지만 화면의 수량 입력칸은 모든 거래 타입에서 계속 편집 가능하다. 사용자가
입금, 배당, 이자, 수수료 등에 수량을 입력해도 실제 요청에서는 조용히 버려진다.

### 영향

백엔드 서비스는 매수/매도 외 거래에 수량이 들어오면 거부하므로 데이터 무결성은
지켜진다. 다만 UI에서는 사용자가 입력한 값이 저장된다고 오해할 수 있다.

### 개선 방향

거래 타입이 매수/매도가 아닐 때는 다음 중 하나를 적용한다.

- 수량 필드를 disabled 처리한다.
- 거래 타입 변경 시 수량 값을 clear 한다.
- 매수/매도 타입에서만 수량 필드를 렌더링한다.

## 6. 확인한 강점

거래 쪽에서는 다음 부분이 유지할 가치가 있다.

- 거래 타입과 통화 타입을 모델에서 공유해 API schema와 런타임 검증이 맞물린다.
- 매수/매도 외 거래의 수량 입력 금지는 서비스 레벨에서 처리된다.
- 외화 자산은 거래 통화와 자산 통화가 같아야 하고, KRW 외 통화는 환율이 필요하다.
- 자산 유형별 허용 거래가 분리되어 현금성 자산, 시장성 자산, 부채 자산의
  잘못된 거래를 막는다.
- 거래 저장 중 오류가 나면 보유자산 변경과 거래 row 저장이 함께 rollback된다.

성장기록 쪽에서는 다음 테스트가 이미 있다.

- 월간/연간 성장기록 계산
- 외부 현금흐름과 배당/이자 분리
- 부채상환을 수익에서 제외하는 계산
- USD 현금흐름의 KRW 환산
- 환율 누락/비정상 값 오류 처리
- 중간 기간이 비어 있을 때 누적 수익 계산

## 7. 검증 상태

이번 리뷰에서 확인한 명령은 다음과 같다.

```bash
.venv/bin/python -m pytest backend/tests/test_transactions.py backend/tests/test_growth.py
npm test
```

결과:

- `backend/tests/test_transactions.py backend/tests/test_growth.py`: `43 passed`
- `frontend` 정적 테스트 묶음: 통과

다음 명령은 현재 환경에서 timeout으로 완료하지 못했다.

```bash
timeout 20 .venv/bin/python -m pytest backend/tests/test_growth_api.py
```

이 문서는 구현 변경 없이 리뷰 결과와 후속 개선 후보를 기록한다.

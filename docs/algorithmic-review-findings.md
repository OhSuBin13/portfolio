# 알고리즘 검토 메모

작성일: 2026-06-19

이 문서는 현재 구현된 포트폴리오 앱의 계산 로직을 검토하면서 발견한
알고리즘상 개선 후보를 정리한다. 대상은 거래 적용, 요약 평가, 성장기록,
시세 동기화 후 스냅샷 생성 흐름이다.

## 요약

현재 거래 검증, 요약 valuation, 목표 진행률 계산의 기본 구조는 비교적
명확하다. 다만 성장기록은 "외부 현금흐름을 제외한 투자 성과"를 계산해야
하므로, 거래 모델과 스냅샷 날짜 경계가 더 엄격해야 한다.

우선순위가 높은 개선 후보는 다음 세 가지다.

1. `buy`/`sell` 거래가 현금 leg 없이 보유자산만 바꾸는 구조라 성장률 계산에서
   외부 유입과 내부 재배분을 구분하기 어렵다.
2. 성장기록의 기간 현금흐름 조회가 시작 스냅샷 날짜의 거래까지 포함해
   날짜 경계 오차가 생길 수 있다.
3. 자동 시세 동기화 후 당일 성장 스냅샷을 `refresh=false`로 만들기 때문에
   같은 날의 이후 가격 변화가 스냅샷에 반영되지 않을 수 있다.

## 1. 매수와 매도 거래의 현금흐름 모델

### 현재 동작

`backend/src/portfolio_app/services/transactions.py`의 `calculate_holding_effect()`는
거래 유형별로 하나의 `holdings` row만 갱신한다.

- `buy`: 시장성 자산 수량을 늘리고 평균단가를 갱신한다.
- `sell`: 시장성 자산 수량을 줄이고 평균단가는 유지한다.
- `deposit`, `withdrawal`, `dividend`, `interest`, `fee`: 현금성 자산 수량을 증감한다.
- `debt_payment`: 부채 자산 수량을 줄인다.

반면 `backend/src/portfolio_app/services/growth.py`의 `_period_cashflow()`는 성장률에서
제외할 외부 현금흐름으로 `deposit`, `withdrawal`, `debt_payment`만 본다. `buy`와
`sell`은 외부 현금흐름에도, 배당/이자 수익에도 포함되지 않는다.

### 문제

매수와 매도가 현금 계좌를 함께 움직이지 않기 때문에 같은 거래를 두 방식으로
기록할 수 있다.

- 현금 입금 없이 `buy`만 기록하면 순자산 증가가 투자 수익처럼 보일 수 있다.
- 먼저 `deposit`으로 현금을 넣고 `buy`를 기록하면 현금과 주식이 동시에 남아
  순자산이 이중 계상될 수 있다.
- `sell`은 주식 수량만 줄이고 현금을 늘리지 않으므로 실현 현금이 누락될 수 있다.

성장기록의 목표가 외부 유입/유출과 투자 성과를 분리하는 것이라면, 이 모델은
장기적으로 오차를 만든다.

### 개선 방향

가장 견고한 방향은 double-entry에 가깝게 거래를 모델링하는 것이다.

- `buy`: 현금성 자산 감소와 시장성 자산 증가를 한 거래 안에서 함께 기록한다.
- `sell`: 시장성 자산 감소와 현금성 자산 증가를 한 거래 안에서 함께 기록한다.
- 수수료는 별도 `fee` 또는 매수/매도 부대비용으로 명확히 분리한다.

단기적으로는 직접 매수/매도 입력을 허용할 경우 다음 정책을 명시해야 한다.

- 현금 leg가 없는 `buy`는 외부 유입으로 볼 것인지, 입력 오류로 막을 것인지 정한다.
- 현금 leg가 없는 `sell`은 외부 유출로 볼 것인지, 입력 오류로 막을 것인지 정한다.
- UI에서는 매수/매도 시 결제 현금 계좌를 필수로 받는 편이 안전하다.

## 2. 성장기록 기간 경계

### 현재 동작

`build_growth_history()`는 기간 내 스냅샷을 모은 뒤, 각 기간의 첫 스냅샷과 마지막
스냅샷을 기준으로 수익을 계산한다.

```text
profit_krw = ending_net_worth_krw - starting_net_worth_krw - external_cash_flow_krw
growth_rate = profit_krw / starting_net_worth_krw
```

현금흐름은 `_period_cashflow()`에서 다음 조건으로 조회한다.

```sql
occurred_on >= starting.snapshot_date
and occurred_on < ending.snapshot_date + 1 day
```

### 문제

스냅샷은 `snapshot_date`만 저장하고 시각을 저장하지 않는다. 따라서 시작일에
발생한 거래가 시작 스냅샷보다 전인지 후인지 알 수 없다.

예를 들어 2026-06-01 시작 스냅샷이 이미 입금 후 상태인데, 2026-06-01 `deposit`
거래까지 외부 현금흐름으로 차감하면 해당 기간 수익이 과소 계산된다. 반대로
스냅샷이 장 시작 전 상태라면 시작일 거래를 포함하는 것이 맞을 수 있다.

### 개선 방향

둘 중 하나를 명확히 선택해야 한다.

1. 날짜 기반 단순 모델을 유지한다.
   - 시작일 거래는 제외하고 `(starting_date, ending_date]` 구간만 현금흐름으로 본다.
   - 이 경우 스냅샷은 해당 날짜의 거래가 모두 반영된 일마감 상태라는 규칙을 둔다.

2. timestamp 기반 모델로 올린다.
   - `portfolio_snapshots`에 `snapshot_at`을 추가한다.
   - `transactions`에도 날짜뿐 아니라 발생 시각 또는 입력 시각 기준의 비교 축을 둔다.
   - 현금흐름 조회는 `transaction_at > starting.snapshot_at` 및
     `transaction_at <= ending.snapshot_at`으로 계산한다.

현재 앱이 일별 성장기록을 목표로 한다면 1번이 구현 비용이 낮다. 다만 자동
시세 동기화와 수동 스냅샷을 하루에 여러 번 갱신할 계획이라면 2번이 더 정확하다.

## 3. 자동 시세 동기화 후 당일 스냅샷 갱신 정책

### 현재 동작

`backend/src/portfolio_app/api/market_data.py`의 `sync_market_data_for_settings()`는
시세 동기화가 끝난 뒤 `create_or_refresh_today_snapshot()`을 호출한다.

```python
create_or_refresh_today_snapshot(db, source="market_sync", refresh=False)
```

`refresh=False`이므로 같은 날짜의 `portfolio_snapshots` row가 이미 있으면 기존
스냅샷을 그대로 반환한다.

### 문제

하루 중 첫 시세 동기화 이후 가격이 바뀌어도 당일 성장 스냅샷은 갱신되지 않는다.
대시보드 요약은 최신 `price_snapshots`를 사용할 수 있지만, 성장기록은 오래된
당일 스냅샷을 보여줄 수 있다.

이는 특히 다음 상황에서 눈에 띈다.

- 백엔드 시작 직후 자동 market sync가 실패 또는 stale 가격으로 스냅샷을 만든다.
- 이후 사용자가 수동 시세 입력 또는 성공한 market sync로 가격을 갱신한다.
- 당일 성장기록 row는 첫 스냅샷의 순자산을 계속 유지한다.

### 개선 방향

스냅샷 source별 갱신 정책을 분리하는 것이 좋다.

- `manual`: 사용자가 명시적으로 만든 값이므로 덮어쓸지 여부를 UI에서 선택하게 한다.
- future external source snapshots: 외부 데이터 반영 직후 기준 스냅샷이므로 보존하는 편이 안전하다.
- `market_sync`: 자동 계산 결과이므로 같은 날 재동기화 시 갱신해도 자연스럽다.
- `scheduled`: 일마감 배치라면 하루 한 번 고정하고, 장중 자동 갱신이라면 갱신한다.

단기 개선안은 market sync 경로에서 `refresh=True`를 사용하거나, 기존 row의 source가
`market_sync` 또는 `scheduled`일 때만 갱신하는 것이다. 후자가 수동 스냅샷 보존과
자동 최신화 사이의 균형이 좋다.

## 검증 상태

다음 범위는 확인했다.

```bash
.venv/bin/python -m pytest backend/tests/test_growth.py -q
```

결과: `13 passed`

`backend/tests/test_summary.py`, `backend/tests/test_market_data.py`,
`backend/tests/test_transactions.py`, `backend/tests/test_goals.py`를 함께 실행한 묶음은
장시간 대기 상태가 되어 중단했다. 따라서 이 문서는 "현재 테스트가 깨지는 버그"보다
"현재 테스트가 충분히 표현하지 못하는 알고리즘 의미와 정책 리스크"에 초점을 둔다.

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/SettingsPage.tsx", import.meta.url), "utf8")
const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const removedStatusPath = "/api/market-data/" + "status"

assert.ok(source.includes("Toss API 인증 정보"), "Settings page should explain Toss credentials are required")
assert.ok(source.includes("자동 백업"), "Settings page should describe backend automatic backups")
assert.ok(source.includes('"/api/backups"'), "Settings page should still read backup records")
assert.match(
  typesSource,
  /reason:\s*"startup"\s*\|\s*"automatic"\s*\|\s*"manual"/,
  "Frontend backup records should type the backend backup reason enum",
)

assert.ok(!source.includes(removedStatusPath), "Settings page should not read removed market status")
assert.ok(!source.includes("MARKET_STATUS_POLL_INTERVAL_MS"), "Settings page should remove market status polling")
assert.ok(!source.includes("window.setInterval"), "Settings page should not poll removed status")
assert.ok(!source.includes("window.clearInterval"), "Settings page should not clean up removed polling")
assert.ok(!source.includes("시세 상태"), "Settings page should not render the removed market status table")
assert.ok(!source.includes("MarketDataStatus"), "Settings page should not import removed market status types")
assert.ok(!source.includes("Alpha Vantage"), "Settings page should not show removed Alpha Vantage settings")
assert.ok(!source.includes("alphaVantage"), "Settings page should not keep Alpha Vantage state")
assert.ok(!source.includes("apiPost"), "Settings page should not post manual actions")
assert.ok(!source.includes('"/api/market-data/sync"'), "Settings page should not call manual market sync")
assert.ok(!source.includes("handleSync"), "Settings page should not keep the manual sync handler")
assert.ok(!source.includes("handleRefresh"), "Settings page should not keep the manual status refresh handler")
assert.ok(!source.includes("handleBackup"), "Settings page should not keep the manual backup handler")
assert.ok(!source.includes("syncResult"), "Settings page should not keep manual sync result state")
assert.ok(!source.includes("isSyncing"), "Settings page should not keep manual syncing state")
assert.ok(!source.includes("isRefreshing"), "Settings page should not keep manual refresh state")
assert.ok(!source.includes("isBackingUp"), "Settings page should not keep manual backup state")
assert.ok(!source.includes("상태 새로고침"), "Settings page should not show a manual status refresh button")
assert.ok(!source.includes("수동 백업 만들기"), "Settings page should not show a manual backup button")
assert.ok(!source.includes("시세 동기화를 완료했습니다"), "Settings page should not show manual sync results")

assert.ok(!typesSource.includes("MarketSnapshotStatus"), "Removed market snapshot status type should be gone")
assert.ok(!typesSource.includes("MarketDataStatus"), "Removed market status type should be gone")
assert.ok(!typesSource.includes("MarketSyncRow"), "Unused manual sync row type should be removed")
assert.ok(!typesSource.includes("MarketSyncResult"), "Unused manual sync result type should be removed")

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/SettingsPage.tsx", import.meta.url), "utf8")
const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")

assert.ok(source.includes("자동 시세 갱신"), "Settings page should describe backend automatic market sync")
assert.ok(source.includes("5분마다"), "Settings page should surface the default polling interval")
assert.ok(source.includes('"/api/market-data/status"'), "Settings page should still read market data status")
assert.ok(source.includes("MARKET_STATUS_POLL_INTERVAL_MS = 60_000"), "Settings page should poll status every 60 seconds")
assert.ok(source.includes("window.setInterval"), "Settings page should automatically poll market status")
assert.ok(source.includes("window.clearInterval"), "Settings page should clean up status polling")
assert.ok(source.includes("자동 백업"), "Settings page should describe backend automatic backups")
assert.ok(source.includes('"/api/backups"'), "Settings page should still read backup records")

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

assert.ok(
  typesSource.includes('export type MarketSnapshotStatus = "ok" | "stale" | "failed" | "manual"'),
  "Frontend should constrain market snapshot statuses",
)
assert.ok(
  typesSource.includes("status: MarketSnapshotStatus"),
  "MarketDataStatus should use the constrained status union",
)
assert.ok(!typesSource.includes("MarketSyncRow"), "Unused manual sync row type should be removed")
assert.ok(!typesSource.includes("MarketSyncResult"), "Unused manual sync result type should be removed")

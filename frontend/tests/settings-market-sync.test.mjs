import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/SettingsPage.tsx", import.meta.url), "utf8")

assert.ok(source.includes("자동 시세 갱신"), "Settings page should describe backend automatic market sync")
assert.ok(source.includes("5분마다"), "Settings page should surface the default polling interval")
assert.ok(source.includes('"/api/market-data/status"'), "Settings page should still read market data status")

assert.ok(!source.includes('"/api/market-data/sync"'), "Settings page should not call manual market sync")
assert.ok(!source.includes("handleSync"), "Settings page should not keep the manual sync handler")
assert.ok(!source.includes("syncResult"), "Settings page should not keep manual sync result state")
assert.ok(!source.includes("isSyncing"), "Settings page should not keep manual syncing state")
assert.ok(!source.includes("시세 동기화를 완료했습니다"), "Settings page should not show manual sync results")

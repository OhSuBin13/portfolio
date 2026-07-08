import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(
  new URL("../src/components/OrderImportRunSummary.tsx", import.meta.url),
  "utf8",
)
const pageSource = readFileSync(new URL("../src/components/OrderHistoryPage.tsx", import.meta.url), "utf8")

assert.ok(source.includes("export function OrderImportRunSummary"), "Import-run summary should be a named export")
assert.ok(source.includes("latestImportRun"), "Import-run summary should receive the latest run")
assert.ok(source.includes("formatDateTime(latestImportRun.started_at)"), "Import-run summary should format start time")
assert.ok(source.includes("formatDateTime(latestImportRun.completed_at)"), "Import-run summary should format completion time")
assert.ok(source.includes("latestImportRun.error_message"), "Import-run summary should render import errors")
assert.ok(source.includes("가져오기 이력이 없습니다."), "Import-run summary should own the empty state")
assert.ok(
  pageSource.includes('from "./OrderImportRunSummary"'),
  "OrderHistoryPage should import the extracted import-run summary",
)
assert.ok(
  !pageSource.includes("latestImportRun.run_status"),
  "OrderHistoryPage should not keep import-run detail markup inline",
)

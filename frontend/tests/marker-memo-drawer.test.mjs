import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(
  new URL("../src/components/MarkerMemoDrawer.tsx", import.meta.url),
  "utf8",
)
const chartsPageSource = readFileSync(
  new URL("../src/components/ChartsPage.tsx", import.meta.url),
  "utf8",
)

assert.ok(source.includes("export function MarkerMemoDrawer"), "Marker memo drawer should be a named export")
assert.ok(source.includes("memoListExpanded"), "Marker memo drawer should receive expanded state")
assert.ok(source.includes("memoManageMode"), "Marker memo drawer should receive manage-mode state")
assert.ok(source.includes("memoMarkers.map((marker) =>"), "Marker memo drawer should render written memo rows")
assert.ok(source.includes("onToggleMemoListExpanded"), "Marker memo drawer should receive the expand toggle")
assert.ok(source.includes("onToggleMemoManageMode"), "Marker memo drawer should receive the manage-mode toggle")
assert.ok(source.includes("onOpenMarkerMemoDialog"), "Marker memo drawer should receive the compose action")
assert.ok(source.includes("onOpenMarkerMemoDetail"), "Marker memo drawer should receive row open action")
assert.ok(source.includes("onDeleteMarkerMemo"), "Marker memo drawer should receive delete action")
assert.ok(source.includes("<Plus size={17} />"), "Marker memo drawer should render the compose icon")
assert.ok(source.includes("<X size={15} />"), "Marker memo drawer should render delete icons")
assert.ok(
  chartsPageSource.includes('from "./MarkerMemoDrawer"'),
  "ChartsPage should import the extracted marker memo drawer",
)
assert.ok(
  !chartsPageSource.includes('className="marker-memo-drawer"'),
  "ChartsPage should not keep marker memo drawer markup inline",
)

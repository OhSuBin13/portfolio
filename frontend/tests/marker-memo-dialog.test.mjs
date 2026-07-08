import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(
  new URL("../src/components/MarkerMemoDialog.tsx", import.meta.url),
  "utf8",
)
const chartsPageSource = readFileSync(
  new URL("../src/components/ChartsPage.tsx", import.meta.url),
  "utf8",
)

assert.ok(source.includes("export function MarkerMemoDialog"), "Marker memo dialog should be a named export")
assert.ok(source.includes("selectedMarker"), "Marker memo dialog should receive the selected marker")
assert.ok(source.includes("markerMemoDraft"), "Marker memo dialog should receive the draft text")
assert.ok(source.includes("memoSaving"), "Marker memo dialog should receive the saving state")
assert.ok(source.includes("formatPrice"), "Marker memo dialog should receive the price formatter")
assert.ok(source.includes("onClose"), "Marker memo dialog should receive an explicit close callback")
assert.ok(source.includes("onDraftChange"), "Marker memo dialog should receive draft updates")
assert.ok(source.includes("onSave"), "Marker memo dialog should receive the save action")
assert.ok(source.includes("<Calendar size={18} />"), "Marker memo dialog should render the date detail icon")
assert.ok(source.includes("<Save size={16} />"), "Marker memo dialog should render the save icon")
assert.ok(
  chartsPageSource.includes('from "./MarkerMemoDialog"'),
  "ChartsPage should import the extracted marker memo dialog",
)
assert.ok(
  !chartsPageSource.includes('className="panel marker-memo-dialog"'),
  "ChartsPage should not keep marker memo dialog markup inline",
)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(
  new URL("../src/components/ChartSettingsDialog.tsx", import.meta.url),
  "utf8",
)
const chartsPageSource = readFileSync(
  new URL("../src/components/ChartsPage.tsx", import.meta.url),
  "utf8",
)

assert.ok(source.includes("export type MovingAverageForm"), "Moving average form type should move with the dialog")
assert.ok(source.includes("export function ChartSettingsDialog"), "Chart settings dialog should be a named export")
assert.ok(source.includes("onClose"), "Chart settings dialog should receive an explicit close callback")
assert.ok(source.includes("onBackdropMouseDown"), "Chart settings dialog should own backdrop click handling")
assert.ok(source.includes("onAddMovingAverage"), "Chart settings dialog should receive the add action")
assert.ok(source.includes("onRemoveMovingAverage"), "Chart settings dialog should receive the remove action")
assert.ok(source.includes("onMovingAverageFormChange"), "Chart settings dialog should receive form updates")
assert.ok(source.includes("onShowVolumeChange"), "Chart settings dialog should receive volume visibility updates")
assert.ok(source.includes("<Plus size={16} />"), "Chart settings dialog should render the add icon")
assert.ok(source.includes("<Trash2 size={16} />"), "Chart settings dialog should render delete icons")
assert.ok(
  chartsPageSource.includes('from "./ChartSettingsDialog"'),
  "ChartsPage should import the extracted chart settings dialog",
)
assert.ok(
  !chartsPageSource.includes('className="panel chart-settings-panel chart-settings-dialog"'),
  "ChartsPage should not keep the chart settings dialog markup inline",
)

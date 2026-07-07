import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")

const navIds = [...shellSource.matchAll(/id: "([^"]+)"/g)].map((match) => match[1])
assert.deepEqual(
  navIds,
  ["dashboard", "holdings", "charts", "orders", "growth", "goals", "settings"],
  "Navigation should expose only the core portfolio screens",
)

for (const screenId of navIds) {
  assert.ok(
    appSource.includes(`active === "${screenId}"`),
    `App should render the ${screenId} screen`,
  )
}

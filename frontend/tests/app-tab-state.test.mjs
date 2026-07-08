import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")

for (const screen of ["holdings", "charts", "orders", "growth", "goals", "settings"]) {
  const stateName = `${screen}Mounted`

  assert.ok(
    appSource.includes(stateName),
    `App should remember when the ${screen} screen has been mounted`,
  )
  assert.ok(
    appSource.includes(`screen === "${screen}"`),
    `App navigation should mark the ${screen} screen as mounted`,
  )
  assert.ok(
    appSource.includes(`hidden={active !== "${screen}"}`),
    `App should hide rather than unmount the ${screen} screen after first visit`,
  )
  assert.ok(
    appSource.includes(`active === "${screen}" || ${stateName}`),
    `App should preserve ${screen} state after navigating away`,
  )
  assert.ok(
    !appSource.includes(`{active === "${screen}" && <`),
    `App should not remount the ${screen} screen on every return`,
  )
}

assert.ok(
  appSource.includes('hidden={active !== "dashboard"}'),
  "App should keep the dashboard mounted from initial render",
)

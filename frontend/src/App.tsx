import { useState } from "react"
import { AppShell } from "./components/AppShell"
import { Dashboard } from "./components/Dashboard"
import { GoalsPage } from "./components/GoalsPage"
import { HoldingsPage } from "./components/HoldingsPage"
import { OrderHistoryPage } from "./components/OrderHistoryPage"
import { SettingsPage } from "./components/SettingsPage"

export default function App() {
  const [active, setActive] = useState("dashboard")

  return (
    <AppShell active={active} onNavigate={setActive}>
      {active === "dashboard" && <Dashboard />}
      {active === "holdings" && <HoldingsPage />}
      {active === "orders" && <OrderHistoryPage />}
      {active === "goals" && <GoalsPage />}
      {active === "settings" && <SettingsPage />}
    </AppShell>
  )
}

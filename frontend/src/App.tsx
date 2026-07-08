import { useState } from "react"
import { AppShell } from "./components/AppShell"
import { ChartsPage } from "./components/ChartsPage"
import { Dashboard } from "./components/Dashboard"
import { GoalsPage } from "./components/GoalsPage"
import { GrowthHistoryPage } from "./components/GrowthHistoryPage"
import { HoldingsPage } from "./components/HoldingsPage"
import { OrderHistoryPage } from "./components/OrderHistoryPage"
import { SettingsPage } from "./components/SettingsPage"

export default function App() {
  const [active, setActive] = useState("dashboard")
  const [chartsMounted, setChartsMounted] = useState(false)

  const navigate = (screen: string) => {
    if (screen === "charts") {
      setChartsMounted(true)
    }
    setActive(screen)
  }

  return (
    <AppShell active={active} onNavigate={navigate}>
      {active === "dashboard" && <Dashboard />}
      {active === "holdings" && <HoldingsPage />}
      {(active === "charts" || chartsMounted) && (
        <div hidden={active !== "charts"}>
          <ChartsPage />
        </div>
      )}
      {active === "orders" && <OrderHistoryPage />}
      {active === "growth" && <GrowthHistoryPage />}
      {active === "goals" && <GoalsPage />}
      {active === "settings" && <SettingsPage />}
    </AppShell>
  )
}

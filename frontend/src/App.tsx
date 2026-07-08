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
  const [holdingsMounted, setHoldingsMounted] = useState(false)
  const [chartsMounted, setChartsMounted] = useState(false)
  const [ordersMounted, setOrdersMounted] = useState(false)
  const [growthMounted, setGrowthMounted] = useState(false)
  const [goalsMounted, setGoalsMounted] = useState(false)
  const [settingsMounted, setSettingsMounted] = useState(false)

  const navigate = (screen: string) => {
    if (screen === "holdings") {
      setHoldingsMounted(true)
    }
    if (screen === "charts") {
      setChartsMounted(true)
    }
    if (screen === "orders") {
      setOrdersMounted(true)
    }
    if (screen === "growth") {
      setGrowthMounted(true)
    }
    if (screen === "goals") {
      setGoalsMounted(true)
    }
    if (screen === "settings") {
      setSettingsMounted(true)
    }
    setActive(screen)
  }

  return (
    <AppShell active={active} onNavigate={navigate}>
      <div hidden={active !== "dashboard"}>
        <Dashboard />
      </div>
      {(active === "holdings" || holdingsMounted) && (
        <div hidden={active !== "holdings"}>
          <HoldingsPage />
        </div>
      )}
      {(active === "charts" || chartsMounted) && (
        <div hidden={active !== "charts"}>
          <ChartsPage />
        </div>
      )}
      {(active === "orders" || ordersMounted) && (
        <div hidden={active !== "orders"}>
          <OrderHistoryPage />
        </div>
      )}
      {(active === "growth" || growthMounted) && (
        <div hidden={active !== "growth"}>
          <GrowthHistoryPage />
        </div>
      )}
      {(active === "goals" || goalsMounted) && (
        <div hidden={active !== "goals"}>
          <GoalsPage />
        </div>
      )}
      {(active === "settings" || settingsMounted) && (
        <div hidden={active !== "settings"}>
          <SettingsPage />
        </div>
      )}
    </AppShell>
  )
}

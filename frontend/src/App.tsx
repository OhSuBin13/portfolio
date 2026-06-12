import { useState } from "react"
import { AppShell } from "./components/AppShell"
import { Dashboard } from "./components/Dashboard"
import { GoalsPage } from "./components/GoalsPage"
import { HoldingsPage } from "./components/HoldingsPage"
import { TransactionsPage } from "./components/TransactionsPage"

export default function App() {
  const [active, setActive] = useState("dashboard")

  return (
    <AppShell active={active} onNavigate={setActive}>
      {active === "dashboard" && <Dashboard />}
      {active === "holdings" && <HoldingsPage />}
      {active === "transactions" && <TransactionsPage />}
      {active === "goals" && <GoalsPage />}
      {active === "import" && <div>가져오기</div>}
      {active === "settings" && <div>설정</div>}
    </AppShell>
  )
}

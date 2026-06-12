import { useState } from "react"
import { AppShell } from "./components/AppShell"

export default function App() {
  const [active, setActive] = useState("dashboard")

  return (
    <AppShell active={active} onNavigate={setActive}>
      <h2>{active}</h2>
    </AppShell>
  )
}

import { BarChart3, Database, Flag, History, Settings } from "lucide-react"

type Props = {
  active: string
  onNavigate: (screen: string) => void
  children: React.ReactNode
}

const navItems = [
  { id: "dashboard", label: "대시보드", icon: BarChart3 },
  { id: "holdings", label: "보유자산", icon: Database },
  { id: "transactions", label: "거래내역", icon: History },
  { id: "goals", label: "목표", icon: Flag },
  { id: "settings", label: "설정", icon: Settings },
]

export function AppShell({ active, onNavigate, children }: Props) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>개인 포트폴리오</h1>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                aria-current={active === item.id ? "page" : undefined}
                className={active === item.id ? "active" : ""}
                onClick={() => onNavigate(item.id)}
                title={item.label}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}

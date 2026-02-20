import {
  Activity,
  BookOpenText,
  GitPullRequestArrow,
  History,
  Home,
  Radar,
  Swords,
} from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

const baseItems: Item[] = [
  { icon: Home, title: "Dashboard", path: "/" },
  { icon: Swords, title: "Play", path: "/play" },
  { icon: Activity, title: "Analysis", path: "/analysis" },
  { icon: BookOpenText, title: "Openings", path: "/openings" },
  { icon: History, title: "History", path: "/history" },
  { icon: GitPullRequestArrow, title: "Matchmaking", path: "/matchmaking" },
  { icon: Radar, title: "System", path: "/system" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={baseItems} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar

import {
  Link,
  createFileRoute,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function Layout() {
  const { pathname, analysisTab } = useRouterState({
    select: (state) => {
      const tab = (state.location.search as Record<string, unknown>)?.tab
      return {
        pathname: state.location.pathname,
        analysisTab: tab === "settings" ? "settings" : "analysis",
      }
    },
  })
  const isWideChessRoute =
    pathname.startsWith("/analysis") ||
    pathname.startsWith("/play") ||
    pathname.startsWith("/openings") ||
    pathname.startsWith("/history")
  const isAnalysisRoute = pathname.startsWith("/analysis")
  const pageTitle = pathname.startsWith("/play")
    ? "Play"
    : pathname.startsWith("/openings")
      ? "Openings"
      : pathname.startsWith("/history")
        ? "History"
        : null

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
          {isAnalysisRoute ? (
            <div className="ml-2 flex min-w-0 items-center gap-3">
              <h1 className="text-lg font-semibold tracking-tight">Analysis</h1>
              <Tabs value={analysisTab} className="gap-0">
                <TabsList className="h-8">
                  <TabsTrigger value="analysis" asChild>
                    <Link to="/analysis" search={{ tab: "analysis" }}>
                      Analysis
                    </Link>
                  </TabsTrigger>
                  <TabsTrigger value="settings" asChild>
                    <Link to="/analysis" search={{ tab: "settings" }}>
                      Settings
                    </Link>
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          ) : null}
          {!isAnalysisRoute && pageTitle ? (
            <h1 className="ml-2 text-lg font-semibold tracking-tight">{pageTitle}</h1>
          ) : null}
        </header>
        <main className="flex-1 p-6 md:p-8">
          <div className={isWideChessRoute ? "w-full max-w-none" : "mx-auto max-w-7xl"}>
            <Outlet />
          </div>
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}

export default Layout

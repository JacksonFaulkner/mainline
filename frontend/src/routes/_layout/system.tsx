import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"

import { getChessHealth, getChessMe } from "@/features/chess/api"

export const Route = createFileRoute("/_layout/system")({
  component: SystemRoute,
  head: () => ({
    meta: [{ title: "System - Chess" }],
  }),
})

function SystemRoute() {
  const health = useQuery({
    queryKey: ["chess", "health"],
    queryFn: getChessHealth,
  })
  const me = useQuery({
    queryKey: ["chess", "me"],
    queryFn: getChessMe,
  })

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System</h1>
        <p className="text-muted-foreground">Backend health and account connectivity checks.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-md border p-3">
          <h2 className="mb-2 font-medium">Health</h2>
          <pre className="text-xs">
            {health.isLoading ? "Loading..." : JSON.stringify(health.data ?? health.error, null, 2)}
          </pre>
        </div>
        <div className="rounded-md border p-3">
          <h2 className="mb-2 font-medium">Account</h2>
          <pre className="text-xs">{me.isLoading ? "Loading..." : JSON.stringify(me.data ?? me.error, null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}


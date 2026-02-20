import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/matchmaking")({
  component: MatchmakingRoute,
  head: () => ({
    meta: [{ title: "Matchmaking - Chess" }],
  }),
})

function MatchmakingRoute() {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight">Matchmaking</h1>
      <p className="text-muted-foreground">
        Challenge stream and accept/decline flows will be migrated here next.
      </p>
    </div>
  )
}


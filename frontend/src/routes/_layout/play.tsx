import { useMutation } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

import {
  CHESS_WORKSPACE_BOARD_CLASS,
  ChessWorkspaceLayout,
} from "@/components/chess/ChessWorkspaceLayout"
import { FenBoard } from "@/components/chess/FenBoard"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { createSeek } from "@/features/chess/api"

export const Route = createFileRoute("/_layout/play")({
  component: PlayRoute,
  head: () => ({
    meta: [{ title: "Play - Chess" }],
  }),
})

function PlayRoute() {
  const [minutes, setMinutes] = useState(10)
  const [increment, setIncrement] = useState(5)
  const [orientation, setOrientation] = useState<"white" | "black">("white")
  const seekMutation = useMutation({
    mutationFn: () =>
      createSeek({
        minutes,
        increment,
        rated: false,
        color: "random",
        variant: "standard",
      }),
  })

  return (
    <ChessWorkspaceLayout
      board={
        <div className="w-full space-y-3">
          <FenBoard
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
            orientation={orientation}
            className={CHESS_WORKSPACE_BOARD_CLASS}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant={orientation === "white" ? "default" : "outline"}
              onClick={() => setOrientation("white")}
            >
              White on bottom
            </Button>
            <Button
              type="button"
              variant={orientation === "black" ? "default" : "outline"}
              onClick={() => setOrientation("black")}
            >
              Black on bottom
            </Button>
          </div>
        </div>
      }
      panel={
        <div className="max-w-2xl space-y-4">
          <p className="text-muted-foreground">
            Create seeks against incoming opponents on Lichess.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="text-sm">
              Minutes
              <Input
                className="mt-1"
                type="number"
                min={1}
                max={180}
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
              />
            </label>
            <label className="text-sm">
              Increment
              <Input
                className="mt-1"
                type="number"
                min={0}
                max={180}
                value={increment}
                onChange={(e) => setIncrement(Number(e.target.value))}
              />
            </label>
          </div>

          <Button
            type="button"
            onClick={() => seekMutation.mutate()}
            disabled={seekMutation.isPending}
          >
            {seekMutation.isPending ? "Creating seek..." : "Create seek"}
          </Button>

          {seekMutation.data ? (
            <pre className="overflow-x-auto rounded-md border p-3 text-xs">
              {JSON.stringify(seekMutation.data, null, 2)}
            </pre>
          ) : null}
          {seekMutation.error ? (
            <p className="text-sm text-red-500">
              {(seekMutation.error as Error).message}
            </p>
          ) : null}
        </div>
      }
    />
  )
}

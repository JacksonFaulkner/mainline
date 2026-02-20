import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useMemo } from "react"

import { DataTable } from "@/components/Common/DataTable"
import {
  CHESS_WORKSPACE_BOARD_CLASS,
  ChessWorkspaceLayout,
} from "@/components/chess/ChessWorkspaceLayout"
import { FenBoard } from "@/components/chess/FenBoard"
import { getRecentGames } from "@/features/chess/api"
import { historyColumns } from "@/features/chess/history-columns"

export const Route = createFileRoute("/_layout/history")({
  component: HistoryRoute,
  head: () => ({
    meta: [{ title: "History - Chess" }],
  }),
})

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

function HistoryRoute() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["chess", "recent-games"],
    queryFn: () => getRecentGames(15),
  })

  const featuredGame = useMemo(
    () => data?.games.find((game) => (game.preview_fens?.length ?? 0) > 0) ?? data?.games[0],
    [data?.games],
  )
  const featuredFen = useMemo(() => {
    const fens = featuredGame?.preview_fens ?? []
    return fens.length > 0 ? fens[fens.length - 1] : STARTING_FEN
  }, [featuredGame?.preview_fens])
  const featuredOrientation = featuredGame?.my_color === "black" ? "black" : "white"

  return (
    <ChessWorkspaceLayout
      board={
        <FenBoard
          fen={featuredFen}
          orientation={featuredOrientation}
          className={CHESS_WORKSPACE_BOARD_CLASS}
        />
      }
      panel={
        <div className="space-y-4">

          {isLoading ? <p>Loading games...</p> : null}
          {error ? <p className="text-sm text-red-500">{(error as Error).message}</p> : null}

          {data ? <DataTable columns={historyColumns} data={data.games} /> : null}
        </div>
      }
    />
  )
}

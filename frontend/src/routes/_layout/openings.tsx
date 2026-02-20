import { Chess } from "chess.js"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useMemo, useState } from "react"

import {
  CHESS_WORKSPACE_BOARD_CLASS,
  ChessWorkspaceLayout,
} from "@/components/chess/ChessWorkspaceLayout"
import { FenBoard } from "@/components/chess/FenBoard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { lookupOpening } from "@/features/chess/api"

export const Route = createFileRoute("/_layout/openings")({
  component: OpeningsRoute,
  head: () => ({
    meta: [{ title: "Openings - Chess" }],
  }),
})

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

type PlayedMove = {
  san: string
  uci: string
}

function toUci(from: string, to: string, promotion?: string): string {
  return `${from}${to}${promotion ?? ""}`.toLowerCase()
}

function OpeningsRoute() {
  const [fen, setFen] = useState(STARTING_FEN)
  const [moves, setMoves] = useState<PlayedMove[]>([])
  const [orientation, setOrientation] = useState<"white" | "black">("white")

  const movesUci = useMemo(() => moves.map((move) => move.uci), [moves])

  const openingQuery = useQuery({
    queryKey: ["chess", "openings", movesUci.join(" ")],
    queryFn: () =>
      lookupOpening({
        moves: movesUci,
        initialFen: STARTING_FEN,
      }),
    enabled: true,
    staleTime: 30_000,
  })

  const applyBoardMove = (sourceSquare: string, targetSquare: string | null): boolean => {
    if (!targetSquare) return false

    try {
      const chess = new Chess(fen)
      const move = chess.move({
        from: sourceSquare,
        to: targetSquare,
        promotion: "q",
      })
      if (!move) return false

      setFen(chess.fen())
      setMoves((prev) => [
        ...prev,
        {
          san: move.san,
          uci: toUci(move.from, move.to, move.promotion),
        },
      ])
      return true
    } catch {
      return false
    }
  }

  const undoMove = () => {
    if (moves.length === 0) return
    const chess = new Chess(fen)
    chess.undo()
    setFen(chess.fen())
    setMoves((prev) => prev.slice(0, -1))
  }

  const resetLine = () => {
    setFen(STARTING_FEN)
    setMoves([])
  }

  const opening = openingQuery.data?.opening
  const continuationArrows = openingQuery.data?.continuations ?? []
  const continuationMoves = useMemo(() => {
    const chess = new Chess(fen)
    return continuationArrows.map((continuation) => {
      let san = continuation.uci
      try {
        const move = chess.move({
          from: continuation.from_square,
          to: continuation.to_square,
          promotion: continuation.uci.length === 5 ? continuation.uci[4] : undefined,
        })
        if (move) {
          san = move.san
          chess.undo()
        }
      } catch {
        san = continuation.uci
      }
      return {
        ...continuation,
        san,
      }
    })
  }, [continuationArrows, fen])
  const databaseInfo = openingQuery.data?.database

  return (
    <ChessWorkspaceLayout
      board={
        <FenBoard
          fen={fen}
          orientation={orientation}
          allowDragging
          onPieceDrop={applyBoardMove}
          arrows={continuationArrows}
          className={CHESS_WORKSPACE_BOARD_CLASS}
        />
      }
      panel={
        <div className="space-y-3">
          <p className="text-muted-foreground">
            Play moves on the board and resolve the current line against the local opening database.
          </p>

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={undoMove} disabled={moves.length === 0}>
              Undo
            </Button>
            <Button type="button" variant="outline" onClick={resetLine}>
              Reset
            </Button>
            <Button
              type="button"
              variant={orientation === "white" ? "default" : "outline"}
              onClick={() => setOrientation("white")}
            >
              White bottom
            </Button>
            <Button
              type="button"
              variant={orientation === "black" ? "default" : "outline"}
              onClick={() => setOrientation("black")}
            >
              Black bottom
            </Button>
          </div>

          <div className="rounded-md border p-3">
            <h2 className="text-sm font-semibold">Opening Match</h2>
            {moves.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">
                Make moves from the starting position to detect an opening.
              </p>
            ) : openingQuery.isLoading ? (
              <p className="mt-2 text-sm text-muted-foreground">Looking up opening...</p>
            ) : openingQuery.error ? (
              <p className="mt-2 text-sm text-red-500">
                {(openingQuery.error as Error).message}
              </p>
            ) : openingQuery.data?.matched && opening ? (
              <div className="mt-2 space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{opening.eco}</Badge>
                  <span className="font-medium">{opening.name}</span>
                </div>
                <p className="text-muted-foreground">Matched at ply {opening.ply}.</p>
                {opening.pgn ? (
                  <p className="rounded-sm bg-muted px-2 py-1 font-mono text-xs">{opening.pgn}</p>
                ) : null}
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                No opening match yet for this move sequence.
              </p>
            )}
          </div>

          <div className="rounded-md border p-3">
            <h2 className="text-sm font-semibold">Next Book Moves</h2>
            {openingQuery.isLoading ? (
              <p className="mt-2 text-sm text-muted-foreground">Loading opening lines...</p>
            ) : openingQuery.error ? (
              <p className="mt-2 text-sm text-red-500">
                {(openingQuery.error as Error).message}
              </p>
            ) : continuationMoves.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">
                No continuation lines for this position.
              </p>
            ) : (
              <ol className="mt-2 space-y-1 text-sm">
                {continuationMoves.map((move) => (
                  <li key={`${move.rank}-${move.uci}`} className="flex items-center gap-2">
                    <Badge variant="outline">#{move.rank}</Badge>
                    <span className="font-mono">{move.san}</span>
                    {move.name ? <span className="text-muted-foreground">{move.name}</span> : null}
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="rounded-md border p-3">
            <h2 className="text-sm font-semibold">Moves</h2>
            {moves.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">No moves played.</p>
            ) : (
              <ol className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                {moves.map((move, index) => (
                  <li key={`${index + 1}-${move.uci}`} className="font-mono">
                    {index + 1}. {move.san}
                  </li>
                ))}
              </ol>
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            Opening data source:{" "}
            {databaseInfo
              ? databaseInfo.source === "full"
                ? `local Lichess TSV files (${databaseInfo.file_count})`
                : databaseInfo.source === "starter"
                  ? `starter fallback dataset (${databaseInfo.file_count})`
                  : "missing"
              : "loading..."}
            . Files are read from `backend/app/data/chess-openings` (or `OPENINGS_DB_DIR`).
          </p>
        </div>
      }
    />
  )
}

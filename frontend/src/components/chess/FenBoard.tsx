import { cva } from "class-variance-authority"
import { validateFen } from "chess.js"
import type { MouseEvent } from "react"
import { useCallback, useId, useMemo, useRef, useState } from "react"
import { Chessboard } from "react-chessboard"

import { colorForArrowSlot } from "@/features/chess/colors"
import { cn } from "@/lib/utils"

type ParsedFenBoard = {
  normalizedFen: string
  error: string | null
}

type FenBoardProps = {
  fen: string
  orientation?: "white" | "black"
  className?: string
  arrows?: Array<{
    from_square: string
    to_square: string
    color_slot: number
    rank?: number
    uci?: string
    cp?: number | null
    mate?: number | null
  }>
  allowDragging?: boolean
  allowDrawingArrows?: boolean
  onPieceDrop?: (sourceSquare: string, targetSquare: string | null) => boolean
  showNotation?: boolean
}

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

const boardShell = cva("")
const FILES = "abcdefgh"

type NormalizedArrow = {
  fromX: number
  fromY: number
  toX: number
  toY: number
  colorSlot: number
  fromSquare: string
  toSquare: string
  rank?: number
  uci?: string
  cp?: number | null
  mate?: number | null
}

function squareToNormalized(
  square: string,
  orientation: "white" | "black",
): { x: number; y: number } | null {
  if (!/^[a-h][1-8]$/.test(square)) return null

  const fileIndex = FILES.indexOf(square[0])
  const rank = Number(square[1])
  if (fileIndex < 0 || Number.isNaN(rank)) return null

  const col = orientation === "white" ? fileIndex : 7 - fileIndex
  const row = orientation === "white" ? 8 - rank : rank - 1

  return {
    x: (col + 0.5) / 8,
    y: (row + 0.5) / 8,
  }
}

function distanceToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1
  const dy = y2 - y1
  if (dx === 0 && dy === 0) return Math.hypot(px - x1, py - y1)

  const t = Math.max(
    0,
    Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)),
  )
  const closestX = x1 + t * dx
  const closestY = y1 + t * dy
  return Math.hypot(px - closestX, py - closestY)
}

function evalLabel(cp?: number | null, mate?: number | null): string {
  if (typeof mate === "number") {
    return mate > 0 ? `M${mate}` : `M${mate}`
  }
  if (typeof cp === "number") {
    const score = (cp / 100).toFixed(2)
    return cp >= 0 ? `+${score}` : score
  }
  return "?"
}

export function parseFenBoard(fen: string): ParsedFenBoard {
  const trimmedFen = fen.trim()
  if (!trimmedFen) {
    return { normalizedFen: STARTING_FEN, error: "FEN is empty." }
  }

  const result = validateFen(trimmedFen)
  if (!result.ok) {
    return {
      normalizedFen: STARTING_FEN,
      error: result.error ?? "Invalid FEN.",
    }
  }

  return { normalizedFen: trimmedFen, error: null }
}

export function FenBoard({
  fen,
  orientation = "white",
  className,
  arrows = [],
  allowDragging = false,
  allowDrawingArrows = false,
  onPieceDrop,
  showNotation = true,
}: FenBoardProps) {
  const boardId = useId()
  const boardRef = useRef<HTMLDivElement | null>(null)
  const [hoveredArrow, setHoveredArrow] = useState<{
    arrow: NormalizedArrow
    x: number
    y: number
  } | null>(null)
  const parsed = parseFenBoard(fen)
  const uniqueArrows = useMemo(() => {
    const seen = new Set<string>()
    return arrows.filter((arrow) => {
      const key = `${arrow.from_square}-${arrow.to_square}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [arrows])
  const boardArrows = useMemo(
    () =>
      uniqueArrows.map((arrow) => ({
        startSquare: arrow.from_square,
        endSquare: arrow.to_square,
        color: colorForArrowSlot(arrow.color_slot),
      })),
    [uniqueArrows],
  )
  const normalizedArrows = useMemo<NormalizedArrow[]>(() => {
    return uniqueArrows.reduce<NormalizedArrow[]>((acc, arrow) => {
        const from = squareToNormalized(arrow.from_square, orientation)
        const to = squareToNormalized(arrow.to_square, orientation)
        if (!from || !to) return acc
        acc.push({
          fromX: from.x,
          fromY: from.y,
          toX: to.x,
          toY: to.y,
          colorSlot: arrow.color_slot,
          fromSquare: arrow.from_square,
          toSquare: arrow.to_square,
          rank: arrow.rank,
          uci: arrow.uci,
          cp: arrow.cp,
          mate: arrow.mate,
        })
        return acc
      }, [])
  }, [orientation, uniqueArrows])

  const handleMouseMove = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      const rect = boardRef.current?.getBoundingClientRect()
      if (!rect || normalizedArrows.length === 0) {
        setHoveredArrow(null)
        return
      }

      const localX = event.clientX - rect.left
      const localY = event.clientY - rect.top
      let best: NormalizedArrow | null = null
      let bestDistance = Number.POSITIVE_INFINITY

      for (const arrow of normalizedArrows) {
        const distance = distanceToSegment(
          localX,
          localY,
          arrow.fromX * rect.width,
          arrow.fromY * rect.height,
          arrow.toX * rect.width,
          arrow.toY * rect.height,
        )
        if (distance < bestDistance) {
          bestDistance = distance
          best = arrow
        }
      }

      const threshold = Math.max(12, rect.width * 0.02)
      if (best && bestDistance <= threshold) {
        setHoveredArrow({
          arrow: best,
          x: Math.max(12, Math.min(localX + 12, rect.width - 12)),
          y: Math.max(12, Math.min(localY - 12, rect.height - 12)),
        })
      } else {
        setHoveredArrow(null)
      }
    },
    [normalizedArrows],
  )

  return (
    <div className={cn("space-y-2", className)}>
      <div
        ref={boardRef}
        className={cn("relative", boardShell())}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredArrow(null)}
      >
        <Chessboard
          options={{
            id: boardId,
            position: parsed.normalizedFen,
            boardOrientation: orientation,
            allowDragging,
            allowDrawingArrows,
            onPieceDrop: onPieceDrop
              ? ({ sourceSquare, targetSquare }) =>
                  onPieceDrop(sourceSquare, targetSquare)
              : undefined,
            arrows: boardArrows,
            clearArrowsOnClick: true,
            clearArrowsOnPositionChange: true,
            showNotation,
            animationDurationInMs: 180,
            boardStyle: {
              width: "100%",
              borderRadius: "0.5rem",
              overflow: "hidden",
            },
            darkSquareStyle: {
              backgroundColor: "rgba(6, 95, 70, 0.9)",
            },
            lightSquareStyle: {
              backgroundColor: "rgb(209, 250, 229)",
            },
          }}
        />
        {hoveredArrow ? (
          <div
            className="pointer-events-none absolute z-20 rounded-md bg-black/80 px-2 py-1 text-xs text-white shadow"
            style={{
              left: hoveredArrow.x,
              top: hoveredArrow.y,
              transform: "translate(-50%, -100%)",
            }}
          >
            <span className="font-semibold">
              #{hoveredArrow.arrow.rank ?? hoveredArrow.arrow.colorSlot}
            </span>{" "}
            {hoveredArrow.arrow.uci ??
              `${hoveredArrow.arrow.fromSquare}${hoveredArrow.arrow.toSquare}`}{" "}
            ({evalLabel(hoveredArrow.arrow.cp, hoveredArrow.arrow.mate)})
          </div>
        ) : null}
      </div>
      {parsed.error ? (
        <p className="text-sm text-red-500">{parsed.error}</p>
      ) : null}
    </div>
  )
}

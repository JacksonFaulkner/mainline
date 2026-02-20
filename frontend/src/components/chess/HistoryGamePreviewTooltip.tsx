import { useEffect, useMemo, useState } from "react"

import { FenBoard } from "@/components/chess/FenBoard"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { RecentGameSummary } from "@/features/chess/types"

type HistoryGamePreviewTooltipProps = {
  game: RecentGameSummary
}

const FRAME_MS = 850

export function HistoryGamePreviewTooltip({ game }: HistoryGamePreviewTooltipProps) {
  const [open, setOpen] = useState(false)
  const [frameIndex, setFrameIndex] = useState(0)

  const previewFens = useMemo(() => game.preview_fens ?? [], [game.preview_fens])
  const previewSans = useMemo(() => game.preview_sans ?? [], [game.preview_sans])
  const frameCount = previewFens.length

  useEffect(() => {
    if (!open || frameCount <= 1) {
      setFrameIndex(0)
      return
    }

    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1 >= frameCount ? 0 : current + 1))
    }, FRAME_MS)

    return () => window.clearInterval(timer)
  }, [open, frameCount])

  const currentFen = frameCount > 0 ? previewFens[frameIndex] : null
  const currentSan = frameIndex > 0 ? previewSans[frameIndex - 1] : null

  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <a className="underline" href={game.url} target="_blank" rel="noreferrer">
          {game.game_id}
        </a>
      </TooltipTrigger>
      <TooltipContent
        side="right"
        sideOffset={8}
        className="w-[250px] rounded-md border bg-popover p-2 text-popover-foreground shadow-md"
      >
        <div className="space-y-2">
          <div className="text-[11px] text-muted-foreground">
            Last {Math.min(6, previewSans.length)} moves
          </div>
          {currentFen ? (
            <FenBoard fen={currentFen} className="mx-auto w-[180px]" showNotation={false} />
          ) : (
            <p className="text-xs text-muted-foreground">Preview unavailable for this game.</p>
          )}
          <div className="text-xs">
            {currentSan ? (
              <span>
                Move {frameIndex}: <span className="font-semibold">{currentSan}</span>
              </span>
            ) : (
              <span className="text-muted-foreground">Starting preview frame</span>
            )}
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

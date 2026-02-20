import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export const CHESS_WORKSPACE_BOARD_CLASS =
  "w-full max-w-[calc(100dvh-9.75rem)] xl:max-w-[calc(100dvh-10.25rem)]"

type ChessWorkspaceLayoutProps = {
  board: ReactNode
  panel: ReactNode
  className?: string
  gridClassName?: string
  boardPaneClassName?: string
  panelClassName?: string
}

export function ChessWorkspaceLayout({
  board,
  panel,
  className,
  gridClassName,
  boardPaneClassName,
  panelClassName,
}: ChessWorkspaceLayoutProps) {
  return (
    <div className={cn("-mt-2 -mb-2 md:-mt-4 md:-mb-4", className)}>
      <div
        className={cn(
          "grid gap-2 xl:grid-cols-[minmax(0,calc(100dvh-10.25rem))_minmax(0,1fr)]",
          gridClassName,
        )}
      >
        <div
          className={cn(
            "flex min-h-[calc(100dvh-9.25rem)] items-center justify-center",
            boardPaneClassName,
          )}
        >
          {board}
        </div>
        <div className={cn("min-w-0 space-y-3 xl:pt-1", panelClassName)}>{panel}</div>
      </div>
    </div>
  )
}

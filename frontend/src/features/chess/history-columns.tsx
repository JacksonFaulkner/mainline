import type { ColumnDef } from "@tanstack/react-table"

import { HistoryGamePreviewTooltip } from "@/components/chess/HistoryGamePreviewTooltip"
import { HistoryGameReviewButton } from "@/components/chess/HistoryGameReviewButton"
import type { RecentGameSummary } from "./types"

export const historyColumns: ColumnDef<RecentGameSummary>[] = [
  {
    accessorKey: "game_id",
    header: "Game",
    cell: ({ row }) => <HistoryGamePreviewTooltip game={row.original} />,
  },
  {
    accessorKey: "my_result",
    header: "Result",
  },
  {
    accessorKey: "opponent_name",
    header: "Opponent",
    cell: ({ row }) => row.original.opponent_name ?? "-",
  },
  {
    accessorKey: "speed",
    header: "Speed",
    cell: ({ row }) => row.original.speed ?? "-",
  },
  {
    id: "game_review",
    header: "Game Review",
    cell: ({ row }) => <HistoryGameReviewButton gameId={row.original.game_id} />,
  },
]

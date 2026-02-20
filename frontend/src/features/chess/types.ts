export type ApiMessage = {
  ok: boolean
  message?: string | null
}

export type AccountInfo = {
  id: string
  username: string
  title?: string | null
  perfs: Record<string, unknown>
  disabled?: boolean | null
}

export type RecentGameSummary = {
  game_id: string
  url: string
  my_color?: "white" | "black" | null
  my_result: "win" | "loss" | "draw" | "unknown"
  opponent_name?: string | null
  opponent_rating?: number | null
  rated?: boolean | null
  speed?: string | null
  perf?: string | null
  variant?: string | null
  status?: string | null
  winner?: "white" | "black" | null
  created_at?: string | null
  last_move_at?: string | null
  preview_fens?: string[]
  preview_sans?: string[]
}

export type RecentGamesResponse = {
  ok: boolean
  count: number
  games: RecentGameSummary[]
}

export type SeekRequest = {
  minutes: number
  increment: number
  rated: boolean
  color: "random" | "white" | "black"
  variant: string
}

export type SeekResponse = {
  ok: boolean
  queued: boolean
  requested: SeekRequest
}

export type OpeningMatch = {
  eco: string
  name: string
  ply: number
  pgn?: string | null
  uci?: string | null
  epd?: string | null
}

export type OpeningContinuation = {
  uci: string
  from_square: string
  to_square: string
  rank: number
  color_slot: number
  eco?: string | null
  name?: string | null
  ply?: number | null
  pgn?: string | null
}

export type OpeningDatabaseInfo = {
  source: "missing" | "starter" | "full"
  file_count: number
}

export type OpeningLookupResponse = {
  ok: boolean
  matched: boolean
  opening: OpeningMatch | null
  continuations: OpeningContinuation[]
  database: OpeningDatabaseInfo
}

export type StockfishPVLine = {
  rank: number
  san?: string | null
  cp?: number | null
  mate?: number | null
  arrow: {
    uci: string
    from_square: string
    to_square: string
    color_slot: number
  }
  pv: string[]
}

export type StockfishDepthUpdateEvent = {
  type: "depth_update"
  analysis_id: string
  fen: string
  side_to_move: "white" | "black"
  depth: number
  multipv: number
  bestmove_uci?: string | null
  lines: StockfishPVLine[]
  generated_at: string
}

export type StockfishAnalysisCompleteEvent = {
  type: "analysis_complete"
  analysis_id: string
  fen: string
  final_depth: number
  bestmove_uci?: string | null
  lines: StockfishPVLine[]
  reason: string
  generated_at: string
}

export type StockfishAnalysisErrorEvent = {
  type: "analysis_error"
  analysis_id?: string | null
  code: string
  message: string
  retryable: boolean
  generated_at: string
}

export type StockfishStreamEvent =
  | StockfishDepthUpdateEvent
  | StockfishAnalysisCompleteEvent
  | StockfishAnalysisErrorEvent

export type CommentaryTextDeltaEvent = {
  type: "commentary_text_delta"
  analysis_id: string
  text_delta: string
  text: string
  generated_at: string
}

export type CommentaryStructuredPlan = {
  position_plan_title: string
  advantage_side: "white" | "black" | "equal" | "unclear"
  advantage_summary: string
  best_move_san: string
  best_move_reason: string
  danger_to_watch: string
  white_plan: [string, string]
  black_plan: [string, string]
  concrete_ideas: Array<{
    title: string
    description: string
    selected_line_id: string
    playback_pv_uci: string[]
  }>
}

export type CommentaryAnalysisCompleteEvent = {
  type: "commentary_complete"
  analysis_id: string
  text: string
  structured?: CommentaryStructuredPlan | null
  stop_reason?: string | null
  usage?: {
    input_tokens?: number | null
    output_tokens?: number | null
    total_tokens?: number | null
  } | null
  latency_ms?: number | null
  generated_at: string
}

export type CommentaryAnalysisErrorEvent = {
  type: "commentary_error"
  analysis_id?: string | null
  code: string
  message: string
  retryable: boolean
  generated_at: string
}

export type CommentaryAnalysisStreamEvent =
  | CommentaryTextDeltaEvent
  | CommentaryAnalysisCompleteEvent
  | CommentaryAnalysisErrorEvent

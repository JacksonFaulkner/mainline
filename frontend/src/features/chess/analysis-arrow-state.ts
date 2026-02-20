import type {
  StockfishAnalysisCompleteEvent,
  StockfishDepthUpdateEvent,
  StockfishPVLine,
  StockfishStreamEvent,
} from "@/features/chess/types"

/**
 * Arrow shape consumed by FenBoard.
 */
export interface AnalysisBoardArrow {
  from_square: string
  to_square: string
  color_slot: number
  rank: number
  uci: string
  cp?: number | null
  mate?: number | null
}

/**
 * Active SSE session identity. `streamToken` is client-owned and prevents stale callbacks
 * from older streams from mutating UI state.
 */
export interface AnalysisArrowSession {
  streamToken: number
  targetFen: string
  analysisId: string | null
  minDepth: number
  warmupDepthCount: number
  warmupTopN: number
  steadyTopN: number
}

/**
 * Last accepted engine arrow snapshot for the current board.
 */
export interface AnalysisArrowSnapshot {
  source: "engine"
  targetFen: string
  analysisId: string
  depth: number
  arrows: AnalysisBoardArrow[]
  updatedAtMs: number
}

export type AnalysisStreamStatus = "idle" | "streaming" | "closed"

/**
 * Single source of truth for analysis stream + arrows.
 */
export interface AnalysisArrowState {
  status: AnalysisStreamStatus
  session: AnalysisArrowSession | null
  snapshot: AnalysisArrowSnapshot | null
  events: StockfishStreamEvent[]
  lastError: string | null
}

type StartSessionAction = {
  type: "start_session"
  streamToken: number
  targetFen: string
  minDepth: number
  warmupDepthCount: number
  warmupTopN: number
  steadyTopN: number
}

type StopSessionAction = {
  type: "stop_session"
  streamToken: number
  nextStatus: AnalysisStreamStatus
}

type ResetBoardAction = {
  type: "reset_for_board_change"
}

type LocalErrorAction = {
  type: "local_error"
  message: string
}

type IngestEventAction = {
  type: "ingest_stream_event"
  streamToken: number
  payload: StockfishStreamEvent
}

export type AnalysisArrowAction =
  | StartSessionAction
  | StopSessionAction
  | ResetBoardAction
  | LocalErrorAction
  | IngestEventAction

function mapLineToBoardArrow(line: StockfishPVLine): AnalysisBoardArrow {
  return {
    ...line.arrow,
    rank: line.rank,
    uci: line.arrow.uci,
    cp: line.cp,
    mate: line.mate,
  }
}

function isDepthLikeEvent(
  payload: StockfishStreamEvent,
): payload is StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent {
  return payload.type === "depth_update" || payload.type === "analysis_complete"
}

function depthOfEvent(
  payload: StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent,
): number {
  return payload.type === "depth_update" ? payload.depth : payload.final_depth
}

function trimLinesForStage(
  lines: StockfishPVLine[],
  options: {
    depth: number
    session: AnalysisArrowSession
  },
): StockfishPVLine[] {
  const { depth, session } = options
  const warmupDepthLimit = session.minDepth + session.warmupDepthCount - 1
  const topN = depth <= warmupDepthLimit ? session.warmupTopN : session.steadyTopN
  return lines.slice(0, Math.max(1, topN))
}

export function createInitialAnalysisArrowState(): AnalysisArrowState {
  return {
    status: "idle",
    session: null,
    snapshot: null,
    events: [],
    lastError: null,
  }
}

export function analysisArrowReducer(
  state: AnalysisArrowState,
  action: AnalysisArrowAction,
): AnalysisArrowState {
  switch (action.type) {
    case "start_session":
      return {
        status: "streaming",
        session: {
          streamToken: action.streamToken,
          targetFen: action.targetFen,
          analysisId: null,
          minDepth: action.minDepth,
          warmupDepthCount: action.warmupDepthCount,
          warmupTopN: action.warmupTopN,
          steadyTopN: action.steadyTopN,
        },
        snapshot: null,
        events: [],
        lastError: null,
      }
    case "stop_session":
      if (!state.session || state.session.streamToken !== action.streamToken) {
        return state
      }
      return {
        ...state,
        status: action.nextStatus,
        session: null,
      }
    case "reset_for_board_change":
      return createInitialAnalysisArrowState()
    case "local_error":
      return {
        status: "closed",
        session: null,
        snapshot: null,
        events: [],
        lastError: action.message,
      }
    case "ingest_stream_event": {
      if (!state.session || state.session.streamToken !== action.streamToken) {
        return state
      }

      const payload = action.payload
      if (payload.type === "analysis_error") {
        return {
          status: "closed",
          session: null,
          snapshot: null,
          events: [...state.events, payload],
          lastError: payload.message,
        }
      }

      if (!isDepthLikeEvent(payload)) {
        return state
      }

      if (payload.fen !== state.session.targetFen) {
        return state
      }

      if (
        state.session.analysisId !== null &&
        payload.analysis_id !== state.session.analysisId
      ) {
        return state
      }

      const analysisId = state.session.analysisId ?? payload.analysis_id
      const depth = depthOfEvent(payload)
      const trimmedLines = trimLinesForStage(payload.lines, {
        depth,
        session: state.session,
      })
      const trimmedPayload: StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent =
        payload.type === "depth_update"
          ? {
              ...payload,
              lines: trimmedLines,
              multipv: trimmedLines.length,
            }
          : {
              ...payload,
              lines: trimmedLines,
            }
      const snapshot: AnalysisArrowSnapshot = {
        source: "engine",
        targetFen: payload.fen,
        analysisId,
        depth,
        arrows: trimmedLines.map(mapLineToBoardArrow),
        updatedAtMs: Date.now(),
      }

      if (payload.type === "analysis_complete") {
        return {
          status: "closed",
          session: null,
          snapshot,
          events: [...state.events, trimmedPayload],
          lastError: null,
        }
      }

      return {
        status: "streaming",
        session: {
          ...state.session,
          analysisId,
        },
        snapshot,
        events: [...state.events, trimmedPayload],
        lastError: null,
      }
    }
    default:
      return state
  }
}

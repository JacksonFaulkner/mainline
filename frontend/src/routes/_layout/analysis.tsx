import { Chess } from "chess.js"
import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"
import { z } from "zod"

import { AnalysisEvalChart } from "@/components/chess/AnalysisEvalChart"
import {
  CHESS_WORKSPACE_BOARD_CLASS,
  ChessWorkspaceLayout,
} from "@/components/chess/ChessWorkspaceLayout"
import { FenBoard, parseFenBoard } from "@/components/chess/FenBoard"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import { buildAnalysisStreamUrl, buildCommentaryAnalysisStreamUrl } from "@/features/chess/api"
import {
  analysisArrowReducer,
  createInitialAnalysisArrowState,
} from "@/features/chess/analysis-arrow-state"
import { openAuthenticatedSse, type SseStreamHandle } from "@/features/chess/sse"
import type {
  CommentaryStructuredPlan,
  CommentaryAnalysisStreamEvent,
  StockfishAnalysisCompleteEvent,
  StockfishDepthUpdateEvent,
  StockfishStreamEvent,
} from "@/features/chess/types"

export const Route = createFileRoute("/_layout/analysis")({
  component: AnalysisRoute,
  validateSearch: z.object({
    tab: z.enum(["analysis", "settings"]).catch("analysis"),
  }),
  head: () => ({
    meta: [{ title: "Analysis - Chess" }],
  }),
})

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
const ANALYSIS_MIN_DEPTH = 8
const ANALYSIS_MAX_DEPTH = 24
const ANALYSIS_WARMUP_DEPTH_COUNT = 10
const ANALYSIS_WARMUP_TOP_N = 5
const ANALYSIS_STEADY_TOP_N = 5
const COMMENTARY_REFRESH_DEPTH = 18
const COMMENTARY_ANIMATION_INTERVAL_MS = 24
const COMMENTARY_ANIMATION_CHARS_PER_TICK = 3

function isStockfishDepthLikeEvent(
  payload: StockfishStreamEvent,
): payload is StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent {
  return payload.type === "depth_update" || payload.type === "analysis_complete"
}

function formatEvalLabel(cp?: number | null, mate?: number | null): string {
  if (typeof mate === "number") {
    return `M${mate > 0 ? "+" : ""}${mate}`
  }
  if (typeof cp === "number") {
    const pawnScore = cp / 100
    const withSign = pawnScore > 0 ? `+${pawnScore.toFixed(2)}` : pawnScore.toFixed(2)
    return withSign
  }
  return "n/a"
}

type CandidateStockfishLine = {
  branchUci: string
  firstMoveSan: string | null
  depth: number
  rank: number
  evalLabel: string
  pvUci: string[]
}

type ConcreteIdea = CommentaryStructuredPlan["concrete_ideas"][number]

function stockfishDepthOfEvent(
  payload: StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent,
): number {
  return payload.type === "depth_update" ? payload.depth : payload.final_depth
}

function mergeCandidateStockfishLines(
  current: CandidateStockfishLine[],
  payload: StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent,
): CandidateStockfishLine[] {
  const depth = stockfishDepthOfEvent(payload)
  const byBranch = new Map<string, CandidateStockfishLine>(
    current.map((line) => [line.branchUci, line]),
  )

  for (const line of payload.lines) {
    const branchUci = (line.pv[0] ?? line.arrow.uci ?? "").toLowerCase()
    if (!branchUci) continue
    const pvUci = (line.pv.length > 0 ? line.pv : [line.arrow.uci])
      .map((move) => move.toLowerCase())
      .slice(0, 8)
    const candidate: CandidateStockfishLine = {
      branchUci,
      firstMoveSan: line.san ?? null,
      depth,
      rank: line.rank,
      evalLabel: formatEvalLabel(line.cp, line.mate),
      pvUci,
    }
    const existing = byBranch.get(branchUci)
    if (!existing || depth > existing.depth || (depth === existing.depth && line.rank < existing.rank)) {
      byBranch.set(branchUci, candidate)
    }
  }

  return Array.from(byBranch.values())
    .sort((a, b) => b.depth - a.depth || a.rank - b.rank)
    .slice(0, 10)
}

function buildEngineConcreteIdeas(lines: CandidateStockfishLine[]): ConcreteIdea[] {
  return lines.slice(0, 2).map((line, index) => {
    const lineId = `L${String(index + 1).padStart(2, "0")}`
    const moveLabel = line.firstMoveSan ?? line.branchUci
    return {
      title: `Try ${moveLabel}`,
      description: `Engine branch ${lineId} scores ${line.evalLabel} at depth ${line.depth}.`,
      selected_line_id: lineId,
      playback_pv_uci: line.pvUci,
    }
  })
}

function buildStockfishContext(
  payload: StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent,
  candidateLines: CandidateStockfishLine[],
): string {
  const depth = stockfishDepthOfEvent(payload)
  const topLines = payload.lines.slice(0, 5)
  const bestLine = topLines[0]
  const bestMove = bestLine?.san ?? bestLine?.arrow.uci ?? payload.bestmove_uci ?? "unknown"
  const bestEval = formatEvalLabel(bestLine?.cp, bestLine?.mate)
  const lineSummary = topLines
    .map((line) => {
      const move = line.san ?? line.arrow.uci
      return `#${line.rank} ${move} (${formatEvalLabel(line.cp, line.mate)})`
    })
    .join("; ")
  const candidateSummary = candidateLines
    .slice(0, 10)
    .map((line, index) => {
      const id = `L${String(index + 1).padStart(2, "0")}`
      const san = line.firstMoveSan ? ` ${line.firstMoveSan}` : ""
      return `${id}|${line.branchUci}${san}|${line.evalLabel}|${line.pvUci.join(" ")}`
    })
    .join("; ")
  return (
    `Depth ${depth}. Best move ${bestMove} (${bestEval}). Top lines: ${lineSummary}. ` +
    `Candidate lines (10 unique branches): ${candidateSummary}`
  )
}

function parseUciForPlayback(uci: string): { from: string; to: string; promotion?: "q" | "r" | "b" | "n" } | null {
  const clean = uci.trim().toLowerCase()
  if (!/^[a-h][1-8][a-h][1-8][nbrq]?$/.test(clean)) return null
  const promotion = clean.length === 5 ? (clean[4] as "q" | "r" | "b" | "n") : undefined
  return { from: clean.slice(0, 2), to: clean.slice(2, 4), promotion }
}

function sanitizeCommentaryText(rawText: string): string {
  const trimmed = rawText.trim()
  if (!trimmed) return rawText
  if (!trimmed.startsWith("```")) {
    return rawText.replace(/```json/g, "").replace(/```/g, "").trim()
  }
  const lines = trimmed.split("\n")
  if (lines.length >= 3 && lines[lines.length - 1]?.trim() === "```") {
    return lines.slice(1, -1).join("\n").trim()
  }
  return rawText.replace(/```json/g, "").replace(/```/g, "").trim()
}

function parseCommentaryStructuredFromText(rawText: string): CommentaryStructuredPlan | null {
  const clean = sanitizeCommentaryText(rawText)
  if (!clean) return null

  const extractJsonObjectCandidates = (text: string): string[] => {
    const candidates: string[] = []
    let depth = 0
    let startIndex = -1
    let inString = false
    let escaped = false

    for (let index = 0; index < text.length; index += 1) {
      const char = text[index]
      if (inString) {
        if (escaped) {
          escaped = false
          continue
        }
        if (char === "\\") {
          escaped = true
          continue
        }
        if (char === "\"") {
          inString = false
        }
        continue
      }
      if (char === "\"") {
        inString = true
        continue
      }
      if (char === "{") {
        if (depth === 0) startIndex = index
        depth += 1
        continue
      }
      if (char === "}" && depth > 0) {
        depth -= 1
        if (depth === 0 && startIndex >= 0) {
          candidates.push(text.slice(startIndex, index + 1).trim())
          startIndex = -1
        }
      }
    }
    return candidates
  }

  const normalizeCandidate = (candidate: string): string => {
    const trimmed = candidate.trim()
    if (trimmed.toLowerCase().startsWith("json\n")) {
      return trimmed.slice(5).trim()
    }
    return trimmed
  }

  const repairCandidate = (candidate: string): string => candidate.replace(/,\s*([}\]])/g, "$1")

  const candidates: string[] = []
  const seenCandidates = new Set<string>()
  const pushCandidate = (candidate: string) => {
    const normalized = normalizeCandidate(candidate)
    if (!normalized || seenCandidates.has(normalized)) return
    seenCandidates.add(normalized)
    candidates.push(normalized)
  }

  pushCandidate(clean)
  extractJsonObjectCandidates(clean).forEach(pushCandidate)

  const asText = (value: unknown): string | null => {
    if (typeof value !== "string") return null
    const normalized = value.trim()
    return normalized ? normalized : null
  }

  const asPlanBullets = (value: unknown): [string, string] | null => {
    if (Array.isArray(value)) {
      const entries = value
        .map(asText)
        .filter((entry): entry is string => Boolean(entry))
        .slice(0, 2)
      if (entries.length < 2) return null
      return [entries[0], entries[1]]
    }
    if (typeof value === "string") {
      const entries = value
        .split(/\n|;|•|\s-\s/)
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0)
        .slice(0, 2)
      if (entries.length < 2) return null
      return [entries[0], entries[1]]
    }
    return null
  }

  for (const candidate of candidates) {
    try {
      let parsed: Record<string, unknown>
      try {
        parsed = JSON.parse(candidate) as Record<string, unknown>
      } catch {
        parsed = JSON.parse(repairCandidate(candidate)) as Record<string, unknown>
      }
      const title = asText(parsed.position_plan_title)
      const advantageSummary = asText(parsed.advantage_summary)
      const bestMoveSan = asText(parsed.best_move_san)
      const bestMoveReason = asText(parsed.best_move_reason)
      const dangerToWatch = asText(parsed.danger_to_watch)
      const whitePlan = asPlanBullets(parsed.white_plan)
      const blackPlan = asPlanBullets(parsed.black_plan)
      if (!title || !advantageSummary || !bestMoveSan || !bestMoveReason || !dangerToWatch) continue
      if (!whitePlan || !blackPlan) continue

      const sideRaw = parsed.advantage_side
      const advantageSide =
        sideRaw === "white" || sideRaw === "black" || sideRaw === "equal" || sideRaw === "unclear"
          ? sideRaw
          : "unclear"

      const ideasRaw = Array.isArray(parsed.concrete_ideas) ? parsed.concrete_ideas : []
      const ideas: ConcreteIdea[] = ideasRaw
        .map((idea, index) => {
          if (!idea || typeof idea !== "object") return null
          const record = idea as Record<string, unknown>
          const ideaTitle = asText(record.title)
          const ideaDescription = asText(record.description)
          const selectedLineId = asText(record.selected_line_id) ?? `L${String(index + 1).padStart(2, "0")}`
          const playbackRaw = Array.isArray(record.playback_pv_uci) ? record.playback_pv_uci : []
          const playback = playbackRaw
            .map((move) => (typeof move === "string" ? move.trim().toLowerCase() : ""))
            .filter((move) => move.length > 0)
          if (!ideaTitle || !ideaDescription || playback.length === 0) return null
          return {
            title: ideaTitle,
            description: ideaDescription,
            selected_line_id: selectedLineId,
            playback_pv_uci: playback,
          }
        })
        .filter((idea): idea is ConcreteIdea => Boolean(idea))
        .slice(0, 2)

      return {
        position_plan_title: title,
        advantage_side: advantageSide,
        advantage_summary: advantageSummary,
        best_move_san: bestMoveSan,
        best_move_reason: bestMoveReason,
        danger_to_watch: dangerToWatch,
        white_plan: whitePlan,
        black_plan: blackPlan,
        concrete_ideas: ideas,
      }
    } catch {
      // Ignore malformed JSON candidates while streaming.
    }
  }

  return null
}

function AnalysisRoute() {
  const { tab } = Route.useSearch()
  const [fen, setFen] = useState(STARTING_FEN)
  const [orientation, setOrientation] = useState<"white" | "black">("white")
  const [arrowState, dispatchArrowAction] = useReducer(
    analysisArrowReducer,
    undefined,
    createInitialAnalysisArrowState,
  )
  const streamRef = useRef<SseStreamHandle | null>(null)
  const activeStreamTokenRef = useRef(0)
  const commentaryStreamRef = useRef<SseStreamHandle | null>(null)
  const activeCommentaryStreamTokenRef = useRef(0)
  const commentaryAnimationTimerRef = useRef<number | null>(null)
  const ideaPlaybackTimerRef = useRef<number | null>(null)
  const candidateStockfishLinesRef = useRef<CandidateStockfishLine[]>([])
  const commentaryRawTextRef = useRef("")
  const [commentaryStatus, setCommentaryStatus] = useState<"idle" | "streaming" | "closed">("idle")
  const [commentaryRenderedText, setCommentaryRenderedText] = useState("")
  const [commentaryStructured, setCommentaryStructured] = useState<CommentaryStructuredPlan | null>(null)
  const [engineConcreteIdeas, setEngineConcreteIdeas] = useState<ConcreteIdea[]>([])
  const [activeIdeaKey, setActiveIdeaKey] = useState<string | null>(null)
  const [commentaryError, setCommentaryError] = useState<string | null>(null)

  const parsedFen = useMemo(() => parseFenBoard(fen), [fen])
  const streamUrl = useMemo(
    () =>
      buildAnalysisStreamUrl({
        fen: parsedFen.normalizedFen,
        multipv: ANALYSIS_WARMUP_TOP_N,
        minDepth: ANALYSIS_MIN_DEPTH,
        maxDepth: ANALYSIS_MAX_DEPTH,
        depthStep: 1,
        throttleMs: 25,
      }),
    [parsedFen.normalizedFen],
  )

  const invalidateActiveStream = useCallback(() => {
    activeStreamTokenRef.current += 1
    streamRef.current?.close()
    streamRef.current = null
  }, [])

  const invalidateActiveCommentaryStream = useCallback(() => {
    activeCommentaryStreamTokenRef.current += 1
    commentaryStreamRef.current?.close()
    commentaryStreamRef.current = null
  }, [])

  const stopCommentaryAnimation = useCallback(() => {
    if (commentaryAnimationTimerRef.current !== null) {
      window.clearInterval(commentaryAnimationTimerRef.current)
      commentaryAnimationTimerRef.current = null
    }
  }, [])

  const stopIdeaPlayback = useCallback(() => {
    if (ideaPlaybackTimerRef.current !== null) {
      window.clearTimeout(ideaPlaybackTimerRef.current)
      ideaPlaybackTimerRef.current = null
    }
    setActiveIdeaKey(null)
  }, [])

  const kickCommentaryAnimation = useCallback(() => {
    if (commentaryAnimationTimerRef.current !== null) return

    commentaryAnimationTimerRef.current = window.setInterval(() => {
      setCommentaryRenderedText((currentText) => {
        const targetText = commentaryRawTextRef.current
        if (currentText.length >= targetText.length) {
          stopCommentaryAnimation()
          return currentText
        }
        const nextLength = Math.min(
          targetText.length,
          currentText.length + COMMENTARY_ANIMATION_CHARS_PER_TICK,
        )
        return targetText.slice(0, nextLength)
      })
    }, COMMENTARY_ANIMATION_INTERVAL_MS)
  }, [stopCommentaryAnimation])

  const stopStream = useCallback(
    (nextStatus: "idle" | "closed" = "closed") => {
      const activeToken = activeStreamTokenRef.current
      invalidateActiveStream()
      invalidateActiveCommentaryStream()
      stopIdeaPlayback()
      dispatchArrowAction({
        type: "stop_session",
        streamToken: activeToken,
        nextStatus,
      })
      setCommentaryStatus(nextStatus)
      setCommentaryError(null)
      if (nextStatus === "idle") {
        commentaryRawTextRef.current = ""
        setCommentaryRenderedText("")
        setCommentaryStructured(null)
        setEngineConcreteIdeas([])
        candidateStockfishLinesRef.current = []
      }
      stopCommentaryAnimation()
    },
    [
      invalidateActiveCommentaryStream,
      invalidateActiveStream,
      stopCommentaryAnimation,
      stopIdeaPlayback,
    ],
  )

  useEffect(
    () => () => {
      invalidateActiveStream()
      invalidateActiveCommentaryStream()
      stopCommentaryAnimation()
      stopIdeaPlayback()
    },
    [
      invalidateActiveCommentaryStream,
      invalidateActiveStream,
      stopCommentaryAnimation,
      stopIdeaPlayback,
    ],
  )

  const startCommentaryStream = useCallback(
    (params: {
      token: string
      commentaryStreamToken: number
      stockfishContext: string
    }) => {
      stopCommentaryAnimation()
      commentaryRawTextRef.current = ""
      setCommentaryRenderedText("")
      setCommentaryStatus("streaming")
      setCommentaryError(null)
      setCommentaryStructured(null)
      const commentaryUrl = buildCommentaryAnalysisStreamUrl({
        fen: parsedFen.normalizedFen,
        stockfishContext: params.stockfishContext,
      })

      commentaryStreamRef.current = openAuthenticatedSse(commentaryUrl, params.token, {
        onEvent: (eventName, eventData) => {
          if (params.commentaryStreamToken !== activeCommentaryStreamTokenRef.current) return
          if (eventName === "proxy_error") {
            try {
              const payload = JSON.parse(eventData) as { error?: string }
              setCommentaryStatus("closed")
              setCommentaryError(payload.error ?? "Commentary stream failed.")
              invalidateActiveCommentaryStream()
              return
            } catch {
              setCommentaryStatus("closed")
              setCommentaryError("Commentary stream failed.")
              invalidateActiveCommentaryStream()
              return
            }
          }
          try {
            const payload = JSON.parse(eventData) as CommentaryAnalysisStreamEvent
            if (payload.type === "commentary_text_delta") {
              const nextText =
                typeof payload.text === "string"
                  ? payload.text
                  : typeof payload.text_delta === "string"
                    ? `${commentaryRawTextRef.current}${payload.text_delta}`
                    : commentaryRawTextRef.current
              commentaryRawTextRef.current = nextText
              setCommentaryError(null)
              setCommentaryStatus("streaming")
              kickCommentaryAnimation()
              return
            }
            if (payload.type === "commentary_complete") {
              const completionText =
                typeof payload.text === "string" ? payload.text : commentaryRawTextRef.current
              if (completionText.length >= commentaryRawTextRef.current.length) {
                commentaryRawTextRef.current = completionText
                kickCommentaryAnimation()
              }
              setCommentaryStructured(payload.structured ?? null)
              setCommentaryStatus("closed")
              invalidateActiveCommentaryStream()
              return
            }
            if (payload.type === "commentary_error") {
              setCommentaryStatus("closed")
              setCommentaryError(payload.message)
              setCommentaryStructured(null)
              invalidateActiveCommentaryStream()
            }
          } catch {
            // Ignore malformed stream payloads in UI preview mode.
          }
        },
        onError: (error) => {
          if (params.commentaryStreamToken !== activeCommentaryStreamTokenRef.current) return
          setCommentaryStatus("closed")
          setCommentaryError(error.message)
          setCommentaryStructured(null)
          invalidateActiveCommentaryStream()
        },
        onClose: () => {
          if (params.commentaryStreamToken !== activeCommentaryStreamTokenRef.current) return
          setCommentaryStatus((currentStatus) =>
            currentStatus === "streaming" ? "closed" : currentStatus,
          )
        },
      })
    },
    [
      invalidateActiveCommentaryStream,
      kickCommentaryAnimation,
      parsedFen.normalizedFen,
      stopCommentaryAnimation,
    ],
  )

  const applyBoardMove = useCallback(
    (sourceSquare: string, targetSquare: string | null): boolean => {
      if (!targetSquare) return false
      if (parsedFen.error) return false

      try {
        const chess = new Chess(parsedFen.normalizedFen)
        const move = chess.move({
          from: sourceSquare,
          to: targetSquare,
          promotion: "q",
        })
        if (!move) return false

        stopStream("idle")
        setFen(chess.fen())
        dispatchArrowAction({ type: "reset_for_board_change" })
        return true
      } catch {
        return false
      }
    },
    [parsedFen.error, parsedFen.normalizedFen, stopStream],
  )

  const playConcreteIdea = useCallback(
    (idea: CommentaryStructuredPlan["concrete_ideas"][number], ideaIndex: number) => {
      if (parsedFen.error) return
      stopStream("idle")
      stopIdeaPlayback()

      const working = new Chess(parsedFen.normalizedFen)
      const ideaKey = `${idea.selected_line_id}-${ideaIndex}`
      setActiveIdeaKey(ideaKey)
      setFen(working.fen())
      dispatchArrowAction({ type: "reset_for_board_change" })

      let moveIndex = 0
      const step = () => {
        if (moveIndex >= idea.playback_pv_uci.length) {
          setActiveIdeaKey(null)
          return
        }
        const parsedMove = parseUciForPlayback(idea.playback_pv_uci[moveIndex])
        if (!parsedMove) {
          setCommentaryError(`Invalid idea move: ${idea.playback_pv_uci[moveIndex]}`)
          setActiveIdeaKey(null)
          return
        }
        const applied = working.move(parsedMove)
        if (!applied) {
          setCommentaryError(`Could not play move ${idea.playback_pv_uci[moveIndex]} on this board.`)
          setActiveIdeaKey(null)
          return
        }

        setFen(working.fen())
        moveIndex += 1
        if (moveIndex < idea.playback_pv_uci.length) {
          ideaPlaybackTimerRef.current = window.setTimeout(step, 520)
        } else {
          setActiveIdeaKey(null)
        }
      }
      step()
    },
    [
      parsedFen.error,
      parsedFen.normalizedFen,
      stopIdeaPlayback,
      stopStream,
    ],
  )

  const startStream = useCallback(() => {
    invalidateActiveStream()
    invalidateActiveCommentaryStream()
    stopCommentaryAnimation()
    stopIdeaPlayback()
    candidateStockfishLinesRef.current = []
    commentaryRawTextRef.current = ""
    setCommentaryRenderedText("")
    setCommentaryStructured(null)
    setEngineConcreteIdeas([])
    setActiveIdeaKey(null)
    setCommentaryStatus("idle")
    setCommentaryError(null)

    if (parsedFen.error) {
      dispatchArrowAction({
        type: "local_error",
        message: `Invalid FEN: ${parsedFen.error}`,
      })
      return
    }

    const token = localStorage.getItem("access_token")
    if (!token) {
      dispatchArrowAction({
        type: "local_error",
        message: "Missing access token. Please log in again.",
      })
      return
    }

    const streamToken = activeStreamTokenRef.current
    const commentaryStreamToken = activeCommentaryStreamTokenRef.current
    let commentaryStarted = false
    let commentaryRefreshedAtDepth18 = false
    dispatchArrowAction({
      type: "start_session",
      streamToken,
      targetFen: parsedFen.normalizedFen,
      minDepth: ANALYSIS_MIN_DEPTH,
      warmupDepthCount: ANALYSIS_WARMUP_DEPTH_COUNT,
      warmupTopN: ANALYSIS_WARMUP_TOP_N,
      steadyTopN: ANALYSIS_STEADY_TOP_N,
    })
    setCommentaryStatus("idle")

    streamRef.current = openAuthenticatedSse(streamUrl, token, {
      onEvent: (_eventName, eventData) => {
        if (streamToken !== activeStreamTokenRef.current) return
        try {
          const payload = JSON.parse(eventData) as StockfishStreamEvent
          if (isStockfishDepthLikeEvent(payload)) {
            candidateStockfishLinesRef.current = mergeCandidateStockfishLines(
              candidateStockfishLinesRef.current,
              payload,
            )
            setEngineConcreteIdeas(buildEngineConcreteIdeas(candidateStockfishLinesRef.current))
            const context = buildStockfishContext(payload, candidateStockfishLinesRef.current)
            const depth = stockfishDepthOfEvent(payload)
            if (!commentaryStarted) {
              startCommentaryStream({
                token,
                commentaryStreamToken,
                stockfishContext: context,
              })
              commentaryStarted = true
              commentaryRefreshedAtDepth18 = depth >= COMMENTARY_REFRESH_DEPTH
            } else if (
              !commentaryRefreshedAtDepth18 &&
              depth >= COMMENTARY_REFRESH_DEPTH
            ) {
              invalidateActiveCommentaryStream()
              const refreshedCommentaryStreamToken = activeCommentaryStreamTokenRef.current
              startCommentaryStream({
                token,
                commentaryStreamToken: refreshedCommentaryStreamToken,
                stockfishContext: context,
              })
              commentaryRefreshedAtDepth18 = true
            }
          }
          dispatchArrowAction({
            type: "ingest_stream_event",
            streamToken,
            payload,
          })
          if (
            payload.type === "analysis_complete" ||
            payload.type === "analysis_error"
          ) {
            invalidateActiveStream()
          }
        } catch {
          // Ignore malformed stream payloads in UI preview mode.
        }
      },
      onError: (error) => {
        if (streamToken !== activeStreamTokenRef.current) return
        dispatchArrowAction({
          type: "local_error",
          message: error.message,
        })
        invalidateActiveStream()
      },
      onClose: () => {
        if (streamToken !== activeStreamTokenRef.current) return
        dispatchArrowAction({
          type: "stop_session",
          streamToken,
          nextStatus: "closed",
        })
      },
    })
  }, [
    invalidateActiveStream,
    parsedFen.error,
    parsedFen.normalizedFen,
    startCommentaryStream,
    stopCommentaryAnimation,
    stopIdeaPlayback,
    streamUrl,
  ])

  const isStreaming = arrowState.status === "streaming" || commentaryStatus === "streaming"
  const commentaryDisplayText = sanitizeCommentaryText(commentaryRenderedText)
  const commentaryRawDisplayText = sanitizeCommentaryText(commentaryRawTextRef.current)
  const commentaryParsedFromRawText = useMemo(
    () => parseCommentaryStructuredFromText(commentaryRawDisplayText),
    [commentaryRawDisplayText],
  )
  const resolvedCommentaryStructured = commentaryStructured ?? commentaryParsedFromRawText
  const commentaryIdeas =
    resolvedCommentaryStructured?.concrete_ideas && resolvedCommentaryStructured.concrete_ideas.length > 0
      ? resolvedCommentaryStructured.concrete_ideas
      : engineConcreteIdeas
  const commentaryLooksLikeJson = commentaryRawDisplayText.trim().startsWith("{")
  const commentaryIsAnimating = commentaryDisplayText.length < commentaryRawDisplayText.length

  return (
    <Tabs value={tab} className="gap-0">
      <ChessWorkspaceLayout
        board={
          <FenBoard
            fen={fen}
            orientation={orientation}
            arrows={arrowState.snapshot?.arrows ?? []}
            allowDragging
            onPieceDrop={applyBoardMove}
            className={CHESS_WORKSPACE_BOARD_CLASS}
          />
        }
        panel={
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-card p-2">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  onClick={startStream}
                  disabled={isStreaming}
                >
                  {isStreaming ? "Streaming..." : "Start stream"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => stopStream()}
                  disabled={!isStreaming}
                >
                  Stop stream
                </Button>
              </div>
              <span className="text-sm text-muted-foreground">
                Status: Engine {arrowState.status}, Commentary {commentaryStatus}
              </span>
            </div>
            <TabsContent value="analysis" className="space-y-3">
              {arrowState.lastError ? (
                <p className="text-sm text-red-500">{arrowState.lastError}</p>
              ) : null}

              <AnalysisEvalChart events={arrowState.events} />

              <section className="space-y-2 rounded-lg border bg-card p-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">Commentary live evaluation</h3>
                  <span className="text-xs text-muted-foreground">
                    {commentaryStatus}
                  </span>
                </div>
                {commentaryError ? (
                  <p className="text-sm text-red-500">{commentaryError}</p>
                ) : null}
                <div className="grid gap-3 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                  <section className="space-y-2 rounded-md border bg-muted/20 p-3">
                    {resolvedCommentaryStructured ? (
                      <>
                        <h4 className="text-sm font-semibold">
                          {resolvedCommentaryStructured.position_plan_title}
                        </h4>
                        <p className="text-sm">
                          {resolvedCommentaryStructured.advantage_summary}
                        </p>
                        <p className="text-sm">
                          <span className="font-medium">Best move:</span>{" "}
                          {resolvedCommentaryStructured.best_move_san} -{" "}
                          {resolvedCommentaryStructured.best_move_reason}
                        </p>
                        <p className="text-sm">
                          <span className="font-medium">Danger:</span>{" "}
                          {resolvedCommentaryStructured.danger_to_watch}
                        </p>
                        <div className="grid gap-3 md:grid-cols-2">
                          <section className="space-y-1">
                            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                              White Plan
                            </p>
                            <ul className="list-disc space-y-1 pl-5 text-sm">
                              {resolvedCommentaryStructured.white_plan.map((point, index) => (
                                <li key={`white-${index}`}>{point}</li>
                              ))}
                            </ul>
                          </section>
                          <section className="space-y-1">
                            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                              Black Plan
                            </p>
                            <ul className="list-disc space-y-1 pl-5 text-sm">
                              {resolvedCommentaryStructured.black_plan.map((point, index) => (
                                <li key={`black-${index}`}>{point}</li>
                              ))}
                            </ul>
                          </section>
                        </div>
                      </>
                    ) : (
                      <div className="min-h-24 rounded-md bg-muted/30 p-3">
                        <p className="whitespace-pre-wrap text-sm leading-6">
                          {commentaryLooksLikeJson
                            ? commentaryStatus === "streaming" || commentaryIsAnimating
                              ? "Formatting structured commentary..."
                              : "Structured commentary was returned but could not be parsed."
                            : commentaryDisplayText ||
                              (commentaryStatus === "streaming"
                                ? "Commentary is thinking..."
                                : arrowState.status === "streaming"
                                  ? "Waiting for Stockfish context..."
                                  : "Start stream to generate a live commentary evaluation.")}
                          {commentaryStatus === "streaming" ? (
                            <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-foreground/70 align-text-bottom" />
                          ) : null}
                        </p>
                      </div>
                    )}
                  </section>
                  <section className="space-y-2 rounded-md border bg-muted/20 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Concrete Ideas
                      </p>
                      <span className="text-xs text-muted-foreground">
                        {commentaryIdeas.length}/2
                      </span>
                    </div>
                    {commentaryIdeas.length > 0 ? (
                      <div className="space-y-2">
                        {commentaryIdeas.map((idea, index) => {
                          const ideaKey = `${idea.selected_line_id}-${index}`
                          return (
                            <div
                              key={ideaKey}
                              className="rounded-md border bg-background/70 p-2"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div>
                                  <p className="text-sm font-medium">{idea.title}</p>
                                  <p className="text-xs text-muted-foreground">
                                    Line {idea.selected_line_id}
                                  </p>
                                </div>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={activeIdeaKey === ideaKey ? "default" : "outline"}
                                  onClick={() => playConcreteIdea(idea, index)}
                                >
                                  {activeIdeaKey === ideaKey ? "Playing..." : "Play"}
                                </Button>
                              </div>
                              <p className="mt-1 text-sm leading-5">{idea.description}</p>
                            </div>
                          )
                        })}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No concrete ideas yet. Start analysis and wait for commentary.
                      </p>
                    )}
                  </section>
                </div>
              </section>
            </TabsContent>

            <TabsContent value="settings" className="space-y-3">
              <label className="block text-sm">
                FEN
                <Input
                  className="mt-1 font-mono text-xs"
                  value={fen}
                  onChange={(e) => {
                    stopStream("idle")
                    setFen(e.target.value)
                    dispatchArrowAction({ type: "reset_for_board_change" })
                  }}
                />
              </label>

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
            </TabsContent>
          </>
        }
      />
    </Tabs>
  )
}

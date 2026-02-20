import type {
  AccountInfo,
  ApiMessage,
  OpeningLookupResponse,
  RecentGamesResponse,
  SeekRequest,
  SeekResponse,
} from "./types"

const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")

function url(path: string): string {
  if (apiBase) {
    return `${apiBase}${path}`
  }
  return path
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("access_token")
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (init?.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json"
  }

  const response = await fetch(url(path), {
    ...init,
    headers,
  })
  if (!response.ok) {
    const reason = await response.text()
    throw new Error(reason || `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export function getChessHealth(): Promise<ApiMessage> {
  return requestJson<ApiMessage>("/api/v1/chess/health")
}

export function getChessMe(): Promise<AccountInfo> {
  return requestJson<AccountInfo>("/api/v1/chess/me")
}

export function getRecentGames(limit = 10): Promise<RecentGamesResponse> {
  return requestJson<RecentGamesResponse>(`/api/v1/chess/me/games/recent?limit=${limit}`)
}

export function getGameReview(gameId: string, refresh = false): Promise<unknown> {
  const suffix = refresh ? "?refresh=true" : ""
  return requestJson<unknown>(`/api/v1/chess/games/${encodeURIComponent(gameId)}/review${suffix}`)
}

export function createSeek(payload: SeekRequest): Promise<SeekResponse> {
  return requestJson<SeekResponse>("/api/v1/chess/seek", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function lookupOpening(params: {
  moves: string[]
  initialFen?: string | null
}): Promise<OpeningLookupResponse> {
  return requestJson<OpeningLookupResponse>("/api/v1/chess/openings/lookup", {
    method: "POST",
    body: JSON.stringify({
      moves: params.moves,
      initialFen: params.initialFen ?? null,
    }),
  })
}

export function buildAnalysisStreamUrl(params: {
  fen: string
  minDepth?: number
  maxDepth?: number
  multipv?: number
  depthStep?: number
  throttleMs?: number
}): string {
  const search = new URLSearchParams()
  search.set("fen", params.fen)
  search.set("min_depth", String(params.minDepth ?? 8))
  search.set("max_depth", String(params.maxDepth ?? 24))
  search.set("multipv", String(params.multipv ?? 3))
  search.set("depth_step", String(params.depthStep ?? 1))
  search.set("throttle_ms", String(params.throttleMs ?? 25))
  return url(`/api/v1/chess/analysis/stream?${search.toString()}`)
}

export function buildCommentaryAnalysisStreamUrl(params: {
  fen: string
  stockfishContext?: string | null
}): string {
  const search = new URLSearchParams()
  search.set("fen", params.fen)
  if (params.stockfishContext && params.stockfishContext.trim()) {
    search.set("stockfish_context", params.stockfishContext.trim())
  }
  return url(`/api/v1/chess/analysis/commentary/stream?${search.toString()}`)
}

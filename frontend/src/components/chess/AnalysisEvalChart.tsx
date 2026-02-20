import { useEffect, useMemo, useRef, useState } from "react"
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts"

import {
  Card,
  CardContent,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  type ChartConfig,
} from "@/components/ui/chart"
import { colorForArrowSlot } from "@/features/chess/colors"
import type {
  StockfishAnalysisCompleteEvent,
  StockfishDepthUpdateEvent,
  StockfishPVLine,
  StockfishStreamEvent,
} from "@/features/chess/types"
import { cn } from "@/lib/utils"

type AnalysisEvalChartProps = {
  events: StockfishStreamEvent[]
  className?: string
}

type LinePoint = {
  depth: number
  value: number
  cp?: number | null
  mate?: number | null
}

type LineSeries = {
  id: string
  rank: number
  san: string | null
  colorSlot: number
  points: LinePoint[]
}

type DepthRow = { depth: number } & Record<string, number | undefined>
const MAX_DISPLAY_SERIES = 5

function isDepthEvent(
  event: StockfishStreamEvent,
): event is StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent {
  return event.type === "depth_update" || event.type === "analysis_complete"
}

function eventDepth(
  event: StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent,
): number {
  return event.type === "analysis_complete" ? event.final_depth : event.depth
}

function normalizeEval(cp?: number | null, mate?: number | null): number | null {
  if (typeof mate === "number") {
    return mate >= 0 ? 12 : -12
  }
  if (typeof cp === "number") {
    const pawns = cp / 100
    return Math.max(-12, Math.min(12, pawns))
  }
  return null
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

function formatAnimatedCp(cp: number): string {
  const score = (cp / 100).toFixed(2)
  return cp >= 0 ? `+${score}` : score
}

function AnimatedEvalValue({
  cp,
  mate,
}: {
  cp?: number | null
  mate?: number | null
}) {
  const [displayCp, setDisplayCp] = useState<number | null>(
    typeof cp === "number" ? cp : null,
  )
  const displayCpRef = useRef<number | null>(
    typeof cp === "number" ? cp : null,
  )
  const previousTargetRef = useRef<number | null>(
    typeof cp === "number" ? cp : null,
  )
  const frameRef = useRef<number | null>(null)
  const [flash, setFlash] = useState<"up" | "down" | null>(null)

  useEffect(() => {
    displayCpRef.current = displayCp
  }, [displayCp])

  useEffect(() => {
    if (typeof cp !== "number") {
      setDisplayCp(null)
      displayCpRef.current = null
      previousTargetRef.current = null
      return
    }

    const from = displayCpRef.current ?? cp
    const to = cp
    const previousTarget = previousTargetRef.current
    if (typeof previousTarget === "number" && previousTarget !== to) {
      setFlash(to > previousTarget ? "up" : "down")
    }
    previousTargetRef.current = to

    if (from === to) {
      setDisplayCp(to)
      return
    }

    const durationMs = 260
    const start = performance.now()
    const step = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(1, elapsed / durationMs)
      const eased = 1 - (1 - progress) ** 3
      setDisplayCp(from + (to - from) * eased)
      if (progress < 1) {
        frameRef.current = window.requestAnimationFrame(step)
      } else {
        frameRef.current = null
      }
    }

    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }
    frameRef.current = window.requestAnimationFrame(step)

    const clearFlash = window.setTimeout(() => setFlash(null), durationMs + 80)
    return () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current)
        frameRef.current = null
      }
      window.clearTimeout(clearFlash)
    }
  }, [cp])

  if (typeof mate === "number") {
    return (
      <span className="inline-block min-w-12 text-right font-mono tabular-nums text-foreground transition-colors">
        {`M${mate}`}
      </span>
    )
  }

  if (typeof cp !== "number" || displayCp === null) {
    return (
      <span className="inline-block min-w-12 text-right font-mono tabular-nums text-muted-foreground">
        ?
      </span>
    )
  }

  return (
    <span
      className={cn(
        "inline-block min-w-12 text-right font-mono tabular-nums transition-colors",
        flash === "up" && "text-emerald-500",
        flash === "down" && "text-rose-500",
        flash === null && "text-foreground",
      )}
    >
      {formatAnimatedCp(displayCp)}
    </span>
  )
}

function moveLabel(series: LineSeries): string {
  const san = series.san?.trim()
  if (san) return san
  return series.id
}

function upsertPoint(
  series: LineSeries,
  depth: number,
  line: StockfishPVLine,
): LineSeries {
  const normalized = normalizeEval(line.cp, line.mate)
  if (normalized === null) {
    return series
  }
  const point: LinePoint = {
    depth,
    value: normalized,
    cp: line.cp,
    mate: line.mate,
  }
  const existing = series.points.findIndex((entry) => entry.depth === depth)
  if (existing >= 0) {
    const next = [...series.points]
    next[existing] = point
    return { ...series, points: next }
  }
  return {
    ...series,
    points: [...series.points, point].sort((a, b) => a.depth - b.depth),
  }
}

function buildSeries(events: StockfishStreamEvent[]): LineSeries[] {
  const latestDepthEvent = [...events].reverse().find(isDepthEvent)
  if (!latestDepthEvent) {
    return []
  }

  const map = new Map<string, LineSeries>()

  for (const event of events) {
    if (!isDepthEvent(event)) continue
    const depth = eventDepth(event)
    for (const line of event.lines) {
      const id = line.arrow.uci
      if (!id) continue
      const base =
        map.get(id) ??
        ({
          id,
          rank: line.rank,
          san: line.san ?? null,
          colorSlot: line.arrow.color_slot,
          points: [],
        } satisfies LineSeries)

      const updated = upsertPoint(
        {
          ...base,
          rank: line.rank,
          san: line.san ?? null,
          colorSlot: line.arrow.color_slot,
        },
        depth,
        line,
      )
      map.set(id, updated)
    }
  }

  const seenActive = new Set<string>()
  const activeSeries: LineSeries[] = []
  for (const line of latestDepthEvent.lines) {
    if (activeSeries.length >= MAX_DISPLAY_SERIES) break
    const id = line.arrow.uci
    if (!id || seenActive.has(id)) continue
    seenActive.add(id)
    const historical = map.get(id)
    if (!historical || historical.points.length === 0) continue
    activeSeries.push({
      ...historical,
      rank: line.rank,
      san: line.san ?? null,
      colorSlot: line.arrow.color_slot,
    })
  }

  return activeSeries.sort((a, b) => a.rank - b.rank)
}

function buildDepthRows(series: LineSeries[]): DepthRow[] {
  const rows = new Map<number, DepthRow>()
  for (const line of series) {
    for (const point of line.points) {
      const row = rows.get(point.depth) ?? { depth: point.depth }
      row[line.id] = point.value
      rows.set(point.depth, row)
    }
  }
  return [...rows.values()].sort((a, b) => a.depth - b.depth)
}

function roundingStep(span: number): number {
  if (span <= 1.2) return 0.1
  if (span <= 3) return 0.25
  if (span <= 8) return 0.5
  return 1
}

function roundDown(value: number, step: number): number {
  return Math.floor(value / step) * step
}

function roundUp(value: number, step: number): number {
  return Math.ceil(value / step) * step
}

function computeYDomain(series: LineSeries[]): [number, number] {
  const values = series.flatMap((line) => line.points.map((point) => point.value))
  if (values.length === 0) return [-1, 1]

  const minValue = Math.min(...values)
  const maxValue = Math.max(...values)
  const range = maxValue - minValue
  const pad = Math.max(0.08, range * 0.2)

  let min = minValue - pad
  let max = maxValue + pad

  if (min > 0) min = 0
  if (max < 0) max = 0

  if (max - min < 0.6) {
    const center = (max + min) / 2
    min = center - 0.3
    max = center + 0.3
  }

  min = Math.max(-12, min)
  max = Math.min(12, max)

  const step = roundingStep(max - min)
  const roundedMin = Math.max(-12, roundDown(min, step))
  const roundedMax = Math.min(12, roundUp(max, step))
  return [roundedMin, roundedMax]
}

function computeXDomain(data: DepthRow[]): [number, number] {
  if (data.length === 0) return [8, 24]
  const min = data[0]?.depth ?? 8
  const max = data[data.length - 1]?.depth ?? min
  return max > min ? [min, max] : [min, min + 1]
}

function formatYAxisTick(value: number): string {
  if (Math.abs(value) >= 2 || Number.isInteger(value)) {
    return value > 0 ? `+${value}` : `${value}`
  }
  const fixed = value.toFixed(1)
  return value > 0 ? `+${fixed}` : fixed
}

export function AnalysisEvalChart({ events, className }: AnalysisEvalChartProps) {
  const series = useMemo(() => buildSeries(events), [events])
  const data = useMemo(() => buildDepthRows(series), [series])
  const xDomain = useMemo(() => computeXDomain(data), [data])
  const yDomain = useMemo(() => computeYDomain(series), [series])
  const chartConfig = useMemo<ChartConfig>(() => {
    return series.reduce<ChartConfig>((acc, line) => {
      acc[line.id] = {
        label: `#${line.rank} ${moveLabel(line)}`,
        color: colorForArrowSlot(line.colorSlot),
      }
      return acc
    }, {})
  }, [series])
  const pointsByDepth = useMemo(() => {
    const lookup = new Map<string, LinePoint>()
    for (const line of series) {
      for (const point of line.points) {
        lookup.set(`${line.id}:${point.depth}`, point)
      }
    }
    return lookup
  }, [series])

  if (series.length === 0 || data.length === 0) {
    return (
      <Card className={cn(className)}>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Start a stream to see each candidate move change as depth increases.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn(className)}>
      <CardContent>
        <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {series.map((line) => (
            <span key={line.id} className="inline-flex items-center gap-1">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: colorForArrowSlot(line.colorSlot) }}
              />
              #{line.rank} {moveLabel(line)}
              <AnimatedEvalValue
                cp={line.points[line.points.length - 1]?.cp}
                mate={line.points[line.points.length - 1]?.mate}
              />
            </span>
          ))}
        </div>
        <ChartContainer
          config={chartConfig}
          className="h-56 w-full aspect-auto"
        >
          <LineChart
            accessibilityLayer
            data={data}
            margin={{ top: 10, right: 8, left: 2, bottom: 0 }}
          >
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="depth"
              type="number"
              allowDecimals={false}
              domain={xDomain}
              tickCount={Math.min(9, Math.max(4, xDomain[1] - xDomain[0] + 1))}
              axisLine={false}
              tickLine={false}
              tickMargin={8}
            />
            <YAxis
              type="number"
              domain={yDomain}
              tickCount={7}
              tickFormatter={formatYAxisTick}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <ChartTooltip
              cursor={false}
              content={({ active, label, payload }) => {
                if (!active || !payload?.length || typeof label !== "number") {
                  return null
                }
                return (
                  <div className="rounded-md border bg-background p-2 text-xs shadow-md">
                    <div className="font-semibold">Depth {label}</div>
                    <div className="mt-1 space-y-1">
                      {series.map((line) => {
                        const point = pointsByDepth.get(`${line.id}:${label}`)
                        if (!point) return null
                        return (
                          <div
                            key={`${line.id}:${label}`}
                            className="flex items-center gap-2"
                          >
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{
                                backgroundColor: colorForArrowSlot(line.colorSlot),
                              }}
                            />
                            <span className="font-medium">#{line.rank}</span>
                            <span>{moveLabel(line)}</span>
                            <span className="text-muted-foreground">
                              {evalLabel(point.cp, point.mate)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              }}
            />
            {series.map((line) => (
              <Line
                key={line.id}
                type="monotone"
                dataKey={line.id}
                stroke={`var(--color-${line.id})`}
                strokeWidth={line.rank === 1 ? 3 : 2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

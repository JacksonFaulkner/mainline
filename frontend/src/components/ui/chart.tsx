import * as React from "react"
import * as RechartsPrimitive from "recharts"

import { cn } from "@/lib/utils"

export type ChartConfig = {
  [key: string]: {
    label?: React.ReactNode
    color?: string
  }
}

type ChartContextProps = {
  config: ChartConfig
}

const ChartContext = React.createContext<ChartContextProps | null>(null)

function useChart() {
  const context = React.useContext(ChartContext)
  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />")
  }
  return context
}

type ChartContainerProps = React.ComponentProps<"div"> & {
  config: ChartConfig
  children: React.ComponentProps<
    typeof RechartsPrimitive.ResponsiveContainer
  >["children"]
}

const ChartContainer = React.forwardRef<HTMLDivElement, ChartContainerProps>(
  ({ id, className, children, config, style, ...props }, ref) => {
    const uniqueId = React.useId().replace(/:/g, "")
    const chartId = `chart-${id ?? uniqueId}`

    const cssVars = Object.entries(config).reduce<Record<string, string>>(
      (acc, [key, value]) => {
        if (value.color) {
          acc[`--color-${key}`] = value.color
        }
        return acc
      },
      {},
    )

    return (
      <ChartContext.Provider value={{ config }}>
        <div
          data-slot="chart"
          data-chart={chartId}
          ref={ref}
          className={cn(
            "flex aspect-video justify-center text-xs [&_.recharts-cartesian-grid_line]:stroke-border/60 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-text]:fill-muted-foreground",
            className,
          )}
          style={{ ...(cssVars as React.CSSProperties), ...style }}
          {...props}
        >
          <RechartsPrimitive.ResponsiveContainer>
            {children}
          </RechartsPrimitive.ResponsiveContainer>
        </div>
      </ChartContext.Provider>
    )
  },
)
ChartContainer.displayName = "ChartContainer"

const ChartTooltip = RechartsPrimitive.Tooltip

type ChartTooltipContentProps = Omit<
  RechartsPrimitive.TooltipContentProps<number, string>,
  "formatter"
> & {
  hideLabel?: boolean
  formatter?: (
    value: unknown,
    name: unknown,
    item: unknown,
    index: number,
  ) => React.ReactNode
}

function ChartTooltipContent({
  active,
  payload,
  label,
  hideLabel = false,
  formatter,
}: ChartTooltipContentProps) {
  const { config } = useChart()

  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="grid min-w-[140px] gap-1.5 rounded-md border bg-background px-2.5 py-2 text-xs shadow-md">
      {!hideLabel ? (
        <div className="font-medium text-foreground">{label}</div>
      ) : null}
      <div className="grid gap-1">
        {payload.map((item, index) => {
          const key = String(item.dataKey ?? "")
          const entry = config[key]
          const itemLabel = entry?.label ?? key
          const color = entry?.color ?? String(item.color ?? "currentColor")
          const rendered = formatter
            ? formatter(item.value, item.name, item, index)
            : null

          if (rendered) {
            return (
              <div key={key} className="flex items-center gap-2">
                {rendered as React.ReactNode}
              </div>
            )
          }

          return (
            <div key={key} className="flex items-center gap-2">
              <span
                className="h-2 w-2 shrink-0 rounded-[2px]"
                style={{ backgroundColor: color }}
              />
              <span className="text-muted-foreground">{itemLabel}</span>
              <span className="ml-auto font-mono tabular-nums text-foreground">
                {item.value}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export { ChartContainer, ChartTooltip, ChartTooltipContent }

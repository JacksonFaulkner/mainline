import { Chess } from "chess.js"
import { Link, createFileRoute } from "@tanstack/react-router"
import { Brain, History, RefreshCcw, Rocket, Swords } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { FenBoard } from "@/components/chess/FenBoard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

type OpeningReplay = {
  eco: string
  name: string
  moves: string[]
  note: string
}

type ActionItem = {
  title: string
  description: string
  href: "/play" | "/analysis" | "/openings" | "/history"
  icon: typeof Swords
}

type ReplayFrames = {
  fens: string[]
  sanMoves: string[]
}

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

const ACTION_ITEMS: ActionItem[] = [
  {
    title: "Play",
    description: "Jump into live games and training positions.",
    href: "/play",
    icon: Swords,
  },
  {
    title: "Analysis",
    description: "Use engine lines and commentary to improve decisions.",
    href: "/analysis",
    icon: Brain,
  },
  {
    title: "Openings",
    description: "Explore book continuations and opening names.",
    href: "/openings",
    icon: Rocket,
  },
  {
    title: "History",
    description: "Review recent games and revisit key moments.",
    href: "/history",
    icon: History,
  },
]

const OPENING_REPLAYS: OpeningReplay[] = [
  {
    eco: "C60",
    name: "Ruy Lopez",
    moves: ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7"],
    note: "Classical center control with long-term queenside pressure.",
  },
  {
    eco: "B20",
    name: "Sicilian Defense",
    moves: ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
    note: "Asymmetrical play from move one and rich tactical middlegames.",
  },
  {
    eco: "D30",
    name: "Queen's Gambit Declined",
    moves: ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O"],
    note: "Solid central structure with strategic piece maneuvering.",
  },
  {
    eco: "E60",
    name: "King's Indian Defense",
    moves: ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3", "O-O"],
    note: "Black yields space early and aims for dynamic counterplay.",
  },
  {
    eco: "A46",
    name: "London System",
    moves: ["d4", "Nf6", "Nf3", "e6", "Bf4", "d5", "e3", "Bd6", "Bg3", "O-O"],
    note: "Reliable setup with quick development and a clear plan.",
  },
  {
    eco: "C42",
    name: "Petrov Defense",
    moves: ["e4", "e5", "Nf3", "Nf6", "Nxe5", "d6", "Nf3", "Nxe4", "d4", "d5"],
    note: "Balanced structure where precise move order matters.",
  },
]

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Dashboard - Chess",
      },
    ],
  }),
})

function pickRandomOpening(previous?: string): OpeningReplay {
  if (OPENING_REPLAYS.length === 1) return OPENING_REPLAYS[0]

  const options = previous
    ? OPENING_REPLAYS.filter((opening) => opening.name !== previous)
    : OPENING_REPLAYS
  return options[Math.floor(Math.random() * options.length)] ?? OPENING_REPLAYS[0]
}

function buildReplayFrames(moves: string[]): ReplayFrames {
  const chess = new Chess()
  const fens: string[] = [STARTING_FEN]
  const sanMoves: string[] = []

  for (const move of moves) {
    const played = chess.move(move)
    if (!played) break
    sanMoves.push(played.san)
    fens.push(chess.fen())
  }

  return { fens, sanMoves }
}

function formatMove(index: number, san: string): string {
  const moveNumber = Math.floor(index / 2) + 1
  return index % 2 === 0 ? `${moveNumber}. ${san}` : `${moveNumber}... ${san}`
}

function Dashboard() {
  const [opening, setOpening] = useState<OpeningReplay>(() => pickRandomOpening())
  const [frameIndex, setFrameIndex] = useState(0)

  const replay = useMemo(() => buildReplayFrames(opening.moves), [opening])
  const currentFen = replay.fens[frameIndex] ?? STARTING_FEN
  const activeMoveIndex = frameIndex > 0 ? frameIndex - 1 : -1

  useEffect(() => {
    if (replay.fens.length <= 1) return
    const isEnd = frameIndex >= replay.fens.length - 1
    const timeout = window.setTimeout(() => {
      setFrameIndex((current) => (current >= replay.fens.length - 1 ? 0 : current + 1))
    }, isEnd ? 1600 : 900)
    return () => window.clearTimeout(timeout)
  }, [frameIndex, replay.fens.length])

  const randomizeReplay = () => {
    setOpening((current) => pickRandomOpening(current.name))
    setFrameIndex(0)
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.9fr)]">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="space-y-1">
                <CardTitle>Opening Replay</CardTitle>
                <CardDescription>
                  A random opening line auto-plays on loop.
                </CardDescription>
              </div>
              <Badge variant="secondary">{opening.eco}</Badge>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
            <FenBoard fen={currentFen} showNotation={false} className="w-full max-w-xl" />
            <div className="space-y-3">
              <div>
                <p className="text-sm text-muted-foreground">Now showing</p>
                <h3 className="text-lg font-semibold">{opening.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{opening.note}</p>
              </div>
              <ol className="grid max-h-56 grid-cols-1 gap-1 overflow-auto rounded-md border p-3 text-sm sm:grid-cols-2">
                {replay.sanMoves.map((san, index) => {
                  const isActive = index === activeMoveIndex
                  return (
                    <li
                      key={`${opening.name}-${index}-${san}`}
                      className={
                        isActive
                          ? "rounded-sm bg-primary/15 px-2 py-1 font-medium animate-pulse"
                          : "rounded-sm px-2 py-1 text-muted-foreground"
                      }
                    >
                      {formatMove(index, san)}
                    </li>
                  )
                })}
              </ol>
            </div>
          </CardContent>
          <CardFooter className="justify-between gap-3 border-t">
            <p className="text-xs text-muted-foreground">
              {frameIndex === 0 ? "Reset to start position." : "Playing move sequence."}
            </p>
            <Button size="sm" variant="outline" onClick={randomizeReplay}>
              <RefreshCcw className="size-4" />
              New Random Opening
            </Button>
          </CardFooter>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
          {ACTION_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <Card key={item.href}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Icon className="size-4 text-primary" />
                    {item.title}
                  </CardTitle>
                  <CardDescription>{item.description}</CardDescription>
                </CardHeader>
                <CardFooter className="pt-0">
                  <Button variant="outline" size="sm" asChild>
                    {item.href === "/analysis" ? (
                      <Link to="/analysis" search={{ tab: "analysis" }}>
                        Open {item.title}
                      </Link>
                    ) : (
                      <Link to={item.href}>Open {item.title}</Link>
                    )}
                  </Button>
                </CardFooter>
              </Card>
            )
          })}
        </div>
      </section>
    </div>
  )
}

import { useEffect, useMemo, useState } from "react"
import { PieChart, type Slice } from "./PieChart"
import type { InsightFilter, Video } from "./types"

type Card = {
  id: string
  title: string
  body: string
  value: string
  filter?: InsightFilter
}

type InsightsFile = {
  pies: Record<string, Slice[]>
  cards: Card[]
}

const PIE_TITLES: Record<string, string> = {
  duration: "Duration",
  recommendedAction: "Recommended action",
  category: "Category",
  contentType: "Content type",
  subCategory: "Subcategory",
  deleteBand: "Delete score band",
  flags: "Flags",
  availability: "Availability",
  watchState: "Watch state",
  language: "Language",
  age: "Published age",
  channel: "Top channels",
}

function groupPie(
  videos: Video[],
  key: (v: Video) => string,
  top = 8,
): Slice[] {
  const map = new Map<string, { n: number; hours: number }>()
  for (const v of videos) {
    const label = key(v) || "(none)"
    const cur = map.get(label) ?? { n: 0, hours: 0 }
    cur.n += 1
    cur.hours += (v.durationSeconds ?? 0) / 3600
    map.set(label, cur)
  }
  const rows = [...map.entries()]
    .map(([label, s]) => ({
      label,
      n: s.n,
      hours: Math.round(s.hours * 10) / 10,
    }))
    .sort((a, b) => b.n - a.n)
  const head = rows.slice(0, top)
  const tail = rows.slice(top)
  if (tail.length) {
    head.push({
      label: "rest",
      n: tail.reduce((a, r) => a + r.n, 0),
      hours: Math.round(tail.reduce((a, r) => a + r.hours, 0) * 10) / 10,
    })
  }
  return head
}

function fromVideos(videos: Video[]): InsightsFile {
  const hours = videos.reduce((a, v) => a + (v.durationSeconds ?? 0), 0) / 3600
  const channels = new Set(videos.map((v) => v.channel).filter(Boolean))
  return {
    pies: {
      duration: groupPie(videos, (v) => v.durationBucket, 9),
      category: groupPie(videos, (v) => v.category, 8),
      subCategory: groupPie(
        videos,
        (v) => `${v.category} / ${v.subCategory}`,
        10,
      ),
      availability: groupPie(videos, (v) => v.availability, 6),
      channel: groupPie(videos, (v) => v.channel || "(no channel)", 10),
    },
    cards: [
      {
        id: "n",
        title: "Imported playlist",
        body: `${videos.length} videos, ${hours.toFixed(1)} h, ${channels.size} channels. Computed in-browser.`,
        value: String(videos.length),
      },
    ],
  }
}

export function Analytics({
  videos,
  onApply,
}: {
  videos: Video[]
  onApply?: (f: InsightFilter) => void
}) {
  const [file, setFile] = useState<InsightsFile | null>(null)
  const [metric, setMetric] = useState<"n" | "hours">("n")
  const fallback = useMemo(() => fromVideos(videos), [videos])

  useEffect(() => {
    const url = `${import.meta.env.BASE_URL}insights.json`
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((json: InsightsFile | null) => {
        if (json?.pies) setFile(json)
      })
      .catch(() => {})
  }, [])

  const data = file ?? fallback


  const pieKeys = Object.keys(PIE_TITLES).filter((k) => data.pies[k]?.length)

  return (
    <main className="analytics">
      <div className="analytics-head">
        <h2>Insights</h2>
        <div className="seg" role="group" aria-label="pie metric">
          <button
            type="button"
            className={metric === "n" ? "on" : ""}
            onClick={() => setMetric("n")}
          >
            count
          </button>
          <button
            type="button"
            className={metric === "hours" ? "on" : ""}
            onClick={() => setMetric("hours")}
          >
            hours
          </button>
        </div>
      </div>
      <div className="pies">
        {pieKeys.map((key) => (
          <PieChart
            key={key}
            title={PIE_TITLES[key] ?? key}
            slices={data.pies[key]}
            metric={key === "flags" ? "n" : metric}
          />
        ))}
      </div>
      <div className="insight-grid">
        {data.cards.map((c) => (
          <article
            key={c.id}
            className={`insight${c.filter && onApply ? " clickable" : ""}`}
            onClick={() => c.filter && onApply?.(c.filter)}
          >
            <p className="insight-value">{c.value}</p>
            <h3>{c.title}</h3>
            <p>{c.body}</p>
          </article>
        ))}
      </div>
    </main>
  )
}

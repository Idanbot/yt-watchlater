import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import {
  clampFontScale,
  clearPlaylist,
  downloadJson,
  FONT_MAX,
  FONT_MIN,
  loadPlaylist,
  loadRemovedIds,
  loadTriage,
  loadViewPrefs,
  savePlaylist,
  saveRemovedIds,
  saveTriage,
  saveViewPrefs,
} from "./storage"
import { Analytics } from "./Analytics"
import { looksLikePlaylist, parsePlaylistText } from "./playlist"
import { thumbUrl, watchUrl } from "./thumbs"
import type {
  Action,
  ColorScheme,
  GroupBy,
  InsightFilter,
  SortKey,
  ThumbSize,
  Triage,
  TriageMap,
  Video,
  ViewMode,
} from "./types"

type Row =
  | { kind: "group"; key: string; n: number; hours: number }
  | { kind: "video"; video: Video }

type Packed =
  | { kind: "group"; key: string; n: number; hours: number }
  | { kind: "list"; video: Video }
  | { kind: "cards"; videos: Video[] }

const EMPTY: Triage = { action: "later", priority: 5, note: "" }
const SCHEME_UI: { id: ColorScheme; label: string; swatch: string }[] = [
  { id: "ember", label: "Ember", swatch: "oklch(0.78 0.14 55)" },
  { id: "ink", label: "Ink", swatch: "oklch(0.55 0.08 250)" },
  { id: "moss", label: "Moss", swatch: "oklch(0.7 0.12 150)" },
  { id: "tide", label: "Tide", swatch: "oklch(0.7 0.12 230)" },
  { id: "dusk", label: "Dusk", swatch: "oklch(0.7 0.16 310)" },
  { id: "paper", label: "Paper", swatch: "oklch(0.93 0.02 85)" },
  { id: "noir", label: "Noir", swatch: "oklch(0.18 0 0)" },
]
const LIST_H = { s: 72, m: 96, l: 132 }
const GRID_H = { s: 300, m: 368, l: 428 }
const CARD_MIN = { s: 168, m: 224, l: 280 }

function hours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b))
}
function groupValue(v: Video, by: GroupBy, triage: TriageMap): string {
  if (by === "category") return v.category || "(none)"
  if (by === "subCategory") return `${v.category} / ${v.subCategory}`
  if (by === "channel") return v.channel || "(no channel)"
  if (by === "durationBucket") return v.durationBucket || "unknown"
  if (by === "availability") return v.availability
  if (by === "action") return triage[v.videoId]?.action ?? "(unset)"
  if (by === "recommendedAction") return v.recommendedAction || "(none)"
  if (by === "contentType") return v.contentType || "(none)"
  return ""
}
function cmp(a: Video, b: Video, sort: SortKey): number {
  const n = (x: number | null | undefined) => x ?? -1
  if (sort === "position") return a.position - b.position
  if (sort === "duration") return n(b.durationSeconds) - n(a.durationSeconds)
  if (sort === "views") return n(b.viewsApprox) - n(a.viewsApprox)
  if (sort === "watchedPercent")
    return n(b.watchedPercent) - n(a.watchedPercent)
  if (sort === "removePriority") return a.removePriority - b.removePriority
  if (sort === "deleteScore") return n(b.deleteScore) - n(a.deleteScore)
  if (sort === "estimatedValue") return n(b.estimatedValue) - n(a.estimatedValue)
  if (sort === "efficiencyScore")
    return n(b.efficiencyScore) - n(a.efficiencyScore)
  return a.title.localeCompare(b.title)
}

function packRows(rows: Row[], view: ViewMode, cols: number): Packed[] {
  if (view === "list") {
    return rows.map((r) =>
      r.kind === "group" ? r : { kind: "list", video: r.video },
    )
  }
  const out: Packed[] = []
  let buf: Video[] = []
  const flush = () => {
    if (buf.length) {
      out.push({ kind: "cards", videos: buf })
      buf = []
    }
  }
  for (const r of rows) {
    if (r.kind === "group") {
      flush()
      out.push(r)
    } else {
      buf.push(r.video)
      if (buf.length >= cols) flush()
    }
  }
  flush()
  return out
}

export default function App() {
  const [videos, setVideos] = useState<Video[]>([])
  const [error, setError] = useState<string | null>(null)
  const [triage, setTriage] = useState<TriageMap>(() => loadTriage())
  const [q, setQ] = useState("")
  const [category, setCategory] = useState("")
  const [subCategory, setSubCategory] = useState("")
  const [channelQ, setChannelQ] = useState("")
  const [bucket, setBucket] = useState("")
  const [availability, setAvailability] = useState("")
  const [watched, setWatched] = useState("")
  const [hint, setHint] = useState("")
  const [saved, setSaved] = useState("")
  const [recAction, setRecAction] = useState("")
  const [contentType, setContentType] = useState("")
  const [flag, setFlag] = useState("")
  const [easyOnly, setEasyOnly] = useState(false)
  const [hebrewOnly, setHebrewOnly] = useState(false)
  const [sort, setSort] = useState<SortKey>("position")
  const [groupBy, setGroupBy] = useState<GroupBy>("none")
  const [view, setView] = useState<ViewMode>(() => loadViewPrefs().view)
  const [thumb, setThumb] = useState<ThumbSize>(() => loadViewPrefs().thumb)
  const [filtersOpen, setFiltersOpen] = useState(() => {
    try {
      if (window.matchMedia("(max-width: 720px)").matches) return false
    } catch {}
    return loadViewPrefs().filtersOpen
  })
  const [searchOpen, setSearchOpen] = useState(() => {
    try {
      if (window.matchMedia("(max-width: 720px)").matches) return false
    } catch {}
    return true
  })
  const [scheme, setScheme] = useState<ColorScheme>(() => loadViewPrefs().scheme)
  const [fontScale, setFontScale] = useState(() => loadViewPrefs().fontScale)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [width, setWidth] = useState(1100)
  const [screen, setScreen] = useState<"browse" | "analytics">("browse")
  const [copied, setCopied] = useState("")
  const [removedIds, setRemovedIds] = useState<string[]>(() => loadRemovedIds())
  const [showRemoved, setShowRemoved] = useState(false)
  const [narrow, setNarrow] = useState(false)
  const parentRef = useRef<HTMLDivElement>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const stored = loadPlaylist()
    if (stored?.length) {
      setVideos(stored)
      return
    }
    const url = `${import.meta.env.BASE_URL}videos.jsonl`
    fetch(url)
      .then((r) => (r.ok ? r.text() : ""))
      .then((text) => {
        if (!text.trim()) return
        const rows = parsePlaylistText(text)
        if (rows.length) setVideos(rows)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 720px)")
    const sync = () => setNarrow(mq.matches)
    sync()
    mq.addEventListener("change", sync)
    return () => mq.removeEventListener("change", sync)
  }, [])

  useEffect(() => {
    saveTriage(triage)
  }, [triage])

  useEffect(() => {
    saveRemovedIds(removedIds)
  }, [removedIds])

  useEffect(() => {
    saveViewPrefs({ view, thumb, filtersOpen, scheme, fontScale })
  }, [view, thumb, filtersOpen, scheme, fontScale])

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus()
  }, [searchOpen])

  useEffect(() => {
    const root = document.documentElement
    root.dataset.scheme = scheme
    const mode = scheme === "paper" ? "light" : "dark"
    root.style.colorScheme = mode
    root.style.setProperty("--font-px", String(fontScale))
    document
      .querySelector('meta[name="color-scheme"]')
      ?.setAttribute("content", mode)
  }, [scheme, fontScale])

  useEffect(() => {
    if (!settingsOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSettingsOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [settingsOpen])

  useLayoutEffect(() => {
    const el = parentRef.current
    if (!el) return
    const sync = () => setWidth(el.clientWidth || 1100)
    sync()
    const ro = new ResizeObserver(sync)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const categories = useMemo(
    () => unique(videos.map((v) => v.category)),
    [videos],
  )
  const subCategories = useMemo(
    () =>
      unique(
        videos
          .filter((v) => !category || v.category === category)
          .map((v) => v.subCategory),
      ),
    [videos, category],
  )
  const buckets = useMemo(
    () => unique(videos.map((v) => v.durationBucket)),
    [videos],
  )
  const hints = useMemo(
    () => unique(videos.flatMap((v) => v.removeHints ?? [])),
    [videos],
  )
  const recActions = useMemo(
    () => unique(videos.map((v) => v.recommendedAction ?? "")),
    [videos],
  )
  const contentTypes = useMemo(
    () => unique(videos.map((v) => v.contentType ?? "")),
    [videos],
  )
  const flagNames = useMemo(
    () => unique(videos.flatMap((v) => v.flags ?? [])),
    [videos],
  )

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const ch = channelQ.trim().toLowerCase()
    return videos.filter((v) => {
      if (!showRemoved && removedIds.includes(v.videoId)) return false
      if (needle && !(v.searchBlob || "").toLowerCase().includes(needle))
        return false
      if (category && v.category !== category) return false
      if (subCategory && v.subCategory !== subCategory) return false
      if (ch && !(v.channel || "").toLowerCase().includes(ch)) return false
      if (bucket && v.durationBucket !== bucket) return false
      if (availability && v.availability !== availability) return false
      if (watched === "yes" && !v.watched) return false
      if (watched === "no" && v.watched) return false
      if (hint && !(v.removeHints ?? []).includes(hint)) return false
      if (easyOnly && v.removePriority > 3) return false
      if (hebrewOnly && !v.hasHebrew) return false
      if (recAction && v.recommendedAction !== recAction) return false
      if (contentType && v.contentType !== contentType) return false
      if (flag && !(v.flags ?? []).includes(flag)) return false
      const action = triage[v.videoId]?.action
      if (saved === "unset" && action) return false
      if (saved && saved !== "unset" && action !== saved) return false
      return true
    })
  }, [
    videos,
    q,
    category,
    subCategory,
    channelQ,
    bucket,
    availability,
    watched,
    hint,
    easyOnly,
    hebrewOnly,
    recAction,
    contentType,
    flag,
    saved,
    triage,
    removedIds,
    showRemoved,
  ])

  const sorted = useMemo(
    () => [...filtered].sort((a, b) => cmp(a, b, sort)),
    [filtered, sort],
  )

  const rows: Row[] = useMemo(() => {
    if (groupBy === "none")
      return sorted.map((video) => ({ kind: "video", video }))
    const groups = new Map<string, Video[]>()
    for (const v of sorted) {
      const key = groupValue(v, groupBy, triage)
      const list = groups.get(key)
      if (list) list.push(v)
      else groups.set(key, [v])
    }
    const out: Row[] = []
    for (const [key, list] of groups) {
      const sec = list.reduce((s, v) => s + (v.durationSeconds ?? 0), 0)
      out.push({ kind: "group", key, n: list.length, hours: hours(sec) })
      for (const video of list) out.push({ kind: "video", video })
    }
    return out
  }, [sorted, groupBy, triage])

  const cols = Math.max(
    1,
    Math.floor((width - 28) / (CARD_MIN[thumb] + 12)),
  )
  const packed = useMemo(
    () => packRows(rows, view, cols),
    [rows, view, cols],
  )

  const virtualizer = useVirtualizer({
    count: packed.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (i) => {
      const item = packed[i]
      if (!item || item.kind === "group") return 40
      if (item.kind === "list") return LIST_H[thumb] + (narrow ? 80 : 0)
      return GRID_H[thumb]
    },
    overscan: 8,
  })
  useEffect(() => {
    virtualizer.measure()
  }, [view, thumb, cols, packed.length, narrow])

  const shownHours = hours(
    sorted.reduce((s, v) => s + (v.durationSeconds ?? 0), 0),
  )
  const counts = useMemo(() => {
    const c = { remove: 0, keep: 0, later: 0 }
    for (const t of Object.values(triage)) {
      if (t.action in c) c[t.action] += 1
    }
    return c
  }, [triage])

  const filterCount = [
    category,
    subCategory,
    channelQ,
    bucket,
    availability,
    watched,
    hint,
    saved,
    recAction,
    contentType,
    flag,
    easyOnly,
    hebrewOnly,
    groupBy !== "none",
  ].filter(Boolean).length

  function patch(id: string, next: Partial<Triage> & { action?: Action | null }) {
    setTriage((prev) => {
      const copy = { ...prev }
      if (next.action === null) {
        delete copy[id]
        return copy
      }
      const cur = copy[id] ?? { ...EMPTY, action: "remove", priority: 5, note: "" }
      copy[id] = { ...cur, ...next, action: next.action ?? cur.action }
      return copy
    })
  }

  function setAction(id: string, action: Action) {
    setTriage((prev) => {
      const copy = { ...prev }
      if (copy[id]?.action === action) {
        delete copy[id]
        return copy
      }
      copy[id] = { ...(copy[id] ?? EMPTY), action }
      return copy
    })
  }

  function markVisible(action: Action) {
    setTriage((prev) => {
      const copy = { ...prev }
      for (const v of sorted) {
        copy[v.videoId] = { ...(copy[v.videoId] ?? EMPTY), action }
      }
      return copy
    })
  }

  function applyPlaylist(rows: Video[], label: string) {
    if (!rows.length) {
      setCopied("no videos")
      setTimeout(() => setCopied(""), 2000)
      return
    }
    setVideos(rows)
    try {
      savePlaylist(rows)
    } catch {
      setCopied("loaded · storage full")
      setTimeout(() => setCopied(""), 2500)
      return
    }
    setCopied(label)
    setTimeout(() => setCopied(""), 2500)
  }

  function onImport(file: File) {
    file.text().then((text) => {
      const trimmed = text.trim()
      if (!trimmed) return
      if (looksLikePlaylist(trimmed) || trimmed.includes('"videoId"')) {
        try {
          const rows = parsePlaylistText(trimmed)
          if (rows.length) {
            applyPlaylist(rows, `imported ${rows.length}`)
            return
          }
        } catch {
          /* fall through */
        }
      }
      const parsed: unknown = JSON.parse(trimmed)
      if (!parsed || typeof parsed !== "object") return
      const rec = parsed as Record<string, unknown>
      if (Array.isArray(rec.removedVideoIds)) {
        const extra = rec.removedVideoIds.filter((x) => typeof x === "string")
        setRemovedIds((prev) => [...new Set([...prev, ...extra])])
        setCopied(`imported ${extra.length} removed`)
        setTimeout(() => setCopied(""), 2500)
        return
      }
      const inner = rec.triage
      const map = (
        inner && typeof inner === "object" && !("action" in inner)
          ? inner
          : parsed
      ) as TriageMap
      setTriage(map)
    })
  }

  async function pullPlaylist() {
    try {
      const text = await navigator.clipboard.readText()
      const rows = parsePlaylistText(text)
      applyPlaylist(rows, `pulled ${rows.length}`)
    } catch (err) {
      setCopied(err instanceof Error ? err.message : "clipboard blocked")
      setTimeout(() => setCopied(""), 2500)
    }
  }

  function acceptRecs() {
    const gone = new Set(removedIds)
    let del = 0
    let keep = 0
    let skippedGoal = 0
    let skippedSet = 0
    for (const v of videos) {
      if (gone.has(v.videoId)) continue
      if (triage[v.videoId]) {
        skippedSet += 1
        continue
      }
      const highFit = (v.flags ?? []).includes("high_goal_fit")
      if (v.recommendedAction === "deleteCandidate") {
        if (highFit) {
          skippedGoal += 1
          continue
        }
        del += 1
      } else if (v.recommendedAction === "watchSoon") {
        keep += 1
      }
    }
    if (!del && !keep) {
      setCopied("nothing to accept")
      setTimeout(() => setCopied(""), 2000)
      return
    }
    const ok = confirm(
      `Mark ${del} deleteCandidate as remove and ${keep} watchSoon as keep?\nSkipped ${skippedGoal} high_goal_fit, ${skippedSet} already decided.`,
    )
    if (!ok) return
    setTriage((prev) => {
      const copy = { ...prev }
      for (const v of videos) {
        if (gone.has(v.videoId) || copy[v.videoId]) continue
        const highFit = (v.flags ?? []).includes("high_goal_fit")
        if (v.recommendedAction === "deleteCandidate" && !highFit) {
          copy[v.videoId] = { ...EMPTY, action: "remove" }
        } else if (v.recommendedAction === "watchSoon") {
          copy[v.videoId] = { ...EMPTY, action: "keep" }
        }
      }
      return copy
    })
  }

  function clearFilters() {
    setQ("")
    setCategory("")
    setSubCategory("")
    setChannelQ("")
    setBucket("")
    setAvailability("")
    setWatched("")
    setHint("")
    setSaved("")
    setRecAction("")
    setContentType("")
    setFlag("")
    setEasyOnly(false)
    setHebrewOnly(false)
    setGroupBy("none")
    setSort("position")
  }

  function applyInsightFilter(f: InsightFilter) {
    clearFilters()
    if (f.recommendedAction) setRecAction(f.recommendedAction)
    if (f.contentType) setContentType(f.contentType)
    if (f.flag) setFlag(f.flag)
    if (f.category) setCategory(f.category)
    if (f.subCategory) setSubCategory(f.subCategory)
    if (f.channel) setChannelQ(f.channel)
    if (f.durationBucket) setBucket(f.durationBucket)
    if (f.availability) setAvailability(f.availability)
    if (f.watched) setWatched(f.watched)
    setScreen("browse")
    setFiltersOpen(true)
  }

  function copyRemoveIds() {
    const gone = new Set(removedIds)
    const videoIds = Object.entries(triage)
      .filter(([id, t]) => t.action === "remove" && !gone.has(id))
      .map(([id]) => id)
    const payload = JSON.stringify({ videoIds }, null, 2)
    navigator.clipboard.writeText(payload).then(() => {
      setCopied(`${videoIds.length} ids`)
      setTimeout(() => setCopied(""), 2000)
    })
    downloadJson("watchlater-remove-ids.json", { videoIds })
  }
  if (error) return <p className="error">{error}</p>

  const userscriptHref = `${import.meta.env.BASE_URL}watchlater-remove.user.js`

  return (
    <div className="app">
      <header className="mast">
        <div>
          <p className="kicker">Watch later</p>
          <h1 className="wordmark">Triage</h1>
        </div>
        <p className="mast-meta">
          {videos.length
            ? "Local triage. Userscript exports the playlist and clicks YouTube Remove."
            : "Install the userscript, open a YouTube playlist, Export, then Pull playlist."}
        </p>
      </header>

      <div className="chrome">
        <div className="chrome-right">
          <div className="seg" role="group" aria-label="screen">
            <button
              type="button"
              className={screen === "browse" ? "on" : ""}
              onClick={() => setScreen("browse")}
            >
              browse
            </button>
            <button
              type="button"
              className={screen === "analytics" ? "on" : ""}
              onClick={() => setScreen("analytics")}
            >
              analytics
            </button>
          </div>
          <button
            type="button"
            className={`pill${settingsOpen ? " on" : ""}`}
            onClick={() => setSettingsOpen(true)}
          >
            settings
          </button>
          <button type="button" className="pill" onClick={pullPlaylist}>
            {copied.startsWith("pulled") ? copied : "pull playlist"}
          </button>
          {screen === "browse" && (
            <>
              <div className="seg" role="group" aria-label="view">
                <button
                  type="button"
                  className={view === "list" ? "on" : ""}
                  onClick={() => setView("list")}
                >
                  list
                </button>
                <button
                  type="button"
                  className={view === "grid" ? "on" : ""}
                  onClick={() => setView("grid")}
                >
                  grid
                </button>
              </div>
              <button
                type="button"
                className={`pill${searchOpen ? " on" : ""}`}
                aria-expanded={searchOpen}
                onClick={() => setSearchOpen((o) => !o)}
              >
                search{q ? ` · ${q.length > 16 ? `${q.slice(0, 16)}…` : q}` : ""}
              </button>
              <button
                type="button"
                className={`pill${filtersOpen ? " on" : ""}`}
                aria-expanded={filtersOpen}
                onClick={() => setFiltersOpen((o) => !o)}
              >
                filters{filterCount ? ` · ${filterCount}` : ""}
              </button>
              {filterCount > 0 && (
                <button type="button" className="pill" onClick={clearFilters}>
                  clear
                </button>
              )}
              <button
                type="button"
                className={`pill${recAction === "deleteCandidate" ? " on" : ""}`}
                onClick={() =>
                  setRecAction((a) =>
                    a === "deleteCandidate" ? "" : "deleteCandidate",
                  )
                }
              >
                delete
              </button>
              <button
                type="button"
                className={`pill${recAction === "peek1m" ? " on" : ""}`}
                onClick={() =>
                  setRecAction((a) => (a === "peek1m" ? "" : "peek1m"))
                }
              >
                peek
              </button>
              <button
                type="button"
                className={`pill${recAction === "watchSoon" ? " on" : ""}`}
                onClick={() =>
                  setRecAction((a) => (a === "watchSoon" ? "" : "watchSoon"))
                }
              >
                watch soon
              </button>
            </>
          )}
        </div>
      </div>
      {screen === "analytics" ? (
        <Analytics videos={videos} onApply={applyInsightFilter} />
      ) : (
        <>
      <div className={`search-panel${searchOpen ? " open" : ""}`}>
        <div className="search-panel-inner">
          <label className="field search">
            search
            <input
              ref={searchRef}
              type="search"
              placeholder="title, channel, id…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
        </div>
      </div>


      <div className={`filters${filtersOpen ? " open" : ""}`}>
        <div className="filters-inner">
          <div className="toolbar">
            <label className="field">
              category
              <select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value)
                  setSubCategory("")
                }}
              >
                <option value="">all</option>
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="field">
              sub
              <select
                value={subCategory}
                onChange={(e) => setSubCategory(e.target.value)}
              >
                <option value="">all</option>
                {subCategories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="field">
              channel
              <input
                type="text"
                placeholder="contains…"
                value={channelQ}
                onChange={(e) => setChannelQ(e.target.value)}
              />
            </label>
            <label className="field">
              length
              <select
                value={bucket}
                onChange={(e) => setBucket(e.target.value)}
              >
                <option value="">all</option>
                {buckets.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="field">
              avail
              <select
                value={availability}
                onChange={(e) => setAvailability(e.target.value)}
              >
                <option value="">all</option>
                <option value="ok">ok</option>
                <option value="private">private</option>
                <option value="deleted">deleted</option>
                <option value="unavailable">unavailable</option>
              </select>
            </label>
            <label className="field">
              watched
              <select
                value={watched}
                onChange={(e) => setWatched(e.target.value)}
              >
                <option value="">all</option>
                <option value="yes">yes</option>
                <option value="no">no</option>
              </select>
            </label>
            <label className="field">
              hint
              <select value={hint} onChange={(e) => setHint(e.target.value)}>
                <option value="">all</option>
                {hints.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="field">
              saved
              <select value={saved} onChange={(e) => setSaved(e.target.value)}>
                <option value="">all</option>
                <option value="unset">unset</option>
                <option value="remove">remove</option>
                <option value="keep">keep</option>
                <option value="later">later</option>
              </select>
            </label>
            <label className="field">
              rec action
              <select
                value={recAction}
                onChange={(e) => setRecAction(e.target.value)}
              >
                <option value="">all</option>
                {recActions.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="field">
              type
              <select
                value={contentType}
                onChange={(e) => setContentType(e.target.value)}
              >
                <option value="">all</option>
                {contentTypes.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="field">
              flag
              <select value={flag} onChange={(e) => setFlag(e.target.value)}>
                <option value="">all</option>
                {flagNames.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={easyOnly}
                onChange={(e) => setEasyOnly(e.target.checked)}
              />
              easy remove
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={hebrewOnly}
                onChange={(e) => setHebrewOnly(e.target.checked)}
              />
              Hebrew
            </label>
            <label className="field">
              sort
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
              >
                <option value="position">position</option>
                <option value="deleteScore">delete score</option>
                <option value="estimatedValue">est. value</option>
                <option value="efficiencyScore">efficiency</option>
                <option value="removePriority">remove priority</option>
                <option value="duration">duration</option>
                <option value="views">views</option>
                <option value="watchedPercent">watched %</option>
                <option value="title">title</option>
              </select>
            </label>
            <label className="field">
              group
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as GroupBy)}
              >
                <option value="none">none</option>
                <option value="recommendedAction">rec action</option>
                <option value="contentType">type</option>
                <option value="category">category</option>
                <option value="subCategory">subcategory</option>
                <option value="channel">channel</option>
                <option value="durationBucket">length</option>
                <option value="availability">availability</option>
                <option value="action">saved action</option>
              </select>
            </label>
          </div>
        </div>
      </div>

      <div className="stats">
        <div className="stat">
          <b>{sorted.length}</b>
          <span>of {videos.length}</span>
        </div>
        <div className="stat">
          <b>{shownHours}</b>
          <span>hours</span>
        </div>
        <div className="stat remove">
          <b>{counts.remove}</b>
          <span>remove</span>
        </div>
        <div className="stat keep">
          <b>{counts.keep}</b>
          <span>keep</span>
        </div>
        <div className="stat later">
          <b>{counts.later}</b>
          <span>later</span>
        </div>
        <div className="stat">
          <b>{removedIds.length}</b>
          <span>gone on YT</span>
        </div>
        <button type="button" className="pill" onClick={acceptRecs}>
          accept recs
        </button>
        <label className="toggle">
          <input
            type="checkbox"
            checked={showRemoved}
            onChange={(e) => setShowRemoved(e.target.checked)}
          />
          show removed
        </label>
        <button
          type="button"
          className="pill danger"
          onClick={() => markVisible("remove")}
        >
          mark visible remove
        </button>
        <button type="button" className="pill" onClick={() => markVisible("keep")}>
          mark visible keep
        </button>
        <button
          type="button"
          className="pill"
          onClick={() =>
            downloadJson("watchlater-triage.json", {
              exportedAt: new Date().toISOString(),
              triage,
            })
          }
        >
          export
        </button>
        <button type="button" className="pill" onClick={() => importRef.current?.click()}>
          import
        </button>
        <button type="button" className="pill danger" onClick={copyRemoveIds}>
          {copied || "copy remove ids"}
        </button>
        <a className="pill" href={userscriptHref} download>
          userscript
        </a>
        <input
          ref={importRef}
          type="file"
          accept="application/json,.jsonl,text/plain"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onImport(file)
            e.target.value = ""
          }}
        />
      </div>

      <main
        className="list"
        ref={parentRef}
        data-view={view}
        data-thumb={thumb}
      >
        <div
          style={{
            height: virtualizer.getTotalSize(),
            width: "100%",
            position: "relative",
          }}
        >
          {virtualizer.getVirtualItems().map((item) => {
            const row = packed[item.index]
            const pos = {
              height: item.size,
              transform: `translateY(${item.start}px)`,
            }
            if (row.kind === "group") {
              return (
                <div key={item.key} className="group" style={pos}>
                  {row.key}
                  <span>
                    {row.n} · {row.hours} h
                  </span>
                </div>
              )
            }
            if (row.kind === "list") {
              return (
                <article
                  key={item.key}
                  className={`row${triage[row.video.videoId] ? ` ${triage[row.video.videoId].action}` : ""}`}
                  style={pos}
                >
                  <VideoTile
                    video={row.video}
                    layout="list"
                    thumb={thumb}
                    triage={triage[row.video.videoId]}
                    onAction={setAction}
                    onPatch={patch}
                  />
                </article>
              )
            }
            return (
              <div key={item.key} className="row cards" style={pos}>
                <div
                  className="card-row"
                  style={{ gridTemplateColumns: `repeat(${row.videos.length}, 1fr)` }}
                >
                  {row.videos.map((v) => (
                    <article
                      key={v.videoId}
                      className={`card${triage[v.videoId] ? ` ${triage[v.videoId].action}` : ""}`}
                    >
                      <VideoTile
                        video={v}
                        layout="grid"
                        thumb={thumb}
                        triage={triage[v.videoId]}
                        onAction={setAction}
                        onPatch={patch}
                      />
                    </article>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </main>
        </>
      )}
      {settingsOpen && (
        <div
          className="modal-backdrop"
          onClick={() => setSettingsOpen(false)}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="settings-title">Settings</h2>
              <button
                type="button"
                className="pill"
                onClick={() => setSettingsOpen(false)}
              >
                close
              </button>
            </div>

            <h3>Color scheme</h3>
            <div className="scheme-grid" role="radiogroup" aria-label="color scheme">
              {SCHEME_UI.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={scheme === s.id}
                  className={`scheme-card${scheme === s.id ? " on" : ""}`}
                  onClick={() => setScheme(s.id)}
                >
                  <i style={{ background: s.swatch }} />
                  {s.label}
                </button>
              ))}
            </div>

            <h3>Text size</h3>
            <div className="text-size" role="group" aria-label="text size">
              <button
                type="button"
                className="pill"
                disabled={fontScale <= FONT_MIN}
                onClick={() => setFontScale((n) => clampFontScale(n - 1))}
              >
                A−
              </button>
              <b>{fontScale}px</b>
              <button
                type="button"
                className="pill"
                disabled={fontScale >= FONT_MAX}
                onClick={() => setFontScale((n) => clampFontScale(n + 1))}
              >
                A+
              </button>
            </div>

            <h3>Thumbnails</h3>
            <div className="seg" role="group" aria-label="thumbnail size">
              {(["s", "m", "l"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={thumb === s ? "on" : ""}
                  onClick={() => setThumb(s)}
                >
                  {s === "s" ? "small" : s === "m" ? "medium" : "large"}
                </button>
              ))}
            </div>

            <h3>Data</h3>
            <button
              type="button"
              className="pill"
              onClick={() => {
                clearPlaylist()
                setVideos([])
                setCopied("cleared local playlist")
                setTimeout(() => setCopied(""), 2000)
              }}
            >
              clear local playlist
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function VideoTile({
  video: v,
  layout,
  thumb,
  triage: t,
  onAction,
  onPatch,
}: {
  video: Video
  layout: ViewMode
  thumb: ThumbSize
  triage?: Triage
  onAction: (id: string, action: Action) => void
  onPatch: (id: string, next: Partial<Triage> & { action?: Action | null }) => void
}) {
  return (
    <div className={layout === "list" ? "row-inner" : "card-inner"}>
      {v.availability === "ok" ? (
        <a
          className="thumb-wrap"
          href={watchUrl(v.videoId, v.resumeSeconds)}
          target="_blank"
          rel="noreferrer"
          aria-label={`Watch ${v.title}`}
        >
          <img
            src={thumbUrl(v.videoId, thumb)}
            alt=""
            loading="lazy"
            decoding="async"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
          <span className="play" aria-hidden>
            ▶
          </span>
          {v.watchedPercent != null ? (
            <i
              className="thumb-bar"
              style={{ width: `${Math.min(100, v.watchedPercent)}%` }}
            />
          ) : null}
        </a>
      ) : (
        <div className="thumb-wrap">
          <div className="ph">{v.availability}</div>
        </div>
      )}
      <div className="meta">
        <h2 dir="auto">
          <a
            href={watchUrl(v.videoId, v.resumeSeconds)}
            target="_blank"
            rel="noreferrer"
          >
            {v.title}
          </a>
        </h2>
        <div className="sub">
          {v.channel || "—"} · {v.duration ?? "?"} · #{v.position}
          {v.viewsText ? ` · ${v.viewsText}` : ""}
          {v.publishedAgo ? ` · ${v.publishedAgo}` : ""}
          {v.deleteScore != null ? ` · del ${v.deleteScore}` : ""}
          {v.estimatedValue != null ? ` · val ${v.estimatedValue}` : ""}
        </div>
        {v.triageReason ? (
          <div className="reason">{v.triageReason}</div>
        ) : null}
        <div className="chips">
          {v.recommendedAction ? (
            <span className={`chip rec-${v.recommendedAction}`}>
              {v.recommendedAction}
            </span>
          ) : null}
          {v.contentType && v.contentType !== "other" ? (
            <span className="chip">{v.contentType}</span>
          ) : null}
          <span className="chip">
            {v.category} / {v.subCategory}
          </span>
          {v.watched && (
            <span className="chip watch">
              watched
              {v.watchedPercent != null ? ` ${v.watchedPercent}%` : ""}
            </span>
          )}
          {(v.flags ?? []).slice(0, 3).map((h) => (
            <span key={h} className="chip bad">
              {h}
            </span>
          ))}
        </div>
      </div>
      <div className="triage">
        <div className="btns">
          {(["remove", "keep", "later"] as const).map((a) => (
            <button
              key={a}
              type="button"
              className={t?.action === a ? `on-${a}` : ""}
              onClick={() => onAction(v.videoId, a)}
            >
              {a}
            </button>
          ))}
        </div>
        <div className="row2">
          <input
            type="number"
            min={0}
            max={9}
            value={t?.priority ?? ""}
            placeholder="prio"
            onChange={(e) =>
              onPatch(v.videoId, {
                action: t?.action ?? "later",
                priority: Number(e.target.value),
              })
            }
          />
          <input
            type="text"
            placeholder="note"
            value={t?.note ?? ""}
            onChange={(e) =>
              onPatch(v.videoId, {
                action: t?.action ?? "later",
                note: e.target.value,
              })
            }
          />
        </div>
      </div>
    </div>
  )
}

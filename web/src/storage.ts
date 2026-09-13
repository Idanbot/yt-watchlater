import type { ColorScheme, TriageMap, Video, ViewPrefs } from "./types"
import { COLOR_SCHEMES } from "./types"

const KEY = "yt-wl-triage-v1"
const VIEW_KEY = "yt-wl-view-v1"
const REMOVED_KEY = "yt-wl-removed-on-yt-v1"
const PLAYLIST_KEY = "yt-wl-playlist-v1"

const DEFAULT_VIEW: ViewPrefs = {
  view: "list",
  thumb: "m",
  filtersOpen: true,
  scheme: "ember",
  fontScale: 14,
}

export const FONT_MIN = 12
export const FONT_MAX = 20

export function clampFontScale(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(n)) return DEFAULT_VIEW.fontScale
  return Math.min(FONT_MAX, Math.max(FONT_MIN, Math.round(n)))
}

function isScheme(value: unknown): value is ColorScheme {
  return (
    typeof value === "string" &&
    (COLOR_SCHEMES as readonly string[]).includes(value)
  )
}

export function loadTriage(): TriageMap {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as TriageMap
    return parsed && typeof parsed === "object" ? parsed : {}
  } catch {
    return {}
  }
}

export function saveTriage(map: TriageMap): void {
  localStorage.setItem(KEY, JSON.stringify(map))
}

export function loadViewPrefs(): ViewPrefs {
  try {
    const raw = localStorage.getItem(VIEW_KEY)
    if (!raw) return DEFAULT_VIEW
    const parsed = JSON.parse(raw) as Partial<ViewPrefs>
    return {
      view: parsed.view === "grid" ? "grid" : "list",
      thumb: parsed.thumb === "s" || parsed.thumb === "l" ? parsed.thumb : "m",
      filtersOpen: parsed.filtersOpen !== false,
      scheme: isScheme(parsed.scheme) ? parsed.scheme : "ember",
      fontScale: clampFontScale(parsed.fontScale),
    }
  } catch {
    return DEFAULT_VIEW
  }
}

export function saveViewPrefs(prefs: ViewPrefs): void {
  localStorage.setItem(VIEW_KEY, JSON.stringify(prefs))
}

export function loadRemovedIds(): string[] {
  try {
    const raw = localStorage.getItem(REMOVED_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed)
      ? parsed.filter((x) => typeof x === "string")
      : []
  } catch {
    return []
  }
}

export function saveRemovedIds(ids: string[]): void {
  localStorage.setItem(REMOVED_KEY, JSON.stringify([...new Set(ids)]))
}

export function loadPlaylist(): Video[] | null {
  try {
    const raw = localStorage.getItem(PLAYLIST_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed) || !parsed.length) return null
    return parsed as Video[]
  } catch {
    return null
  }
}

export function savePlaylist(videos: Video[]): void {
  localStorage.setItem(PLAYLIST_KEY, JSON.stringify(videos))
}

export function clearPlaylist(): void {
  localStorage.removeItem(PLAYLIST_KEY)
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

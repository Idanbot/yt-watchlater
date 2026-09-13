import type { Video } from "./types"

const HEBREW = /[\u0590-\u05FF]/

export function parseDurationSeconds(text: string | null | undefined): number | null {
  if (!text) return null
  const parts = text.trim().split(":")
  if (!parts.length || parts.some((p) => !/^\d+$/.test(p))) return null
  const nums = parts.map(Number)
  if (nums.length === 3) return nums[0] * 3600 + nums[1] * 60 + nums[2]
  if (nums.length === 2) return nums[0] * 60 + nums[1]
  if (nums.length === 1) return nums[0]
  return null
}

export function durationBucket(seconds: number | null): string {
  if (seconds == null) return "unknown"
  if (seconds < 60) return "<1m"
  if (seconds < 5 * 60) return "1-5m"
  if (seconds < 12 * 60) return "5-12m"
  if (seconds < 20 * 60) return "12-20m"
  if (seconds < 40 * 60) return "20-40m"
  if (seconds < 60 * 60) return "40-60m"
  if (seconds < 2 * 3600) return "1-2h"
  return "2h+"
}

function videoIdOf(raw: Record<string, unknown>): string | null {
  if (typeof raw.videoId === "string" && raw.videoId.length >= 11) {
    return raw.videoId.slice(0, 11)
  }
  const url = typeof raw.url === "string" ? raw.url : ""
  const m = url.match(/[?&]v=([\w-]{11})/)
  return m ? m[1] : null
}

export function normalizeVideo(
  raw: Record<string, unknown>,
  index: number,
): Video | null {
  const videoId = videoIdOf(raw)
  if (!videoId) return null
  const title = typeof raw.title === "string" ? raw.title : ""
  const channel = typeof raw.channel === "string" ? raw.channel : ""
  const duration = typeof raw.duration === "string" ? raw.duration : null
  const durationSeconds =
    typeof raw.durationSeconds === "number"
      ? raw.durationSeconds
      : parseDurationSeconds(duration)
  const category = typeof raw.category === "string" ? raw.category : "Other"
  const subCategory =
    typeof raw.subCategory === "string" ? raw.subCategory : "General"
  const url =
    typeof raw.url === "string" && raw.url
      ? raw.url
      : `https://www.youtube.com/watch?v=${videoId}`
  const availability =
    title === "[Private video]"
      ? "private"
      : title === "[Deleted video]"
        ? "deleted"
        : title === "[Unavailable video]"
          ? "unavailable"
          : "ok"
  return {
    position:
      typeof raw.position === "number" && raw.position > 0
        ? raw.position
        : index + 1,
    videoId,
    title,
    url,
    channel,
    channelHandle:
      typeof raw.channelHandle === "string" ? raw.channelHandle : null,
    duration,
    durationSeconds,
    durationBucket:
      typeof raw.durationBucket === "string"
        ? raw.durationBucket
        : durationBucket(durationSeconds),
    category,
    subCategory,
    watched: Boolean(raw.watched),
    resumeSeconds:
      typeof raw.resumeSeconds === "number" ? raw.resumeSeconds : null,
    watchedPercent:
      typeof raw.watchedPercent === "number" ? raw.watchedPercent : null,
    remainingSeconds:
      typeof raw.remainingSeconds === "number" ? raw.remainingSeconds : null,
    viewsText: typeof raw.viewsText === "string" ? raw.viewsText : null,
    viewsApprox: typeof raw.viewsApprox === "number" ? raw.viewsApprox : null,
    publishedAgo:
      typeof raw.publishedAgo === "string" ? raw.publishedAgo : null,
    hasHebrew: HEBREW.test(title) || HEBREW.test(channel),
    availability:
      typeof raw.availability === "string" ? raw.availability : availability,
    isShort: Boolean(raw.isShort) || (durationSeconds != null && durationSeconds <= 60),
    removeHints: Array.isArray(raw.removeHints)
      ? raw.removeHints.filter((x) => typeof x === "string")
      : [],
    removePriority:
      typeof raw.removePriority === "number" ? raw.removePriority : 9,
    searchBlob: [title, channel, videoId, category, subCategory]
      .filter(Boolean)
      .join(" "),
    contentType: typeof raw.contentType === "string" ? raw.contentType : undefined,
    recommendedAction:
      typeof raw.recommendedAction === "string"
        ? raw.recommendedAction
        : undefined,
    triageReason:
      typeof raw.triageReason === "string" ? raw.triageReason : undefined,
    flags: Array.isArray(raw.flags)
      ? raw.flags.filter((x) => typeof x === "string")
      : undefined,
    personalRelevance:
      typeof raw.personalRelevance === "number" ? raw.personalRelevance : null,
    deleteScore: typeof raw.deleteScore === "number" ? raw.deleteScore : null,
    estimatedValue:
      typeof raw.estimatedValue === "number" ? raw.estimatedValue : null,
    efficiencyScore:
      typeof raw.efficiencyScore === "number" ? raw.efficiencyScore : null,
    redundancyRisk:
      typeof raw.redundancyRisk === "number" ? raw.redundancyRisk : null,
    analyzeBeforeDelete: Boolean(raw.analyzeBeforeDelete),
    deleteBand: typeof raw.deleteBand === "string" ? raw.deleteBand : undefined,
  }
}

export function parseJsonl(text: string): Record<string, unknown>[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>)
}

export function parsePlaylistText(text: string): Video[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  const lines = trimmed.split("\n").map((l) => l.trim()).filter(Boolean)
  if (lines.length > 1 && lines[0].startsWith("{") && !trimmed.startsWith("[")) {
    try {
      return parseJsonl(trimmed)
        .map((row, i) => normalizeVideo(row, i))
        .filter((v): v is Video => v != null)
    } catch {
      /* fall through to single JSON */
    }
  }
  if (trimmed.startsWith("[")) {
    const arr = JSON.parse(trimmed) as unknown
    if (!Array.isArray(arr)) return []
    return arr
      .map((row, i) =>
        row && typeof row === "object"
          ? normalizeVideo(row as Record<string, unknown>, i)
          : null,
      )
      .filter((v): v is Video => v != null)
  }
  if (trimmed.startsWith("{")) {
    const rec = JSON.parse(trimmed) as Record<string, unknown>
    const list = Array.isArray(rec.videos)
      ? rec.videos
      : Array.isArray(rec.videoIds)
        ? rec.videoIds.map((id, i) =>
            typeof id === "string" ? { videoId: id, position: i + 1 } : null,
          )
        : null
    if (list) {
      return list
        .map((row, i) =>
          row && typeof row === "object"
            ? normalizeVideo(row as Record<string, unknown>, i)
            : null,
        )
        .filter((v): v is Video => v != null)
    }
    if (typeof rec.videoId === "string") {
      const v = normalizeVideo(rec, 0)
      return v ? [v] : []
    }
    return []
  }
  return parseJsonl(trimmed)
    .map((row, i) => normalizeVideo(row, i))
    .filter((v): v is Video => v != null)
}

export function looksLikePlaylist(text: string): boolean {
  const t = text.trim()
  if (!t) return false
  if (t.startsWith("{")) {
    try {
      const rec = JSON.parse(t) as Record<string, unknown>
      return (
        rec.kind === "playlist" ||
        rec.source === "userscript" && Array.isArray(rec.videos) ||
        Array.isArray(rec.videos)
      )
    } catch {
      return false
    }
  }
  if (t.startsWith("[")) {
    try {
      const arr = JSON.parse(t) as unknown
      return (
        Array.isArray(arr) &&
        arr.some(
          (row) =>
            row &&
            typeof row === "object" &&
            ("videoId" in row || "url" in row),
        )
      )
    } catch {
      return false
    }
  }
  return t.includes('"videoId"')
}

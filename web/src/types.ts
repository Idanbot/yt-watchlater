export type Video = {
  position: number
  videoId: string
  title: string
  url: string
  channel: string
  channelHandle: string | null
  duration: string | null
  durationSeconds: number | null
  durationBucket: string
  category: string
  subCategory: string
  watched: boolean
  resumeSeconds: number | null
  watchedPercent: number | null
  remainingSeconds: number | null
  viewsText: string | null
  viewsApprox: number | null
  publishedAgo: string | null
  hasHebrew: boolean
  availability: string
  isShort: boolean
  removeHints: string[]
  removePriority: number
  searchBlob: string
  contentType?: string
  recommendedAction?: string
  triageReason?: string
  flags?: string[]
  personalRelevance?: number | null
  deleteScore?: number | null
  estimatedValue?: number | null
  efficiencyScore?: number | null
  redundancyRisk?: number | null
  analyzeBeforeDelete?: boolean
  deleteBand?: string
}

export type Action = "remove" | "keep" | "later"

export type Triage = {
  action: Action
  priority: number
  note: string
}

export type TriageMap = Record<string, Triage>

export type GroupBy =
  | "none"
  | "category"
  | "subCategory"
  | "channel"
  | "durationBucket"
  | "availability"
  | "action"
  | "recommendedAction"
  | "contentType"

export type SortKey =
  | "position"
  | "duration"
  | "views"
  | "watchedPercent"
  | "removePriority"
  | "title"
  | "deleteScore"
  | "estimatedValue"
  | "efficiencyScore"

export type InsightFilter = {
  recommendedAction?: string
  contentType?: string
  flag?: string
  category?: string
  subCategory?: string
  channel?: string
  durationBucket?: string
  availability?: string
  watched?: string
}

export type ViewMode = "list" | "grid"

export type ThumbSize = "s" | "m" | "l"

export const COLOR_SCHEMES = [
  "ember",
  "ink",
  "moss",
  "tide",
  "dusk",
  "paper",
  "noir",
] as const

export type ColorScheme = (typeof COLOR_SCHEMES)[number]

export type ViewPrefs = {
  view: ViewMode
  thumb: ThumbSize
  filtersOpen: boolean
  scheme: ColorScheme
  fontScale: number
}

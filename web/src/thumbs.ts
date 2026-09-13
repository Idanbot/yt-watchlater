/** Google's public thumbnail CDN. Not youtube.com scrape; no API key.
 *  mqdefault 320×180, hqdefault 480×360. Do not use scraped `sqp`/`rs` URLs.
 */
export type ThumbSize = "s" | "m" | "l"

export function thumbUrl(videoId: string, size: ThumbSize = "m"): string {
  const file = size === "l" ? "hqdefault.jpg" : "mqdefault.jpg"
  return `https://i.ytimg.com/vi/${videoId}/${file}`
}

export function watchUrl(videoId: string, resumeSeconds: number | null): string {
  const t = resumeSeconds && resumeSeconds > 0 ? `&t=${resumeSeconds}s` : ""
  return `https://www.youtube.com/watch?v=${videoId}&list=WL${t}`
}

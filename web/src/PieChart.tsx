export type Slice = { label: string; n: number; hours: number }

const COLORS = Array.from(
  { length: 11 },
  (_, i) => `var(--pie-${i + 1})`,
)

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = ((deg - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

function wedge(cx: number, cy: number, r: number, a0: number, a1: number) {
  if (a1 - a0 >= 359.9) {
    return `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy}`
  }
  const s = polar(cx, cy, r, a1)
  const e = polar(cx, cy, r, a0)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M ${cx} ${cy} L ${e.x} ${e.y} A ${r} ${r} 0 ${large} 1 ${s.x} ${s.y} Z`
}

export function PieChart({
  title,
  slices,
  metric,
}: {
  title: string
  slices: Slice[]
  metric: "n" | "hours"
}) {
  const total = slices.reduce((s, x) => s + (metric === "n" ? x.n : x.hours), 0) || 1
  let deg = 0
  const arcs = slices.map((slice, i) => {
    const value = metric === "n" ? slice.n : slice.hours
    const span = (value / total) * 360
    const d = wedge(50, 50, 42, deg, deg + span)
    deg += span
    return { d, color: COLORS[i % COLORS.length], slice, value }
  })

  return (
    <figure className="pie">
      <figcaption>{title}</figcaption>
      <div className="pie-body">
        <svg viewBox="0 0 100 100" className="pie-svg" aria-hidden>
          {arcs.map((a) => (
            <path key={a.slice.label} d={a.d} fill={a.color} />
          ))}
          <circle cx="50" cy="50" r="22" fill="var(--pie-hole)" />
        </svg>
        <ul className="pie-legend">
          {arcs.map((a) => (
            <li key={a.slice.label}>
              <i style={{ background: a.color }} />
              <span>{a.slice.label}</span>
              <b>
                {metric === "n"
                  ? a.slice.n
                  : `${a.slice.hours.toFixed(1)}h`}
              </b>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  )
}

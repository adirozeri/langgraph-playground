export default function LeanBadge({ lean }) {
  const cls = { INVEST: 'badge-invest', HOLD: 'badge-hold', AVOID: 'badge-avoid' }[lean] ?? 'badge-neutral'
  return <span className={`badge ${cls}`}>{lean ?? '—'}</span>
}

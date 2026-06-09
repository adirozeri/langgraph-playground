import { useNavigate } from 'react-router-dom'
import LeanBadge from './LeanBadge'
import ScoreBar from './ScoreBar'

const scoreClass = (s) => {
  const n = parseFloat(s)
  if (n >= 6) return 'score-high'
  if (n >= 4) return 'score-mid'
  return 'score-low'
}

const fmt = (v) => {
  if (v === 'UNAVAILABLE' || v == null) return '—'
  return parseFloat(v).toFixed(2)
}

export default function Leaderboard({ ranking, groupName, clickable = false }) {
  const navigate = useNavigate()
  if (!ranking?.members?.length) return <p style={{ color: 'var(--text-dim)' }}>No data yet.</p>

  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Ticker</th>
          <th>Composite</th>
          <th>Income</th>
          <th>Momentum</th>
          <th>Valuation</th>
          <th>Capital</th>
          <th>Lean</th>
        </tr>
      </thead>
      <tbody>
        {ranking.members.map((m) => (
          <tr
            key={m.ticker}
            style={clickable ? { cursor: 'pointer' } : {}}
            onClick={clickable ? () => navigate(`/groups/${groupName}/company/${m.ticker}`) : undefined}
          >
            <td style={{ color: 'var(--text-dim)', width: 32 }}>{m.rank}</td>
            <td style={{ fontWeight: 700, color: 'var(--blue)' }}>{m.ticker}</td>
            <td><ScoreBar score={m.composite} /></td>
            <td><span className={scoreClass(m.income)}>{fmt(m.income)}</span></td>
            <td><span className={scoreClass(m.momentum)}>{fmt(m.momentum)}</span></td>
            <td><span className={scoreClass(m.valuation)}>{fmt(m.valuation)}</span></td>
            <td><span className={scoreClass(m.capital)}>{fmt(m.capital)}</span></td>
            <td><LeanBadge lean={m.lean} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

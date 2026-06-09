import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LeanBadge from './LeanBadge'
import ScoreBar from './ScoreBar'
import styles from './CompanySummaryCard.module.css'

const SIGNAL_ARROW = { POSITIVE: '↑', NEGATIVE: '↓', NEUTRAL: '→', UNAVAILABLE: '—' }
const SIGNAL_COLOR = { POSITIVE: 'var(--green)', NEGATIVE: 'var(--red)', NEUTRAL: 'var(--text-dim)', UNAVAILABLE: 'var(--text-muted)' }

const fmt = (v) => {
  if (!v || v === 'UNAVAILABLE') return '—'
  const n = parseFloat(v)
  return isNaN(n) ? v : n.toFixed(2)
}

export default function CompanySummaryCard({ rank, ticker, decision, groupName }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  if (!decision) return null
  const { lean, scorecard: sc, valuation_position: vp, soft_signals: ss, justification } = decision

  return (
    <div className={styles.card}>
      <div className={styles.header} onClick={() => setOpen(o => !o)}>
        <div className={styles.left}>
          <span className={styles.rank}>#{rank}</span>
          <span className={styles.ticker}>{ticker}</span>
          <LeanBadge lean={lean} />
        </div>
        <div className={styles.right}>
          <ScoreBar score={sc?.composite} showBar={false} />
          <span className={styles.chevron}>{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className={styles.body}>
          {/* Scorecard */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Scorecard</div>
            <table className={styles.inner}>
              <thead><tr><th>Pillar</th><th>Score</th><th>Verdict</th></tr></thead>
              <tbody>
                {['income','momentum','valuation','capital'].map(p => (
                  <tr key={p}>
                    <td style={{ textTransform: 'capitalize' }}>{p}</td>
                    <td><ScoreBar score={sc?.[p]?.score} showBar={false} /></td>
                    <td style={{ color: 'var(--text-dim)', fontSize: 12 }}>{sc?.[p]?.verdict}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Valuation vs history */}
          {vp && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Valuation vs Own History</div>
              <p style={{ fontSize: 13 }}>
                <strong>{vp.position}</strong> — current P/E {fmt(vp.current_pe)}×
                &nbsp;vs hist. median {fmt(vp.historical_median_pe)}×
              </p>
            </div>
          )}

          {/* Soft signals */}
          {ss && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Soft Signals</div>
              <div className={styles.signals}>
                {[
                  { label: 'Insider',    dir: ss.insider_activity,   detail: ss.insider_detail },
                  { label: 'Revisions',  dir: ss.estimate_revisions, detail: ss.revision_detail },
                  { label: 'Buybacks',   dir: ss.buyback_activity,   detail: ss.buyback_detail },
                ].map(({ label, dir, detail }) => (
                  <div key={label} className={styles.signal}>
                    <span className={styles.signalArrow} style={{ color: SIGNAL_COLOR[dir] }}>
                      {SIGNAL_ARROW[dir]}
                    </span>
                    <span className={styles.signalLabel}>{label}</span>
                    <span className={styles.signalDetail}>{detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Rationale */}
          {justification && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Rationale</div>
              <p className={styles.rationale}>{justification}</p>
            </div>
          )}

          <button
            className="btn-ghost"
            style={{ marginTop: 8, fontSize: 12 }}
            onClick={() => navigate(`/groups/${groupName}/company/${ticker}`)}
          >
            Full analysis →
          </button>
        </div>
      )}
    </div>
  )
}

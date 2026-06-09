import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { fetchCompanyResult } from '../api/client'
import LeanBadge from '../components/LeanBadge'
import ScoreBar from '../components/ScoreBar'
import styles from './CompanyDetail.module.css'

const SIGNAL_ARROW = { POSITIVE: '↑', NEGATIVE: '↓', NEUTRAL: '→', UNAVAILABLE: '—' }
const SIGNAL_COLOR = { POSITIVE: 'var(--green)', NEGATIVE: 'var(--red)', NEUTRAL: 'var(--text-dim)', UNAVAILABLE: 'var(--text-muted)' }

const fmt = (v) => {
  if (!v || v === 'UNAVAILABLE') return '—'
  const n = parseFloat(v)
  return isNaN(n) ? v : n.toFixed(2)
}
const fmtPct = (v) => {
  if (!v || v === 'UNAVAILABLE') return '—'
  const n = parseFloat(v)
  return isNaN(n) ? v : `${(n * 100).toFixed(1)}%`
}

export default function CompanyDetail() {
  const { name, ticker } = useParams()
  const { data: dec, isLoading, error } = useQuery({
    queryKey: ['company', name, ticker],
    queryFn: () => fetchCompanyResult(name, ticker),
    retry: false,
  })

  if (isLoading) return <div className="page"><div className="spinner" /></div>
  if (error) return <div className="page"><div className="empty-state"><h3>No data found</h3></div></div>

  const { lean, scorecard: sc, valuation_position: vp, projection, soft_signals: ss, justification, caveat_quality_not_timing, caveat_projection_not_guaranteed, caveat_garbage_in_garbage_out } = dec

  return (
    <div className="page">
      {/* Breadcrumb */}
      <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>
        <Link to="/">Dashboard</Link> / <Link to={`/groups/${name}`}>{name}</Link> / {ticker}
      </div>

      {/* Header */}
      <div className="flex items-center gap-16" style={{ marginBottom: 24 }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>{ticker}</h1>
        <LeanBadge lean={lean} />
        <ScoreBar score={sc?.composite} showBar={false} />
      </div>

      <div className={styles.grid}>
        {/* Scorecard */}
        <div className="card">
          <div className={styles.cardTitle}>Scorecard</div>
          <table>
            <thead><tr><th>Pillar</th><th>Score</th><th>Verdict</th></tr></thead>
            <tbody>
              {['income','momentum','valuation','capital'].map(p => (
                <tr key={p}>
                  <td style={{ textTransform: 'capitalize' }}>{p}</td>
                  <td style={{ width: 160 }}><ScoreBar score={sc?.[p]?.score} /></td>
                  <td style={{ color: 'var(--text-dim)', fontSize: 12 }}>{sc?.[p]?.verdict}</td>
                </tr>
              ))}
              <tr style={{ borderTop: '2px solid var(--border)' }}>
                <td><strong>Composite</strong></td>
                <td><ScoreBar score={sc?.composite} /></td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>

        {/* Valuation */}
        {vp && (
          <div className="card">
            <div className={styles.cardTitle}>Valuation vs Own History</div>
            <table>
              <tbody>
                <tr><td>Position</td><td><strong>{vp.position}</strong></td></tr>
                <tr><td>Current P/E</td><td>{fmt(vp.current_pe)}×</td></tr>
                <tr><td>Historical Median P/E</td><td>{fmt(vp.historical_median_pe)}×</td></tr>
                <tr><td>Deviation</td><td>{fmtPct(vp.deviation_from_median_pct)}</td></tr>
                <tr><td>Current P/S</td><td>{fmt(vp.current_ps)}×</td></tr>
              </tbody>
            </table>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{vp.note}</p>
          </div>
        )}

        {/* Soft signals */}
        {ss && (
          <div className="card">
            <div className={styles.cardTitle}>Soft Signals</div>
            <div className={styles.signals}>
              {[
                { label: 'Insider Activity', dir: ss.insider_activity,   detail: ss.insider_detail },
                { label: 'EPS Revisions',    dir: ss.estimate_revisions, detail: ss.revision_detail },
                { label: 'Buybacks',         dir: ss.buyback_activity,   detail: ss.buyback_detail },
              ].map(({ label, dir, detail }) => (
                <div key={label} className={styles.signal}>
                  <span style={{ color: SIGNAL_COLOR[dir], fontSize: 16 }}>{SIGNAL_ARROW[dir]}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{label} <span style={{ color: SIGNAL_COLOR[dir], fontSize: 12 }}>{dir}</span></div>
                    <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{detail}</div>
                  </div>
                </div>
              ))}
              {ss.conflict_flag && (
                <div style={{ background: 'var(--yellow-dim)', borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
                  ⚠ {ss.conflict_description}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 3-Year Projection */}
        {projection && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className={styles.cardTitle}>3-Year Projection</div>
            <table>
              <thead>
                <tr><th></th><th>Base Case</th><th>Bull Case</th></tr>
              </thead>
              <tbody>
                {[
                  ['Revenue CAGR',    fmtPct(projection.base_case?.revenue_cagr),       fmtPct(projection.bull_case?.revenue_cagr)],
                  ['EPS CAGR',        fmtPct(projection.base_case?.eps_cagr),           fmtPct(projection.bull_case?.eps_cagr)],
                  ['Applied P/E',     `${fmt(projection.base_case?.applied_pe_multiple)}×`, `${fmt(projection.bull_case?.applied_pe_multiple)}×`],
                  ['Implied Price Y3',`$${fmt(projection.base_case?.implied_price_year_3)}`, `$${fmt(projection.bull_case?.implied_price_year_3)}`],
                ].map(([label, base, bull]) => (
                  <tr key={label}><td>{label}</td><td>{base}</td><td>{bull}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Rationale */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <div className={styles.cardTitle}>Rationale</div>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-dim)' }}>{justification}</p>
        </div>

        {/* Caveats */}
        <div className={styles.caveats}>
          {[caveat_quality_not_timing, caveat_projection_not_guaranteed, caveat_garbage_in_garbage_out].map((c, i) => (
            <p key={i}>{i + 1}. {c}</p>
          ))}
        </div>
      </div>
    </div>
  )
}

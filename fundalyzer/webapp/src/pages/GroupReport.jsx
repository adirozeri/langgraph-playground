import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchLatestResult } from '../api/client'
import Leaderboard from '../components/Leaderboard'
import KpiComparisonTable from '../components/KpiComparisonTable'
import CompanySummaryCard from '../components/CompanySummaryCard'
import ProgressPanel from '../components/ProgressPanel'
import styles from './GroupReport.module.css'

const TABS = ['Leaderboard', 'KPI Comparison', 'Summaries']

export default function GroupReport() {
  const { name } = useParams()
  const qc = useQueryClient()
  const [tab, setTab] = useState('Leaderboard')
  const [running, setRunning] = useState(false)

  const { data: result, isLoading, error } = useQuery({
    queryKey: ['result', name],
    queryFn: () => fetchLatestResult(name),
    retry: false,
  })

  const handleDone = () => {
    setRunning(false)
    qc.invalidateQueries({ queryKey: ['result', name] })
  }

  return (
    <div className="page">
      {running && <ProgressPanel group={name} onDone={handleDone} onClose={() => setRunning(false)} />}

      <div className="flex items-center justify-between gap-16" style={{ marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>
            <Link to="/">Dashboard</Link> / {name}
          </div>
          <h1 className="page-title" style={{ marginBottom: 0 }}>{name}</h1>
          {result && <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>Updated {result.run_date}</span>}
        </div>
        <button className="btn-primary" onClick={() => setRunning(true)} disabled={running}>
          {running ? 'Running…' : 'Run now'}
        </button>
      </div>

      {isLoading && <div className="spinner" />}

      {error && (
        <div className="empty-state">
          <h3>No results yet</h3>
          <p>Click <strong>Run now</strong> to analyze this group.</p>
        </div>
      )}

      {result && (
        <>
          <div className={styles.tabs}>
            {TABS.map(t => (
              <button key={t} className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`} onClick={() => setTab(t)}>
                {t}
              </button>
            ))}
          </div>

          <div className={styles.content}>
            {tab === 'Leaderboard' && (
              <div className="card">
                <Leaderboard ranking={result.ranking} groupName={name} clickable />
              </div>
            )}

            {tab === 'KPI Comparison' && (
              <KpiComparisonTable kpiValues={result.kpi_values} ranking={result.ranking} />
            )}

            {tab === 'Summaries' && (
              <div className={styles.summaries}>
                {result.ranking.members.map(m => (
                  <CompanySummaryCard
                    key={m.ticker}
                    rank={m.rank}
                    ticker={m.ticker}
                    decision={result.decisions[m.ticker]}
                    groupName={name}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchGroups, fetchLatestResult } from '../api/client'
import Leaderboard from '../components/Leaderboard'
import ProgressPanel from '../components/ProgressPanel'
import styles from './Dashboard.module.css'

export default function Dashboard() {
  const qc = useQueryClient()
  const { data: groups = {}, isLoading } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })
  const groupNames = Object.keys(groups)

  const [selected, setSelected]   = useState(null)
  const [running, setRunning]      = useState(null)   // group name being analyzed

  const active = selected ?? groupNames[0] ?? null

  const { data: result, isLoading: loadingResult } = useQuery({
    queryKey: ['result', active],
    queryFn: () => fetchLatestResult(active),
    enabled: !!active,
    retry: false,
  })

  const handleDone = ({ group }) => {
    setRunning(null)
    qc.invalidateQueries({ queryKey: ['result', group] })
  }

  if (isLoading) return <div className="page"><div className="spinner" /></div>

  if (groupNames.length === 0) {
    return (
      <div className="page">
        <div className="empty-state">
          <h3>No groups configured</h3>
          <p>Go to <Link to="/settings">Settings</Link> to add your first peer group.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      {running && (
        <ProgressPanel group={running} onDone={handleDone} onClose={() => setRunning(null)} />
      )}

      <div className={styles.layout}>
        {/* Sidebar */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTitle}>Groups</div>
          {groupNames.map(name => (
            <button
              key={name}
              className={`${styles.groupBtn} ${active === name ? styles.groupBtnActive : ''}`}
              onClick={() => setSelected(name)}
            >
              {name}
            </button>
          ))}
        </aside>

        {/* Main */}
        <main className={styles.main}>
          {active && (
            <>
              <div className="flex items-center justify-between gap-16" style={{ marginBottom: 16 }}>
                <div>
                  <h1 className="page-title" style={{ marginBottom: 2 }}>{active}</h1>
                  {result && (
                    <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                      Last updated: {result.run_date}
                    </span>
                  )}
                </div>
                <div className="flex gap-8">
                  {result && (
                    <Link to={`/groups/${active}`}>
                      <button className="btn-ghost">Full report →</button>
                    </Link>
                  )}
                  <button
                    className="btn-primary"
                    onClick={() => setRunning(active)}
                    disabled={!!running}
                  >
                    {running === active ? 'Running…' : 'Run now'}
                  </button>
                </div>
              </div>

              {loadingResult && <div className="spinner" />}

              {!loadingResult && !result && (
                <div className="empty-state">
                  <h3>No results yet</h3>
                  <p>Click <strong>Run now</strong> to analyze this group.</p>
                </div>
              )}

              {result && (
                <div className="card">
                  <Leaderboard ranking={result.ranking} groupName={active} clickable />
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}

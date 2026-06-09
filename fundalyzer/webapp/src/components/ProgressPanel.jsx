import { useEffect, useState } from 'react'
import { openAnalysisStream } from '../api/client'
import styles from './ProgressPanel.module.css'

const STEP_LABELS = {
  fetching_data:       'Fetching data',
  computing_kpis:      'Computing KPIs',
  building_peers:      'Building peers',
  building_dashboards: 'Assembling dashboards',
  interpreting:        'Interpreting (LLM)',
  deciding:            'Deciding',
  done:                'Done',
}

export default function ProgressPanel({ group, onDone, onClose }) {
  const [events, setEvents] = useState([])
  const [status, setStatus] = useState('connecting')   // connecting | running | done | error
  const [current, setCurrent] = useState(null)          // { ticker, step, index, total }
  const [errorMsg, setErrorMsg] = useState(null)

  useEffect(() => {
    const es = openAnalysisStream(group)
    setStatus('running')

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      setCurrent(data)
      setEvents(prev => {
        const last = prev[prev.length - 1]
        if (last?.ticker === data.ticker) {
          return [...prev.slice(0, -1), data]
        }
        return [...prev, data]
      })
    })

    es.addEventListener('done', (e) => {
      const data = JSON.parse(e.data)
      setStatus('done')
      es.close()
      onDone?.(data)
    })

    es.addEventListener('error', (e) => {
      try {
        const data = JSON.parse(e.data)
        setErrorMsg(data.message)
      } catch {
        setErrorMsg('Stream error')
      }
      setStatus('error')
      es.close()
    })

    return () => es.close()
  }, [group])

  const pct = current ? Math.round((current.index / current.total) * 100) : 0

  return (
    <div className={styles.overlay}>
      <div className={styles.panel}>
        <div className={styles.header}>
          <span>Analyzing <strong>{group}</strong></span>
          {status === 'done' || status === 'error' ? (
            <button className="btn-ghost" onClick={onClose}>Close</button>
          ) : null}
        </div>

        {status === 'running' && current && (
          <>
            <div className={styles.progressBar}>
              <div className={styles.fill} style={{ width: `${pct}%` }} />
            </div>
            <div className={styles.currentStep}>
              [{current.index}/{current.total}] {current.ticker} — {STEP_LABELS[current.step] ?? current.step}
            </div>
          </>
        )}

        {status === 'done' && (
          <p className={styles.done}>✓ Analysis complete</p>
        )}

        {status === 'error' && (
          <p className={styles.error}>✗ {errorMsg}</p>
        )}

        <ul className={styles.log}>
          {events.map((e, i) => (
            <li key={i} style={{ color: e.step === 'done' ? 'var(--green)' : 'var(--text-dim)' }}>
              {e.ticker} — {STEP_LABELS[e.step] ?? e.step}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

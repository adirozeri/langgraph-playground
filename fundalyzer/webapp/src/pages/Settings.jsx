import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSettings } from '../api/client'
import GroupManager from '../components/GroupManager'
import styles from './Settings.module.css'

export default function Settings() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })

  const [hour,   setHour]   = useState('')
  const [minute, setMinute] = useState('')
  const [years,  setYears]  = useState('')
  const [saved,  setSaved]  = useState(false)

  const save = useMutation({
    mutationFn: () => {
      const body = {}
      if (hour   !== '') body.schedule_hour   = parseInt(hour)
      if (minute !== '') body.schedule_minute = parseInt(minute)
      if (years  !== '') body.default_years   = parseInt(years)
      return patchSettings(body)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (isLoading) return <div className="page"><div className="spinner" /></div>

  return (
    <div className="page">
      <h1 className="page-title">Settings</h1>

      <div className={styles.grid}>
        {/* API Status */}
        <div className="card">
          <div className={styles.cardTitle}>API Keys</div>
          <table>
            <tbody>
              <tr>
                <td>ANTHROPIC_API_KEY</td>
                <td>
                  <span className={`badge ${settings?.anthropic_api_key === 'set' ? 'badge-invest' : 'badge-avoid'}`}>
                    {settings?.anthropic_api_key}
                  </span>
                </td>
              </tr>
              <tr>
                <td>FMP_API_KEY</td>
                <td>
                  <span className={`badge ${settings?.fmp_api_key === 'set' ? 'badge-invest' : 'badge-hold'}`}>
                    {settings?.fmp_api_key}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
            Set keys in your <code>.env</code> file and restart the server.
          </p>
        </div>

        {/* Scheduler */}
        <div className="card">
          <div className={styles.cardTitle}>Daily Scheduler</div>
          <table style={{ marginBottom: 14 }}>
            <tbody>
              <tr><td>Status</td><td><span className={`badge ${settings?.scheduler_enabled ? 'badge-invest' : 'badge-hold'}`}>{settings?.scheduler_enabled ? 'enabled' : 'disabled'}</span></td></tr>
              <tr><td>Runs at</td><td>{String(settings?.schedule_hour ?? 7).padStart(2,'0')}:{String(settings?.schedule_minute ?? 0).padStart(2,'0')} local time</td></tr>
              <tr><td>Default years</td><td>{settings?.default_years}</td></tr>
            </tbody>
          </table>
          <div className={styles.form}>
            <div className={styles.formRow}>
              <label>Run at hour (0–23)</label>
              <input type="number" min="0" max="23" placeholder={settings?.schedule_hour}
                value={hour} onChange={e => setHour(e.target.value)} style={{ width: 70 }} />
            </div>
            <div className={styles.formRow}>
              <label>Run at minute (0–59)</label>
              <input type="number" min="0" max="59" placeholder={settings?.schedule_minute}
                value={minute} onChange={e => setMinute(e.target.value)} style={{ width: 70 }} />
            </div>
            <div className={styles.formRow}>
              <label>Default years of history</label>
              <input type="number" min="1" max="20" placeholder={settings?.default_years}
                value={years} onChange={e => setYears(e.target.value)} style={{ width: 70 }} />
            </div>
            <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
              {saved ? '✓ Saved' : save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>

        {/* Group manager */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <GroupManager />
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchGroups, createGroup, deleteGroup } from '../api/client'
import styles from './GroupManager.module.css'

export default function GroupManager() {
  const qc = useQueryClient()
  const { data: groups = {}, isLoading } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })

  const [newName, setNewName]       = useState('')
  const [newTickers, setNewTickers] = useState('')
  const [error, setError]           = useState(null)

  const create = useMutation({
    mutationFn: () => {
      const tickers = newTickers.split(',').map(t => t.trim().toUpperCase()).filter(Boolean)
      if (!newName.trim()) throw new Error('Group name is required')
      if (tickers.length < 2) throw new Error('At least 2 tickers required')
      return createGroup(newName.trim().toLowerCase(), tickers)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['groups'] })
      setNewName(''); setNewTickers(''); setError(null)
    },
    onError: (e) => setError(e.message),
  })

  const remove = useMutation({
    mutationFn: deleteGroup,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }),
  })

  if (isLoading) return <div className="spinner" />

  return (
    <div className={styles.wrap}>
      <h3 className={styles.title}>Peer Groups</h3>

      {/* Existing groups */}
      <div className={styles.list}>
        {Object.entries(groups).map(([name, tickers]) => (
          <div key={name} className={styles.groupRow}>
            <div>
              <span className={styles.groupName}>{name}</span>
              <span className={styles.tickers}>{tickers.join(', ')}</span>
            </div>
            <button
              className="btn-danger"
              style={{ fontSize: 12, padding: '4px 10px' }}
              onClick={() => remove.mutate(name)}
              disabled={remove.isPending}
            >
              Remove
            </button>
          </div>
        ))}
        {Object.keys(groups).length === 0 && (
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>No groups configured.</p>
        )}
      </div>

      {/* Add group form */}
      <div className={styles.form}>
        <div className={styles.formTitle}>Add / Update Group</div>
        {error && <p className={styles.error}>{error}</p>}
        <div className={styles.fields}>
          <input
            placeholder="Group name (e.g. big_tech)"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            style={{ width: 180 }}
          />
          <input
            placeholder="Tickers, comma-separated (e.g. AAPL,MSFT,GOOGL)"
            value={newTickers}
            onChange={e => setNewTickers(e.target.value)}
            style={{ flex: 1 }}
          />
          <button
            className="btn-primary"
            onClick={() => create.mutate()}
            disabled={create.isPending}
          >
            {create.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

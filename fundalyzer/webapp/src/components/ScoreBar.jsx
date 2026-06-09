import styles from './ScoreBar.module.css'

const scoreClass = (s) => {
  const n = parseFloat(s)
  if (n >= 6) return 'score-high'
  if (n >= 4) return 'score-mid'
  return 'score-low'
}

export default function ScoreBar({ score, showBar = true }) {
  const n = parseFloat(score)
  const pct = Math.min(100, Math.max(0, (n / 10) * 100))
  const cls = scoreClass(score)
  return (
    <div className={styles.wrap}>
      <span className={cls} style={{ fontVariantNumeric: 'tabular-nums', minWidth: 36 }}>
        {isNaN(n) ? '—' : n.toFixed(2)}
      </span>
      {showBar && (
        <div className={styles.track}>
          <div className={`${styles.fill} ${styles[cls]}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

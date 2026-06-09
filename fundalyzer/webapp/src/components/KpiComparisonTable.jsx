import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts'
import styles from './KpiComparisonTable.module.css'

const KPI_ROWS = [
  { key: 'revenue_growth_yoy', label: 'Revenue Growth',   fmt: 'pct'  },
  { key: 'gross_margin',       label: 'Gross Margin',     fmt: 'pct'  },
  { key: 'operating_margin',   label: 'Operating Margin', fmt: 'pct'  },
  { key: 'net_margin',         label: 'Net Margin',       fmt: 'pct'  },
  { key: 'fcf_margin',         label: 'FCF Margin',       fmt: 'pct'  },
  { key: 'trailing_pe',        label: 'Trailing P/E',     fmt: 'mult' },
  { key: 'ev_to_ebitda',       label: 'EV/EBITDA',        fmt: 'mult' },
  { key: 'roic',               label: 'ROIC',             fmt: 'pct'  },
  { key: 'roe',                label: 'ROE',              fmt: 'pct'  },
  { key: 'fcf_yield',          label: 'FCF Yield',        fmt: 'pct'  },
  { key: 'debt_to_equity',     label: 'Debt/Equity',      fmt: 'mult' },
]

const COLORS = ['#63b3ed','#48bb78','#ecc94b','#fc8181','#b794f4','#f6ad55','#76e4f7']

function fmtVal(raw, fmt) {
  if (!raw || raw === 'UNAVAILABLE') return '—'
  const n = parseFloat(raw)
  if (isNaN(n)) return '—'
  if (fmt === 'pct')  return `${(n * 100).toFixed(1)}%`
  if (fmt === 'mult') return `${n.toFixed(1)}×`
  return n.toFixed(2)
}

function numVal(raw, fmt) {
  if (!raw || raw === 'UNAVAILABLE') return 0
  const n = parseFloat(raw)
  if (isNaN(n)) return 0
  return fmt === 'pct' ? parseFloat((n * 100).toFixed(2)) : parseFloat(n.toFixed(2))
}

const CustomTooltip = ({ active, payload, label, fmt }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: '8px 12px', borderRadius: 6 }}>
      <p style={{ color: 'var(--text-dim)', marginBottom: 4, fontSize: 12 }}>{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color, fontSize: 13 }}>
          {p.dataKey}: {fmtVal(String(p.value / (fmt === 'pct' ? 100 : 1)), fmt)}
        </p>
      ))}
    </div>
  )
}

export default function KpiComparisonTable({ kpiValues, ranking }) {
  if (!kpiValues || !ranking) return null
  const tickers = ranking.members.map(m => m.ticker)

  return (
    <div className={styles.wrap}>
      {KPI_ROWS.map(({ key, label, fmt }) => {
        const chartData = [{ name: label }]
        tickers.forEach(ticker => {
          chartData[0][ticker] = numVal(kpiValues[ticker]?.[key], fmt)
        })

        return (
          <div key={key} className={styles.metric}>
            <div className={styles.metricLabel}>{label}</div>
            <div className={styles.tableRow}>
              {tickers.map((ticker, i) => (
                <div key={ticker} className={styles.cell}>
                  <span className={styles.tickerTag} style={{ color: COLORS[i % COLORS.length] }}>{ticker}</span>
                  <span className={styles.value}>{fmtVal(kpiValues[ticker]?.[key], fmt)}</span>
                </div>
              ))}
            </div>
            <div className={styles.chart}>
              <ResponsiveContainer width="100%" height={36}>
                <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" hide />
                  {tickers.map((ticker, i) => (
                    <Bar key={ticker} dataKey={ticker} fill={COLORS[i % COLORS.length]} radius={2} barSize={10} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )
      })}
    </div>
  )
}

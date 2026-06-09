import { Link, useLocation } from 'react-router-dom'
import styles from './Navbar.module.css'

export default function Navbar() {
  const { pathname } = useLocation()
  return (
    <nav className={styles.nav}>
      <Link to="/" className={styles.brand}>📈 Fundalyzer</Link>
      <div className={styles.links}>
        <Link to="/"         className={pathname === '/'          ? styles.active : ''}>Dashboard</Link>
        <Link to="/settings" className={pathname === '/settings'  ? styles.active : ''}>Settings</Link>
      </div>
    </nav>
  )
}

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import GroupReport from './pages/GroupReport'
import CompanyDetail from './pages/CompanyDetail'
import Settings from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/"                                   element={<Dashboard />} />
        <Route path="/groups/:name"                       element={<GroupReport />} />
        <Route path="/groups/:name/company/:ticker"       element={<CompanyDetail />} />
        <Route path="/settings"                           element={<Settings />} />
        <Route path="*"                                   element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

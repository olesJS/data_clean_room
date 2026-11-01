import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth, RequireRole } from './auth/guards'
import { useAuth } from './auth/useAuth'
import { AppLayout } from './layout/AppLayout'
import { HOME_BY_ROLE } from './layout/nav'
import AccessRequestsPage from './pages/AccessRequestsPage'
import AuditPage from './pages/AuditPage'
import CatalogPage from './pages/CatalogPage'
import DatasetsPage from './pages/DatasetsPage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import ProfilePage from './pages/ProfilePage'
import RequestsPage from './pages/RequestsPage'
import UploadPage from './pages/UploadPage'

function HomeRedirect() {
  const { role } = useAuth()
  return <Navigate to={role ? HOME_BY_ROLE[role] : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<HomeRedirect />} />
          <Route element={<RequireRole allow={['DataProvider']} />}>
            <Route path="/datasets" element={<DatasetsPage />} />
            <Route path="/datasets/:id" element={<ProfilePage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/access" element={<AccessRequestsPage />} />
          </Route>
          <Route element={<RequireRole allow={['DataConsumer', 'DataSteward']} />}>
            <Route path="/catalog" element={<CatalogPage />} />
          </Route>
          <Route element={<RequireRole allow={['DataConsumer']} />}>
            <Route path="/requests" element={<RequestsPage />} />
          </Route>
          <Route element={<RequireRole allow={['DataSteward']} />}>
            <Route path="/audit" element={<AuditPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

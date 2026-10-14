import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
import { BusyProvider } from './context/BusyContext';
import { Skeleton } from './components/ui';
import { page } from './components/ViewTransitions';

// Auth is on the critical path; everything else splits per route.
import Login from './pages/Login';

const LoginPage = page(Login);

const Register = lazy(() => import('./pages/Register'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const ImportData = lazy(() => import('./pages/ImportData'));
const FeedbackList = lazy(() => import('./pages/FeedbackList'));
const InsightsDashboard = lazy(() => import('./pages/InsightsDashboard'));
const PRDWorkspace = lazy(() => import('./pages/PRDWorkspace'));
const UserStoriesWorkspace = lazy(() => import('./pages/UserStoriesWorkspace'));
const PrioritizationHub = lazy(() => import('./pages/PrioritizationHub'));
const RoadmapPlanner = lazy(() => import('./pages/RoadmapPlanner'));
const OutcomeTracker = lazy(() => import('./pages/OutcomeTracker'));
const ExecutiveReports = lazy(() => import('./pages/ExecutiveReports'));
const CopilotChat = lazy(() => import('./pages/CopilotChat'));

// One page boundary per route. They have to be distinct components: React
// reuses a boundary of the same type in the same position, so twelve routes
// sharing one wrapper would make every navigation look like an update of that
// wrapper rather than a page leaving and another arriving.
const RegisterPage = page(Register);
const DashboardPage = page(Dashboard);
const ImportPage = page(ImportData);
const FeedbackPage = page(FeedbackList);
const InsightsPage = page(InsightsDashboard);
const PrdsPage = page(PRDWorkspace);
const StoriesPage = page(UserStoriesWorkspace);
const PrioritizationPage = page(PrioritizationHub);
const RoadmapPage = page(RoadmapPlanner);
const OutcomesPage = page(OutcomeTracker);
const ReportsPage = page(ExecutiveReports);
const CopilotPage = page(CopilotChat);

const hasToken = () => Boolean(localStorage.getItem('pm_copilot_token'));

/** Sends anyone without a session back to sign-in. */
function RequireAuth({ children }) {
  if (!hasToken()) return <Navigate to="/" replace />;
  return children;
}

function AuthFallback() {
  return (
    <div className="auth-container">
      <div className="auth-card stack stack-md" role="status" aria-label="Loading">
        <Skeleton className="skeleton-title" style={{ height: 26, width: 180 }} />
        <Skeleton className="skeleton-line w-75" />
        <Skeleton className="skeleton-block" style={{ height: 40 }} />
        <Skeleton className="skeleton-block" style={{ height: 40 }} />
        <Skeleton className="skeleton-block" style={{ height: 40 }} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BusyProvider>
        <Router>
          <Routes>
            {/* Public */}
            <Route
              path="/"
              element={
                hasToken() ? (
                  <Navigate to="/dashboard" replace />
                ) : (
                  <LoginPage />
                )
              }
            />
            <Route
              path="/register"
              element={
                <Suspense fallback={<AuthFallback />}>
                  <RegisterPage />
                </Suspense>
              }
            />

            {/* Authenticated shell */}
            <Route
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              {/* One page-level transition per screen, so the whole app
                  navigates the same way. */}
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/feedback" element={<FeedbackPage />} />
              <Route path="/insights" element={<InsightsPage />} />
              <Route path="/prds" element={<PrdsPage />} />
              <Route path="/prds/:prdId" element={<PrdsPage />} />
              <Route path="/user-stories" element={<StoriesPage />} />
              <Route path="/prioritization" element={<PrioritizationPage />} />
              <Route path="/roadmap" element={<RoadmapPage />} />
              <Route path="/outcomes" element={<OutcomesPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/copilot" element={<CopilotPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Router>
      </BusyProvider>
    </ErrorBoundary>
  );
}

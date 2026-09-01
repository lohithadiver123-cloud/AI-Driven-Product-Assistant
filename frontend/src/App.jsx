import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import FeedbackTable from './components/FeedbackTable';
import UploadModal from './components/UploadModal';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import VerifyEmail from './pages/VerifyEmail';
import {
  fetchHealth,
  fetchFeedbackStats,
  fetchCategories,
  fetchFeedbackList,
  fetchSupportTicketsList,
} from './services/api';
import './App.css';

/**
 * History Guard: Keeps browser history safely inside the application
 * so clicking the browser Back button never dumps the user out to the Edge New Tab page.
 */
function HistoryGuard() {
  const location = useLocation();

  useEffect(() => {
    const currentState = window.history.state || {};
    if (!currentState.__app_guard) {
      window.history.pushState({ ...currentState, __app_guard: true }, '', window.location.href);
    }

    const onPopState = () => {
      if (location.pathname === '/dashboard' || location.pathname === '/') {
        window.history.pushState({ __app_guard: true }, '', window.location.href);
      }
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [location.pathname]);

  return null;
}

/**
 * Main Authenticated Workspace View
 */
function WorkspaceApp() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Derive active tab from current URL pathname
  const activeTab = location.pathname.startsWith('/feedback')
    ? 'feedback'
    : location.pathname.startsWith('/upload') || location.pathname.startsWith('/import')
    ? 'upload'
    : 'dashboard';

  const handleTabChange = (newTab) => {
    if (newTab === 'feedback') {
      navigate('/feedback');
    } else if (newTab === 'upload' || newTab === 'import') {
      navigate('/upload');
    } else {
      navigate('/dashboard');
    }
  };

  const [tableCurrentView, setTableCurrentView] = useState('feedback'); // 'feedback' | 'tickets'
  const [isOnline, setIsOnline] = useState(false);
  const [loading, setLoading] = useState(false);

  // Stats & Categories
  const [stats, setStats] = useState(null);
  const [categories, setCategories] = useState([]);

  // Table State
  const [items, setItems] = useState([]);
  const [totalItems, setTotalItems] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [totalPages, setTotalPages] = useState(1);
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    sentiment: '',
    priority: '',
    status: '',
    source: '',
  });

  // Check Health
  const checkStatus = useCallback(async () => {
    try {
      await fetchHealth();
      setIsOnline(true);
    } catch {
      setIsOnline(false);
    }
  }, []);

  // Load Dashboard Stats & Categories for active workspace
  const loadStatsAndCategories = useCallback(async () => {
    try {
      const [statsData, catData] = await Promise.all([
        fetchFeedbackStats(),
        fetchCategories(),
      ]);
      setStats(statsData);
      setCategories(catData);
    } catch (err) {
      console.error('Error loading stats/categories:', err);
    }
  }, []);

  // Load Records (Feedback or Support Tickets)
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      if (tableCurrentView === 'feedback') {
        const data = await fetchFeedbackList({
          page,
          pageSize,
          search: filters.search,
          category: filters.category,
          sentiment: filters.sentiment,
          priority: filters.priority,
          source: filters.source,
        });
        setItems(data.items || []);
        setTotalItems(data.total || 0);
        setTotalPages(data.total_pages || 1);
      } else {
        const data = await fetchSupportTicketsList({
          page,
          pageSize,
          search: filters.search,
          category: filters.category,
          priority: filters.priority,
          status: filters.status,
          source: filters.source,
        });
        setItems(data.items || []);
        setTotalItems(data.total || 0);
        setTotalPages(data.total_pages || 1);
      }
    } catch (err) {
      console.error('Error loading table data:', err);
    } finally {
      setLoading(false);
    }
  }, [tableCurrentView, page, pageSize, filters]);

  // Initial Load and periodic health heartbeat (re-runs when user switches active workspace)
  useEffect(() => {
    checkStatus();
    loadStatsAndCategories();

    const interval = setInterval(() => {
      checkStatus();
    }, 10000);

    return () => clearInterval(interval);
  }, [checkStatus, loadStatsAndCategories, user?.current_workspace_id]);

  useEffect(() => {
    loadData();
  }, [loadData, user?.current_workspace_id]);

  // Filter Change Handler
  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  // View switch handler (feedback vs tickets)
  const handleViewChange = (view) => {
    setTableCurrentView(view);
    setFilters({
      search: '',
      category: '',
      sentiment: '',
      priority: '',
      status: '',
      source: '',
    });
    setPage(1);
  };

  // Navigate from Dashboard category bar to filtered Feedback table
  const handleCategoryClick = (categoryName) => {
    setTableCurrentView('feedback');
    setFilters((prev) => ({ ...prev, category: categoryName }));
    setPage(1);
    navigate('/feedback');
  };

  // Refresh All Data
  const handleRefresh = async () => {
    setLoading(true);
    await Promise.all([checkStatus(), loadStatsAndCategories(), loadData()]);
    setLoading(false);
  };

  return (
    <div className="app-layout">
      {/* Top Navigation with Auth & Workspace Profile */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        isOnline={isOnline}
        onRefresh={handleRefresh}
        loading={loading}
      />

      {/* Main Content Area */}
      <main className="main-content-container">
        {activeTab === 'dashboard' && (
          <Dashboard
            stats={stats}
            categories={categories}
            onCategoryClick={handleCategoryClick}
            onNavigateToUpload={() => handleTabChange('upload')}
          />
        )}

        {activeTab === 'feedback' && (
          <FeedbackTable
            currentView={tableCurrentView}
            onViewChange={handleViewChange}
            items={items}
            total={totalItems}
            page={page}
            pageSize={pageSize}
            totalPages={totalPages}
            onPageChange={setPage}
            filters={filters}
            onFilterChange={handleFilterChange}
            categories={categories}
            loading={loading}
          />
        )}

        {activeTab === 'upload' && (
          <UploadModal
            onUploadSuccess={() => {
              loadStatsAndCategories();
              loadData();
            }}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <p>
          AI-Driven Product Assistant & Requirements Workspace &bull; Secure Multi-Tenant Edition
        </p>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <HistoryGuard />
      <AuthProvider>
        <Routes>
          {/* Public Auth Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />

          {/* Protected Workspace Routes */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <WorkspaceApp />
              </ProtectedRoute>
            }
          />
          <Route
            path="/feedback"
            element={
              <ProtectedRoute>
                <WorkspaceApp />
              </ProtectedRoute>
            }
          />
          <Route
            path="/upload"
            element={
              <ProtectedRoute>
                <WorkspaceApp />
              </ProtectedRoute>
            }
          />
          <Route
            path="/import"
            element={
              <ProtectedRoute>
                <WorkspaceApp />
              </ProtectedRoute>
            }
          />

          {/* Root and Fallback: Redirect to /dashboard */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Navigate to="/dashboard" replace />
              </ProtectedRoute>
            }
          />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Navigate to="/dashboard" replace />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

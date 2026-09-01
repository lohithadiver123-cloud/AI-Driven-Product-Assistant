import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const CATEGORY_COLORS = {
  Authentication: '#6366f1',
  Performance: '#eab308',
  Payment: '#10b981',
  Bug: '#ef4444',
  'UI/UX': '#8b5cf6',
  'Feature Request': '#06b6d4',
  Notifications: '#f97316',
  'Account Management': '#3b82f6',
  Integration: '#ec4899',
  Other: '#6b7280',
};

export default function FeedbackTable({
  currentView,
  onViewChange,
  items,
  total,
  page,
  pageSize,
  totalPages,
  onPageChange,
  filters,
  onFilterChange,
  categories,
  loading,
}) {
  const navigate = useNavigate();
  const [selectedItem, setSelectedItem] = useState(null);
  const [showCleanedMap, setShowCleanedMap] = useState({});

  const toggleCleaned = (id) => {
    setShowCleanedMap((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const formatDate = (isoString) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  const isTicketView = currentView === 'tickets';

  return (
    <div className="feedback-view-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
        <button className="back-nav-btn" onClick={() => navigate('/dashboard')}>
          ← Back to Dashboard
        </button>
      </div>

      {/* Top View Toggle */}
      <div className="view-switch-header">
        <div className="view-toggle-group">
          <button
            className={`view-toggle-btn ${!isTicketView ? 'active' : ''}`}
            onClick={() => onViewChange('feedback')}
          >
            💬 Customer Feedback Repository
          </button>
          <button
            className={`view-toggle-btn ${isTicketView ? 'active' : ''}`}
            onClick={() => onViewChange('tickets')}
          >
            🎫 Customer Support Tickets
          </button>
        </div>
      </div>

      {/* Search & Filter Header Bar */}
      <div className="filter-card">
        <div className="filter-row">
          <div className="search-box">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              placeholder={
                isTicketView
                  ? 'Search ticket ID, customer, issue keywords...'
                  : 'Search feedback text, customer ID, keywords...'
              }
              value={filters.search}
              onChange={(e) => onFilterChange('search', e.target.value)}
              className="search-input"
            />
            {filters.search && (
              <button
                className="clear-search-btn"
                onClick={() => onFilterChange('search', '')}
              >
                ✕
              </button>
            )}
          </div>

          <div className="filter-selects-group">
            {/* Category Filter */}
            <select
              value={filters.category}
              onChange={(e) => onFilterChange('category', e.target.value)}
              className="filter-select"
            >
              <option value="">All Categories ({categories.length})</option>
              {categories.map((cat) => (
                <option key={cat.name} value={cat.name}>
                  {cat.name}
                </option>
              ))}
            </select>

            {/* Priority Filter */}
            <select
              value={filters.priority}
              onChange={(e) => onFilterChange('priority', e.target.value)}
              className="filter-select"
            >
              <option value="">All Priorities</option>
              <option value="Urgent">Urgent</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>

            {/* Sentiment Filter (For feedback) */}
            {!isTicketView && (
              <select
                value={filters.sentiment}
                onChange={(e) => onFilterChange('sentiment', e.target.value)}
                className="filter-select"
              >
                <option value="">All Sentiments</option>
                <option value="Positive">Positive</option>
                <option value="Neutral">Neutral</option>
                <option value="Negative">Negative</option>
              </select>
            )}

            {/* Status Filter (For support tickets) */}
            {isTicketView && (
              <select
                value={filters.status || ''}
                onChange={(e) => onFilterChange('status', e.target.value)}
                className="filter-select"
              >
                <option value="">All Statuses</option>
                <option value="Open">Open</option>
                <option value="In-Progress">In-Progress</option>
                <option value="Resolved">Resolved</option>
                <option value="Closed">Closed</option>
              </select>
            )}

            {/* Reset Filters */}
            {(filters.search || filters.category || filters.sentiment || filters.priority || filters.status) && (
              <button
                className="reset-filters-btn"
                onClick={() => {
                  onFilterChange('search', '');
                  onFilterChange('category', '');
                  onFilterChange('sentiment', '');
                  onFilterChange('priority', '');
                  onFilterChange('status', '');
                }}
              >
                Reset
              </button>
            )}
          </div>
        </div>

        <div className="results-count-bar">
          <span>
            Showing <strong>{items.length}</strong> of <strong>{total}</strong>{' '}
            {isTicketView ? 'support tickets' : 'feedback records'}
          </span>
          {filters.category && (
            <span className="active-filter-tag">
              Category: {filters.category}
              <button onClick={() => onFilterChange('category', '')}>✕</button>
            </span>
          )}
          {filters.priority && (
            <span className="active-filter-tag">
              Priority: {filters.priority}
              <button onClick={() => onFilterChange('priority', '')}>✕</button>
            </span>
          )}
        </div>
      </div>

      {/* Main Table */}
      <div className="table-responsive-wrapper">
        <table className="feedback-table">
          <thead>
            <tr>
              {isTicketView && <th>Ticket ID</th>}
              <th>Customer</th>
              <th>Source</th>
              <th>{isTicketView ? 'Issue Description' : 'Feedback (Verbatim vs Cleaned)'}</th>
              <th>Category</th>
              <th>Confidence</th>
              <th>Sentiment</th>
              <th>Priority</th>
              {isTicketView && <th>Status</th>}
              <th>Date</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={isTicketView ? 11 : 9} className="table-empty-cell">
                  <div className="loading-spinner-row">
                    <span className="spinner-icon">↻</span> Loading {isTicketView ? 'tickets' : 'feedback'}...
                  </div>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={isTicketView ? 11 : 9} className="table-empty-cell">
                  <div className="empty-state-message">
                    <span>📭 No records match your criteria.</span>
                  </div>
                </td>
              </tr>
            ) : (
              items.map((item) => {
                const isCleaned = showCleanedMap[item.id];
                const displayedText = isCleaned && item.cleaned_text ? item.cleaned_text : item.text;
                const catColor = CATEGORY_COLORS[item.category] || '#6b7280';
                const confidencePct = item.category_confidence
                  ? Math.round(item.category_confidence * 100)
                  : 85;

                return (
                  <tr key={item.id} className="feedback-table-row">
                    {isTicketView && (
                      <td className="ticket-id-cell">
                        <span className="ticket-id-badge">{item.ticket_id || '—'}</span>
                      </td>
                    )}
                    <td className="customer-cell">
                      <span className="customer-badge">{item.customer_id || 'Anonymous'}</span>
                    </td>
                    <td className="source-cell">
                      <span className="source-pill">{item.source || 'Direct'}</span>
                    </td>
                    <td className="feedback-text-cell">
                      <div className="text-content-wrapper">
                        <p className="feedback-text-snippet">{displayedText}</p>
                        {item.cleaned_text && (
                          <button
                            className="toggle-cleaned-btn"
                            onClick={() => toggleCleaned(item.id)}
                            title="Toggle between verbatim raw text and preprocessed text"
                          >
                            {isCleaned ? 'Show Raw' : 'Show Cleaned'}
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="category-cell">
                      <span
                        className="category-pill"
                        style={{ borderColor: catColor, color: catColor }}
                      >
                        {item.category || 'Other'}
                      </span>
                    </td>
                    <td className="confidence-cell">
                      <span className="confidence-pill" title={`Confidence: ${confidencePct}%`}>
                        {confidencePct}%
                      </span>
                    </td>
                    <td className="sentiment-cell">
                      <span className={`sentiment-pill ${(item.sentiment || 'neutral').toLowerCase()}`}>
                        {item.sentiment || 'Neutral'}
                      </span>
                    </td>
                    <td className="priority-cell">
                      <span className={`priority-pill ${(item.priority || 'medium').toLowerCase()}`}>
                        {item.priority || 'Medium'}
                      </span>
                    </td>
                    {isTicketView && (
                      <td className="status-cell">
                        <span className={`status-tag ${(item.status || 'open').toLowerCase()}`}>
                          {item.status || 'Open'}
                        </span>
                      </td>
                    )}
                    <td className="date-cell">{formatDate(item.created_at)}</td>
                    <td className="action-cell">
                      <button
                        className="inspect-btn"
                        onClick={() => setSelectedItem(item)}
                        title="View Full Details"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="pagination-bar">
          <button
            className="page-nav-btn"
            disabled={page <= 1 || loading}
            onClick={() => onPageChange(page - 1)}
          >
            ← Previous
          </button>
          <span className="page-indicator">
            Page <strong>{page}</strong> of <strong>{totalPages}</strong>
          </span>
          <button
            className="page-nav-btn"
            disabled={page >= totalPages || loading}
            onClick={() => onPageChange(page + 1)}
          >
            Next →
          </button>
        </div>
      )}

      {/* Detail Inspection Modal */}
      {selectedItem && (
        <div className="modal-overlay" onClick={() => setSelectedItem(null)}>
          <div className="modal-card detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-group">
                <h3>
                  {isTicketView ? 'Customer Support Ticket Details' : 'Customer Feedback Signal Details'}
                </h3>
                <span className="modal-id-tag">ID: {selectedItem.id}</span>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedItem(null)}>
                ✕
              </button>
            </div>

            <div className="modal-body">
              {/* Badges Grid */}
              <div className="modal-badges-grid">
                {selectedItem.ticket_id && (
                  <div className="modal-badge-item">
                    <span className="badge-item-label">Ticket ID</span>
                    <span className="ticket-id-badge">{selectedItem.ticket_id}</span>
                  </div>
                )}

                <div className="modal-badge-item">
                  <span className="badge-item-label">Category</span>
                  <span
                    className="category-pill"
                    style={{
                      borderColor: CATEGORY_COLORS[selectedItem.category] || '#6366f1',
                      color: CATEGORY_COLORS[selectedItem.category] || '#6366f1',
                    }}
                  >
                    {selectedItem.category}
                  </span>
                </div>

                <div className="modal-badge-item">
                  <span className="badge-item-label">Confidence</span>
                  <span className="confidence-pill">
                    {selectedItem.category_confidence
                      ? `${Math.round(selectedItem.category_confidence * 100)}%`
                      : '85%'}
                  </span>
                </div>

                <div className="modal-badge-item">
                  <span className="badge-item-label">Sentiment</span>
                  <span className={`sentiment-pill ${(selectedItem.sentiment || 'neutral').toLowerCase()}`}>
                    {selectedItem.sentiment || 'Neutral'}
                  </span>
                </div>

                <div className="modal-badge-item">
                  <span className="badge-item-label">Priority</span>
                  <span className={`priority-pill ${(selectedItem.priority || 'medium').toLowerCase()}`}>
                    {selectedItem.priority || 'Medium'}
                  </span>
                </div>

                {selectedItem.status && (
                  <div className="modal-badge-item">
                    <span className="badge-item-label">Status</span>
                    <span className={`status-tag ${(selectedItem.status || 'open').toLowerCase()}`}>
                      {selectedItem.status}
                    </span>
                  </div>
                )}

                <div className="modal-badge-item">
                  <span className="badge-item-label">Source</span>
                  <span className="source-pill">{selectedItem.source || 'Direct'}</span>
                </div>

                <div className="modal-badge-item">
                  <span className="badge-item-label">Customer</span>
                  <span className="customer-badge">{selectedItem.customer_id || 'Anonymous'}</span>
                </div>
              </div>

              {/* Text Comparison Box */}
              <div className="text-comparison-section">
                <div className="text-box">
                  <h4>Original Verbatim Issue / Feedback</h4>
                  <div className="text-box-content verbatim">{selectedItem.text}</div>
                </div>

                <div className="text-box">
                  <h4>Preprocessed & Cleaned Text</h4>
                  <div className="text-box-content cleaned">
                    {selectedItem.cleaned_text || selectedItem.text}
                  </div>
                </div>
              </div>

              {/* Metadata JSON */}
              {selectedItem.metadata && Object.keys(selectedItem.metadata).length > 0 && (
                <div className="metadata-section">
                  <h4>Attached Metadata</h4>
                  <pre className="metadata-pre">
                    {JSON.stringify(selectedItem.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="banner-action-btn" onClick={() => setSelectedItem(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

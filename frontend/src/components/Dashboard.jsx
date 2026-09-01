import React from 'react';

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

const CATEGORY_ICONS = {
  Authentication: '🔐',
  Performance: '⚡',
  Payment: '💳',
  Bug: '🐞',
  'UI/UX': '🎨',
  'Feature Request': '✨',
  Notifications: '🔔',
  'Account Management': '👥',
  Integration: '🔌',
  Other: '📁',
};

export default function Dashboard({ stats, categories, onCategoryClick, onNavigateToUpload }) {
  const total = stats?.total || 0;
  const categoriesMap = stats?.categories || {};
  const sentimentMap = stats?.sentiment || { Positive: 0, Neutral: 0, Negative: 0 };
  const priorityMap = stats?.priority || { Urgent: 0, High: 0, Medium: 0, Low: 0 };

  const featureRequestsCount = categoriesMap['Feature Request'] || 0;
  const negativePct = stats?.negative_percentage || 0;
  const highPriorityPct = stats?.high_priority_percentage || 0;
  const avgConfidence = stats?.average_confidence || 0.85;

  return (
    <div className="dashboard-container">
      {/* Top Welcome Banner */}
      <div className="welcome-banner">
        <div>
          <h2>Product Feedback Intelligence Overview</h2>
          <p>
            Real-time automated categorization, sentiment analysis, and priority heuristics from{' '}
            <strong>{total} customer signals</strong>.
          </p>
        </div>
        <button className="banner-action-btn" onClick={onNavigateToUpload}>
          + Ingest New Dataset
        </button>
      </div>

      {total === 0 && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15))',
          border: '1px solid rgba(99, 102, 241, 0.4)',
          borderRadius: '12px',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem'
        }}>
          <div>
            <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '1rem', marginBottom: '0.25rem' }}>
              🚀 Workspace Ready: Import your first dataset
            </div>
            <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
              Your workspace is clean. Import <code>sample_feedback.csv</code> or <code>sample_support_tickets.csv</code> from <code>data/raw/</code> to view AI analytics.
            </div>
          </div>
          <button
            onClick={onNavigateToUpload}
            style={{
              padding: '0.6rem 1.2rem',
              background: '#6366f1',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Go to Import Page →
          </button>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="kpi-grid">
        <div className="kpi-card total-card">
          <div className="kpi-icon">📊</div>
          <div className="kpi-content">
            <span className="kpi-label">Total Ingested Feedback</span>
            <span className="kpi-value">{total}</span>
            <span className="kpi-subtext">Across {Object.keys(stats?.sources || {}).length || 4} channels</span>
          </div>
        </div>

        <div className="kpi-card negative-card">
          <div className="kpi-icon">⚠️</div>
          <div className="kpi-content">
            <span className="kpi-label">Negative Feedback</span>
            <span className="kpi-value">{negativePct}%</span>
            <span className="kpi-subtext">{sentimentMap.Negative || 0} user pain points</span>
          </div>
        </div>

        <div className="kpi-card priority-card">
          <div className="kpi-icon">🚨</div>
          <div className="kpi-content">
            <span className="kpi-label">High / Urgent Priority</span>
            <span className="kpi-value">{highPriorityPct}%</span>
            <span className="kpi-subtext">{(priorityMap.High || 0) + (priorityMap.Urgent || 0)} critical blockers</span>
          </div>
        </div>

        <div className="kpi-card feature-card">
          <div className="kpi-icon">💡</div>
          <div className="kpi-content">
            <span className="kpi-label">Feature Requests</span>
            <span className="kpi-value">{featureRequestsCount}</span>
            <span className="kpi-subtext">Avg. Confidence: {(avgConfidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      </div>

      {/* Visual Distributions Layout */}
      <div className="distributions-layout">
        {/* Category Distribution Breakdown */}
        <div className="chart-panel category-panel">
          <div className="panel-header">
            <h3>Category Distribution</h3>
            <span className="panel-badge">10 Controlled Domains</span>
          </div>

          <div className="category-bars-list">
            {categories.map((cat) => {
              const count = categoriesMap[cat.name] || 0;
              const pct = total > 0 ? Math.round((count / total) * 100) : 0;
              const color = CATEGORY_COLORS[cat.name] || '#6366f1';
              const icon = CATEGORY_ICONS[cat.name] || '📁';

              return (
                <div
                  key={cat.name}
                  className="category-bar-row"
                  onClick={() => onCategoryClick(cat.name)}
                  title={`View all ${cat.name} feedback`}
                >
                  <div className="category-row-label">
                    <span className="cat-icon">{icon}</span>
                    <span className="cat-name">{cat.name}</span>
                  </div>

                  <div className="progress-bar-track">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: color }}
                    ></div>
                  </div>

                  <div className="category-row-stats">
                    <span className="cat-count">{count}</span>
                    <span className="cat-pct">({pct}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Sentiment & Priority Visualizers */}
        <div className="side-panels-column">
          {/* Sentiment Breakdown */}
          <div className="chart-panel">
            <div className="panel-header">
              <h3>Sentiment Polarity</h3>
            </div>

            <div className="sentiment-breakdown-bar">
              {total > 0 && (
                <>
                  <div
                    className="sentiment-segment positive"
                    style={{ width: `${((sentimentMap.Positive || 0) / total) * 100}%` }}
                    title={`Positive: ${sentimentMap.Positive || 0}`}
                  ></div>
                  <div
                    className="sentiment-segment neutral"
                    style={{ width: `${((sentimentMap.Neutral || 0) / total) * 100}%` }}
                    title={`Neutral: ${sentimentMap.Neutral || 0}`}
                  ></div>
                  <div
                    className="sentiment-segment negative"
                    style={{ width: `${((sentimentMap.Negative || 0) / total) * 100}%` }}
                    title={`Negative: ${sentimentMap.Negative || 0}`}
                  ></div>
                </>
              )}
            </div>

            <div className="sentiment-legend">
              <div className="legend-item">
                <span className="legend-dot positive"></span>
                <span>Positive: <strong>{sentimentMap.Positive || 0}</strong></span>
              </div>
              <div className="legend-item">
                <span className="legend-dot neutral"></span>
                <span>Neutral: <strong>{sentimentMap.Neutral || 0}</strong></span>
              </div>
              <div className="legend-item">
                <span className="legend-dot negative"></span>
                <span>Negative: <strong>{sentimentMap.Negative || 0}</strong></span>
              </div>
            </div>
          </div>

          {/* Priority Levels */}
          <div className="chart-panel">
            <div className="panel-header">
              <h3>Priority Severity</h3>
            </div>

            <div className="priority-grid">
              <div className="priority-badge-box urgent">
                <span className="prio-title">Urgent</span>
                <span className="prio-number">{priorityMap.Urgent || 0}</span>
              </div>
              <div className="priority-badge-box high">
                <span className="prio-title">High</span>
                <span className="prio-number">{priorityMap.High || 0}</span>
              </div>
              <div className="priority-badge-box medium">
                <span className="prio-title">Medium</span>
                <span className="prio-number">{priorityMap.Medium || 0}</span>
              </div>
              <div className="priority-badge-box low">
                <span className="prio-title">Low</span>
                <span className="prio-number">{priorityMap.Low || 0}</span>
              </div>
            </div>
          </div>

          {/* Source Channels */}
          <div className="chart-panel">
            <div className="panel-header">
              <h3>Ingestion Channels</h3>
            </div>
            <div className="source-tags-cloud">
              {Object.entries(stats?.sources || {}).map(([src, cnt]) => (
                <div key={src} className="source-tag">
                  <span className="source-name">{src}</span>
                  <span className="source-count">{cnt}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

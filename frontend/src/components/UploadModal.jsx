import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadFeedbackCSV, uploadSupportTicketsCSV } from '../services/api';

const SAMPLE_FEEDBACK_CSV = `customer_id,source,type,text,created_at
CUST-1001,AppStore,review,"The new login flow with Google SSO is completely broken on iOS 17. Keeps throwing 401 error. Please fix ASAP! https://app.example.com/login",2026-08-01T10:15:00Z
CUST-1002,Zendesk,support_ticket,"I was charged twice for the annual Pro subscription ($199 x 2). Need an immediate refund for the duplicate transaction.",2026-08-02T11:20:00Z
CUST-1003,InApp,survey,"The dashboard takes over 8 seconds to load our company analytics table. Extremely slow compared to the previous version.",2026-08-03T14:30:00Z
CUST-1004,Trustpilot,review,"Fantastic platform! The automated sprint reporting and Jira export saved our product team hours this week.",2026-08-04T09:00:00Z
CUST-1005,FeedbackWidget,review,"<div>Would love to see <b>Dark Mode</b> support for the requirements document editor. The bright white screen is straining at night.</div>",2026-08-05T16:45:00Z
CUST-1006,Email,support_ticket,"Notification emails are not being delivered when teammates mention me in user stories. Checked spam folder as well.",2026-08-06T08:10:00Z
CUST-1007,Zendesk,support_ticket,"Cannot reset my account password. The password reset link sent to my email expires in 10 seconds or says invalid token.",2026-08-07T12:05:00Z
CUST-1008,AppStore,review,"The mobile app crashes every single time I attempt to upload a PNG screenshot to a bug report ticket.",2026-08-08T15:20:00Z
CUST-1009,InApp,feedback,"Can you please add export to Figma or Notion? We currently copy-paste user stories manually.",2026-08-09T17:00:00Z
CUST-1010,Trustpilot,review,"Credit card checkout failed with error code ERR_STRIPE_502. Lost our team discount because of this.",2026-08-10T13:40:00Z
CUST-1011,FeedbackWidget,review,"The UI redesign for the roadmap view is confusing. Hard to drag and drop milestones across quarters.",2026-08-11T18:15:00Z
CUST-1012,Intercom,support_ticket,"Need to delete our workspace account and purge all stored customer data in compliance with GDPR. Where is the delete button?",2026-08-12T10:50:00Z
CUST-1013,Email,feedback,"Push notifications on Android arrive 30 minutes delayed. Critical alerts are missing their time windows.",2026-08-13T07:30:00Z
CUST-1014,AppStore,review,"Super intuitive AI assistant. Generating acceptance criteria from customer interviews is a game changer!",2026-08-14T20:10:00Z
CUST-1015,Zendesk,support_ticket,"Two-factor authentication (2FA) SMS codes are never received on T-Mobile numbers in US.",2026-08-15T11:15:00Z
CUST-1016,InApp,review,"Searching through 500+ backlog items hangs the browser tab completely. Search needs indexing or pagination.",2026-08-16T14:00:00Z
CUST-1017,FeedbackWidget,feedback,"Please allow custom user roles (e.g. Viewer, Editor, Product Owner) rather than just Admin and Member.",2026-08-17T16:20:00Z
CUST-1018,Trustpilot,review,"Invoicing system is missing tax ID / VAT number field required for our EU accounting department.",2026-08-18T09:45:00Z
CUST-1019,Intercom,support_ticket,"The bulk CSV import button disappeared after yesterday's frontend deployment! Urgent!",2026-08-19T13:10:00Z
CUST-1020,Email,feedback,"Love the clean minimal design! Keep up the great work on this product manager tool.",2026-08-20T19:00:00Z
CUST-1021,InApp,survey,"The contrast ratio between light gray text and the white background makes it unreadable in daylight.",2026-08-21T10:30:00Z
CUST-1022,Zendesk,support_ticket,"Audit log exports timeout with 504 Gateway Time-out whenever we query more than 30 days of activity.",2026-08-22T15:40:00Z
CUST-1023,FeedbackWidget,review,"Is there any plan to support GitLab integration alongside the existing GitHub pull request tracker?",2026-08-23T11:00:00Z
CUST-1024,AppStore,review,"App battery consumption is huge when background sync is active. 30% battery drain in 1 hour.",2026-08-24T14:15:00Z
CUST-1025,Intercom,support_ticket,"Want to transfer workspace ownership to another product lead before I leave the company.",2026-08-25T16:50:00Z`;

const SAMPLE_TICKETS_CSV = `ticket_id,customer_id,source,text,priority,status,created_at
TIK-101,CUST-901,Zendesk,"Unable to log in via Okta SAML SSO. Page returns 403 forbidden.",Urgent,Open,2026-08-01T08:00:00Z
TIK-102,CUST-902,Intercom,"Charged twice on monthly billing statement.",High,In-Progress,2026-08-02T09:15:00Z
TIK-103,CUST-903,Email,"Sprint roadmap view is extremely sluggish when loading 200+ tasks.",Medium,Open,2026-08-03T11:30:00Z
TIK-104,CUST-904,Zendesk,"Password reset link sent to Outlook email is invalid upon click.",High,Resolved,2026-08-04T13:45:00Z
TIK-105,CUST-905,Intercom,"Feature request: need integration with Jira Cloud webhooks.",Low,Open,2026-08-05T15:00:00Z
TIK-106,CUST-906,Email,"Dark mode contrast is too low in settings modal.",Low,Closed,2026-08-06T16:20:00Z
TIK-107,CUST-907,Zendesk,"2FA SMS code not received on international UK numbers.",Urgent,In-Progress,2026-08-07T17:10:00Z
TIK-108,CUST-908,Intercom,"Export to CSV crashes the browser when file contains UTF-8 characters.",High,Open,2026-08-08T18:00:00Z`;

export default function UploadModal({ onUploadSuccess }) {
  const navigate = useNavigate();
  const [datasetType, setDatasetType] = useState('feedback'); // 'feedback' | 'tickets'
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [report, setReport] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  const handleLoadSample = (type = 'feedback') => {
    const csvContent = type === 'feedback' ? SAMPLE_FEEDBACK_CSV : SAMPLE_TICKETS_CSV;
    const filename = type === 'feedback' ? 'sample_feedback.csv' : 'sample_support_tickets.csv';
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const sampleFile = new File([blob], filename, { type: 'text/csv' });
    setDatasetType(type);
    setFile(sampleFile);
    setErrorMsg(null);
    setReport(null);
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setErrorMsg(null);
      setReport(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setErrorMsg(null);
      setReport(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setErrorMsg('Please select a .csv file to upload.');
      return;
    }

    setUploading(true);
    setErrorMsg(null);
    try {
      const data =
        datasetType === 'feedback'
          ? await uploadFeedbackCSV(file)
          : await uploadSupportTicketsCSV(file);
      setReport(data);
      if (onUploadSuccess) onUploadSuccess();
    } catch (err) {
      setErrorMsg(err.message || 'CSV Ingestion failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="upload-view-container">
      <button className="back-nav-btn" onClick={() => navigate('/dashboard')}>
        ← Back to Dashboard
      </button>
      <div className="upload-card">
        <div className="upload-header">
          <h2>Import Customer Signals & Support Datasets</h2>
          <p>
            Upload a CSV export (from Zendesk, App Store, Trustpilot, Jira Service Desk, Intercom, or custom CSVs).
            The Python ingestion engine will automatically validate, clean, deduplicate, and classify
            records into controlled categories.
          </p>

          {/* Dataset Type Selector */}
          <div className="dataset-type-selector">
            <button
              className={`type-btn ${datasetType === 'feedback' ? 'active' : ''}`}
              onClick={() => {
                setDatasetType('feedback');
                setFile(null);
                setReport(null);
                setErrorMsg(null);
              }}
            >
              💬 Customer Feedback Dataset
            </button>
            <button
              className={`type-btn ${datasetType === 'tickets' ? 'active' : ''}`}
              onClick={() => {
                setDatasetType('tickets');
                setFile(null);
                setReport(null);
                setErrorMsg(null);
              }}
            >
              🎫 Support Tickets Dataset
            </button>
          </div>
        </div>

        {/* Drag and drop box */}
        <div
          className={`dropzone-box ${file ? 'has-file' : ''}`}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
        >
          <div className="dropzone-inner">
            <span className="dropzone-icon">{file ? '📄' : '📁'}</span>
            {file ? (
              <div className="file-info-selected">
                <span className="selected-filename">{file.name}</span>
                <span className="selected-filesize">
                  ({(file.size / 1024).toFixed(1)} KB) &bull; Target: {datasetType === 'feedback' ? 'Feedback' : 'Support Tickets'}
                </span>
              </div>
            ) : (
              <div>
                <p className="dropzone-primary-text">
                  Drag and drop your <strong>.csv</strong> file here, or{' '}
                  <label className="file-browse-link">
                    browse
                    <input
                      type="file"
                      accept=".csv,.txt"
                      onChange={handleFileChange}
                      style={{ display: 'none' }}
                    />
                  </label>
                </p>
                <p className="dropzone-hint-text">
                  {datasetType === 'feedback'
                    ? 'Expected columns: customer_id, source, text, created_at'
                    : 'Expected columns: ticket_id, customer_id, source, text/issue, priority, status'}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Quick Demo Data Buttons */}
        <div className="quick-demo-row" style={{ margin: '1rem 0', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', justifyContent: 'center', alignItems: 'center' }}>
          <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Or load pre-packaged sample dataset:</span>
          <button
            type="button"
            style={{ padding: '0.45rem 0.9rem', fontSize: '0.82rem', background: '#1e293b', color: '#38bdf8', border: '1px solid #38bdf8', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}
            onClick={() => handleLoadSample('feedback')}
          >
            ✨ Load Demo Feedback (25 items)
          </button>
          <button
            type="button"
            style={{ padding: '0.45rem 0.9rem', fontSize: '0.82rem', background: '#1e293b', color: '#a855f7', border: '1px solid #a855f7', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}
            onClick={() => handleLoadSample('tickets')}
          >
            🎫 Load Demo Tickets (8 items)
          </button>
        </div>

        {/* Error message */}
        {errorMsg && <div className="upload-error-banner">⚠️ {errorMsg}</div>}

        {/* Action button */}
        <div className="upload-actions-bar">
          <button
            className="start-upload-btn"
            disabled={!file || uploading}
            onClick={handleUpload}
          >
            {uploading
              ? 'Processing & Classifying Dataset...'
              : `Ingest ${datasetType === 'feedback' ? 'Feedback' : 'Support Tickets'}`}
          </button>
        </div>

        {/* Ingestion Quality Report */}
        {report && (
          <div className="ingestion-report-card">
            <div className="report-header">
              <span className="report-status-badge success">Ingestion Completed</span>
              <h3>{report.message}</h3>
            </div>

            <div className="report-metrics-grid">
              <div className="report-metric">
                <span className="metric-label">Total Rows</span>
                <span className="metric-val">{report.total_records}</span>
              </div>
              <div className="report-metric highlight">
                <span className="metric-label">Processed & Stored</span>
                <span className="metric-val">{report.processed_records}</span>
              </div>
              <div className="report-metric">
                <span className="metric-label">Duplicates Skipped</span>
                <span className="metric-val">{report.duplicate_records}</span>
              </div>
              <div className="report-metric">
                <span className="metric-label">Empty Rows Skipped</span>
                <span className="metric-val">{report.empty_text_records}</span>
              </div>
            </div>

            {/* Category breakdown in report */}
            {report.categories_summary && Object.keys(report.categories_summary).length > 0 && (
              <div className="report-categories-section">
                <h4>Detected Category Breakdown</h4>
                <div className="category-pills-row">
                  {Object.entries(report.categories_summary).map(([cat, count]) => (
                    <span key={cat} className="report-cat-tag">
                      {cat}: <strong>{count}</strong>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Error issues list */}
            {report.errors && report.errors.length > 0 && (
              <div className="report-errors-section">
                <h4>Row Validation Notices ({report.errors.length})</h4>
                <ul className="report-errors-list">
                  {report.errors.slice(0, 5).map((err, idx) => (
                    <li key={idx}>
                      Row {err.row_index}: {err.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

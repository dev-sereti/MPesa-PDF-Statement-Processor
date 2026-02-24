// frontend/src/components/ResultDownload/ResultDownload.tsx
import React, { useState } from 'react';
import './ResultDownload.css';

interface ResultDownloadProps {
  downloadToken: string;
  transactionCount: number;
  accountName?: string;
  statementPeriod?: string;
  warnings?: string[];
  onDownload: () => Promise<void>;
  onReset: () => void;
}

const ResultDownload: React.FC<ResultDownloadProps> = ({
  downloadToken,
  transactionCount,
  accountName,
  statementPeriod,
  warnings = [],
  onDownload,
  onReset,
}) => {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadComplete, setDownloadComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWarnings, setShowWarnings] = useState(false);

  const handleDownload = async () => {
    setIsDownloading(true);
    setError(null);
    
    try {
      await onDownload();
      setDownloadComplete(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="result-download">
      {/* Success Header */}
      <div className="success-header">
        <div className="success-icon">✅</div>
        <h2>Statement Processed Successfully!</h2>
      </div>

      {/* Summary Card */}
      <div className="summary-card">
        <h3>Summary</h3>
        
        <div className="summary-grid">
          <div className="summary-item">
            <span className="summary-label">Transactions Found</span>
            <span className="summary-value highlight">{transactionCount}</span>
          </div>
          
          {accountName && (
            <div className="summary-item">
              <span className="summary-label">Account Name</span>
              <span className="summary-value">{accountName}</span>
            </div>
          )}
          
          {statementPeriod && (
            <div className="summary-item">
              <span className="summary-label">Statement Period</span>
              <span className="summary-value">{statementPeriod}</span>
            </div>
          )}
        </div>

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="warnings-section">
            <button 
              className="warnings-toggle"
              onClick={() => setShowWarnings(!showWarnings)}
            >
              <span className="warning-icon">⚠️</span>
              <span>{warnings.length} parsing note{warnings.length !== 1 ? 's' : ''}</span>
              <span className="toggle-arrow">{showWarnings ? '▲' : '▼'}</span>
            </button>
            
            {showWarnings && (
              <ul className="warnings-list">
                {warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Download Section */}
      <div className="download-section">
        <p className="download-description">
          Your Excel file is ready. The file includes:
        </p>
        
        <ul className="features-list">
          <li>📊 Summary dashboard with totals</li>
          <li>📝 Detailed transaction list</li>
          <li>📅 Monthly breakdown</li>
          <li>📈 Transaction type analysis</li>
        </ul>

        {error && (
          <div className="download-error">
            <span>❌</span> {error}
          </div>
        )}

        <div className="download-actions">
          <button
            className={`download-button ${downloadComplete ? 'downloaded' : ''}`}
            onClick={handleDownload}
            disabled={isDownloading}
          >
            {isDownloading ? (
              <>
                <span className="button-spinner"></span>
                Preparing Download...
              </>
            ) : downloadComplete ? (
              <>
                <span>✓</span>
                Download Again
              </>
            ) : (
              <>
                <span>📥</span>
                Download Excel File
              </>
            )}
          </button>

          <button className="new-statement-button" onClick={onReset}>
            Process Another Statement
          </button>
        </div>
      </div>

      {/* Data Notice */}
      <div className="data-notice">
        <div className="notice-icon">🔐</div>
        <div className="notice-content">
          <strong>Your data is secure</strong>
          <p>
            Your PDF and generated Excel file will be automatically deleted from our 
            servers within 30 minutes. We do not store or access your financial data.
          </p>
        </div>
      </div>

      {/* Tips Section */}
      <details className="tips-section">
        <summary>Tips for using your Excel file</summary>
        <ul>
          <li>Use Excel filters to search for specific transactions</li>
          <li>Check the "Monthly Breakdown" sheet for spending patterns</li>
          <li>The "Type Analysis" sheet shows how you use MPesa most</li>
          <li>All amounts are in KES (Kenyan Shillings)</li>
        </ul>
      </details>
    </div>
  );
};

export default ResultDownload;
// frontend/src/App.tsx
import React from 'react';
import FileUpload from './components/FileUpload/FileUpload';
import PinInput from './components/PinInput/PinInput';
import ProcessingStatus from './components/ProcessingStatus/ProcessingStatus';
import ResultDownload from './components/ResultDownload/ResultDownload';
import { useStatementProcessor } from './hooks/useStatementProcessor';
import './App.css';

const App: React.FC = () => {
  const {
    state,
    handleUploadSuccess,
    handlePinSubmit,
    handleDownload,
    reset,
  } = useStatementProcessor();

  const handleError = (message: string) => {
    console.error('Upload error:', message);
    // Could display toast notification here
  };

  const renderContent = () => {
    switch (state.step) {
      case 'idle':
        return (
          <FileUpload
            onUploadSuccess={handleUploadSuccess}
            onError={handleError}
            isLoading={false}
          />
        );

      case 'uploading':
        return (
          <ProcessingStatus
            status="uploading"
            message="Uploading your statement..."
            progress={50}
          />
        );

      case 'pin_required':
        return (
          <div className="pin-step">
            <ProcessingStatus
              status="uploading"
              message="File uploaded successfully"
              progress={100}
            />
            <PinInput
              onSubmit={handlePinSubmit}
              attemptsLeft={state.attemptsLeft}
              isLoading={false}
              isLocked={state.isLocked}
              lockoutSeconds={state.lockoutSeconds}
            />
            {state.error && (
              <div className="error-message">
                <span className="error-icon">⚠️</span>
                {state.error}
              </div>
            )}
          </div>
        );

      case 'processing':
        return (
          <ProcessingStatus
            status="processing"
            message="Extracting transactions from your statement..."
            progress={65}
          />
        );

      case 'complete':
        return (
          <ResultDownload
            downloadToken={state.downloadToken!}
            transactionCount={state.transactionCount}
            accountName={state.accountName}
            statementPeriod={state.statementPeriod}
            warnings={state.warnings}
            onDownload={handleDownload}
            onReset={reset}
          />
        );

      case 'error':
        return (
          <div className="error-state">
            <div className="error-icon-large">❌</div>
            <h2>Something went wrong</h2>
            <p>{state.error}</p>
            <button className="retry-button" onClick={reset}>
              Try Again
            </button>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <div className="logo">
            <span className="logo-icon">📊</span>
            <h1>MPesa Statement Processor</h1>
          </div>
          <p className="tagline">
            Convert your MPesa PDF statements to Excel instantly
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="app-main">
        <div className="content-wrapper">
          {renderContent()}
        </div>
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <div className="footer-content">
          <div className="security-badges">
            <span className="badge">🔒 Secure Processing</span>
            <span className="badge">🗑️ Auto-Delete</span>
            <span className="badge">📱 Mobile Friendly</span>
          </div>
          
          <div className="footer-links">
            <a href="#privacy">Privacy Policy</a>
            <span className="separator">•</span>
            <a href="#terms">Terms of Use</a>
            <span className="separator">•</span>
            <a href="#contact">Contact</a>
          </div>
          
          <p className="copyright">
            © {new Date().getFullYear()} MPesa Statement Processor. 
            Not affiliated with Safaricom or MPesa.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default App;
// frontend/src/components/ProcessingStatus/ProcessingStatus.tsx
import React, { useEffect, useState } from 'react';
import './ProcessingStatus.css';

interface ProcessingStatusProps {
  status: 'uploading' | 'processing' | 'complete' | 'error';
  message?: string;
  progress?: number;
}

const ProcessingStatus: React.FC<ProcessingStatusProps> = ({
  status,
  message,
  progress = 0,
}) => {
  const [dots, setDots] = useState('');

  // Animated dots for loading states
  useEffect(() => {
    if (status === 'uploading' || status === 'processing') {
      const interval = setInterval(() => {
        setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
      }, 500);
      return () => clearInterval(interval);
    }
  }, [status]);

  const getStatusConfig = () => {
    switch (status) {
      case 'uploading':
        return {
          icon: '📤',
          title: 'Uploading',
          description: 'Uploading your statement securely...',
          color: 'blue',
          showProgress: true,
        };
      case 'processing':
        return {
          icon: '⚙️',
          title: 'Processing',
          description: 'Extracting transaction data...',
          color: 'green',
          showProgress: true,
        };
      case 'complete':
        return {
          icon: '✅',
          title: 'Complete',
          description: message || 'Your statement has been processed successfully!',
          color: 'green',
          showProgress: false,
        };
      case 'error':
        return {
          icon: '❌',
          title: 'Error',
          description: message || 'An error occurred during processing.',
          color: 'red',
          showProgress: false,
        };
      default:
        return {
          icon: '📋',
          title: 'Ready',
          description: 'Upload your statement to begin.',
          color: 'gray',
          showProgress: false,
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className={`processing-status status-${config.color}`}>
      <div className="status-container">
        {/* Icon */}
        <div className="status-icon-wrapper">
          {(status === 'uploading' || status === 'processing') ? (
            <div className="spinner">
              <div className="spinner-ring"></div>
              <span className="spinner-icon">{config.icon}</span>
            </div>
          ) : (
            <span className="status-icon">{config.icon}</span>
          )}
        </div>

        {/* Text Content */}
        <div className="status-content">
          <h3 className="status-title">
            {config.title}
            {(status === 'uploading' || status === 'processing') && (
              <span className="loading-dots">{dots}</span>
            )}
          </h3>
          <p className="status-description">{config.description}</p>
        </div>

        {/* Progress Bar */}
        {config.showProgress && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{
                  width: `${progress}%`,
                  transition: 'width 0.3s ease-in-out',
                }}
              />
            </div>
            {progress > 0 && (
              <span className="progress-text">{Math.round(progress)}%</span>
            )}
          </div>
        )}

        {/* Processing Steps (for processing status) */}
        {status === 'processing' && (
          <div className="processing-steps">
            <ProcessingStep
              step={1}
              label="Decrypting PDF"
              status={progress >= 25 ? 'complete' : progress >= 10 ? 'active' : 'pending'}
            />
            <ProcessingStep
              step={2}
              label="Extracting text"
              status={progress >= 50 ? 'complete' : progress >= 25 ? 'active' : 'pending'}
            />
            <ProcessingStep
              step={3}
              label="Parsing transactions"
              status={progress >= 75 ? 'complete' : progress >= 50 ? 'active' : 'pending'}
            />
            <ProcessingStep
              step={4}
              label="Generating Excel"
              status={progress >= 100 ? 'complete' : progress >= 75 ? 'active' : 'pending'}
            />
          </div>
        )}
      </div>

      {/* Security Notice */}
      {(status === 'uploading' || status === 'processing') && (
        <div className="security-notice">
          <span className="lock-icon">🔒</span>
          <span>Your data is processed securely and never stored permanently.</span>
        </div>
      )}
    </div>
  );
};

// Processing Step Sub-component
interface ProcessingStepProps {
  step: number;
  label: string;
  status: 'pending' | 'active' | 'complete';
}

const ProcessingStep: React.FC<ProcessingStepProps> = ({ step, label, status }) => {
  return (
    <div className={`processing-step step-${status}`}>
      <div className="step-indicator">
        {status === 'complete' ? (
          <span className="step-check">✓</span>
        ) : status === 'active' ? (
          <div className="step-spinner"></div>
        ) : (
          <span className="step-number">{step}</span>
        )}
      </div>
      <span className="step-label">{label}</span>
    </div>
  );
};

export default ProcessingStatus;
// frontend/src/components/PinInput/PinInput.tsx
import React, { useState, useRef, useEffect } from 'react';

interface PinInputProps {
  onSubmit: (pin: string) => void;
  attemptsLeft: number;
  isLoading: boolean;
  isLocked: boolean;
  lockoutSeconds: number;
}

const PinInput: React.FC<PinInputProps> = ({
  onSubmit, attemptsLeft, isLoading, isLocked, lockoutSeconds
}) => {
  const [pin, setPin] = useState('');
  const [showPin, setShowPin] = useState(false);
  const [countdown, setCountdown] = useState(lockoutSeconds);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isLocked && lockoutSeconds > 0) {
      setCountdown(lockoutSeconds);
      const timer = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [isLocked, lockoutSeconds]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pin.trim() || isLoading || isLocked) return;
    onSubmit(pin);
    setPin(''); // Clear PIN after submission
  };

  const formatCountdown = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  return (
    <div className="pin-container">
      <div className="pin-header">
        <div className="lock-icon">🔐</div>
        <h3>Enter Your Statement PIN</h3>
        <p className="pin-description">
          This is the PIN you received via SMS when requesting your MPesa statement.
        </p>
      </div>

      {isLocked ? (
        <div className="lockout-message">
          <div className="lockout-icon">⚠️</div>
          <p>Too many incorrect attempts.</p>
          <p className="countdown">Try again in <strong>{formatCountdown(countdown)}</strong></p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="pin-form">
          <div className="pin-input-group">
            <input
              ref={inputRef}
              type={showPin ? 'text' : 'password'}
              value={pin}
              onChange={(e) => {
                // Only allow digits and common PIN characters
                const sanitized = e.target.value.replace(/[^0-9+\-\s]/g, '');
                setPin(sanitized.slice(0, 20));
              }}
              placeholder="Enter PIN"
              disabled={isLoading || isLocked}
              autoComplete="off"
              autoFocus
              className="pin-input"
              aria-label="Statement PIN"
            />
            <button
              type="button"
              onClick={() => setShowPin(!showPin)}
              className="toggle-visibility"
              aria-label={showPin ? 'Hide PIN' : 'Show PIN'}
            >
              {showPin ? '👁️' : '👁️‍🗨️'}
            </button>
          </div>

          {attemptsLeft < 3 && attemptsLeft > 0 && (
            <div className="attempts-warning">
              ⚠️ {attemptsLeft} attempt{attemptsLeft !== 1 ? 's' : ''} remaining
            </div>
          )}

          <button
            type="submit"
            disabled={!pin.trim() || isLoading || isLocked}
            className="submit-btn"
          >
            {isLoading ? (
              <span className="loading-spinner">Processing...</span>
            ) : (
              'Unlock & Process Statement'
            )}
          </button>
        </form>
      )}

      <div className="pin-help">
        <details>
          <summary>Where do I find my PIN?</summary>
          <ul>
            <li>Check the SMS you received when you requested the statement</li>
            <li>The PIN is usually your phone number or a code sent via SMS</li>
            <li>Contact Safaricom on *234# if you need assistance</li>
          </ul>
        </details>
      </div>
    </div>
  );
};

export default PinInput;
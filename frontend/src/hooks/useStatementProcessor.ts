// frontend/src/hooks/useStatementProcessor.ts
import { useState, useCallback } from 'react';

type ProcessingStep = 'idle' | 'uploading' | 'pin_required' | 'processing' | 'complete' | 'error';

interface ProcessorState {
  step: ProcessingStep;
  sessionId: string | null;
  isEncrypted: boolean;
  downloadToken: string | null;
  transactionCount: number;
  error: string | null;
  warnings: string[];
  attemptsLeft: number;
  isLocked: boolean;
  lockoutSeconds: number;
  accountName: string;
  statementPeriod: string;
}

const API_BASE = '/api/v1';

export const useStatementProcessor = () => {
  const [state, setState] = useState<ProcessorState>({
    step: 'idle',
    sessionId: null,
    isEncrypted: false,
    downloadToken: null,
    transactionCount: 0,
    error: null,
    warnings: [],
    attemptsLeft: 3,
    isLocked: false,
    lockoutSeconds: 0,
    accountName: '',
    statementPeriod: '',
  });

  const handleUploadSuccess = useCallback((sessionId: string, isEncrypted: boolean) => {
    setState(prev => ({
      ...prev,
      sessionId,
      isEncrypted,
      step: isEncrypted ? 'pin_required' : 'processing',
      error: null,
    }));

    // If not encrypted, process immediately
    if (!isEncrypted) {
      processStatement(sessionId, undefined);
    }
  }, []);

  const processStatement = useCallback(async (sessionId: string, pin?: string) => {
    setState(prev => ({ ...prev, step: 'processing', error: null }));

    try {
      const response = await fetch(`${API_BASE}/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, pin }),
      });

      const data = await response.json();

      if (!response.ok) {
        if (response.status === 401) {
          // Wrong PIN
          setState(prev => ({
            ...prev,
            step: 'pin_required',
            error: data.detail,
            attemptsLeft: extractAttemptsLeft(data.detail),
          }));
          return;
        }

        if (response.status === 423) {
          // Locked out
          const lockoutSeconds = extractLockoutSeconds(data.detail);
          setState(prev => ({
            ...prev,
            step: 'pin_required',
            error: data.detail,
            isLocked: true,
            lockoutSeconds,
          }));
          return;
        }

        throw new Error(data.detail || 'Processing failed');
      }

      setState(prev => ({
        ...prev,
        step: 'complete',
        downloadToken: data.download_token,
        transactionCount: data.transaction_count,
        warnings: data.parsing_warnings || [],
        accountName: data.account_name || '',
        statementPeriod: data.statement_period || '',
        error: null,
      }));

    } catch (error) {
      setState(prev => ({
        ...prev,
        step: 'error',
        error: error instanceof Error ? error.message : 'Processing failed',
      }));
    }
  }, []);

  const handlePinSubmit = useCallback((pin: string) => {
    if (state.sessionId) {
      processStatement(state.sessionId, pin);
    }
  }, [state.sessionId, processStatement]);

  const handleDownload = useCallback(async () => {
    if (!state.downloadToken) return;

    try {
      const response = await fetch(`${API_BASE}/download/${state.downloadToken}`);
      
      if (!response.ok) {
        throw new Error('Download failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `MPesa_Statement_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: 'Download failed. Please try again.',
      }));
    }
  }, [state.downloadToken]);

  const reset = useCallback(() => {
    setState({
      step: 'idle',
      sessionId: null,
      isEncrypted: false,
      downloadToken: null,
      transactionCount: 0,
      error: null,
      warnings: [],
      attemptsLeft: 3,
      isLocked: false,
      lockoutSeconds: 0,
      accountName: '',
      statementPeriod: '',
    });
  }, []);

  return {
    state,
    handleUploadSuccess,
    handlePinSubmit,
    handleDownload,
    reset,
  };
};

// Helpers
const extractAttemptsLeft = (message: string): number => {
  const match = message.match(/(\d+) attempt/);
  return match ? parseInt(match[1]) : 2;
};

const extractLockoutSeconds = (message: string): number => {
  const match = message.match(/(\d+) seconds/);
  return match ? parseInt(match[1]) : 900;
};
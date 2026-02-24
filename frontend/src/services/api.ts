// frontend/src/services/api.ts
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface UploadResponse {
  session_id: string;
  filename: string;
  is_encrypted: boolean;
  file_size_kb: number;
  message: string;
}

interface ProcessResponse {
  success: boolean;
  download_token?: string;
  transaction_count: number;
  parsing_warnings: string[];
  statement_period?: string;
  account_name?: string;
  message: string;
}

class ApiService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    
    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || error.error || 'Request failed');
    }

    return response.json();
  }

  async uploadFile(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request<UploadResponse>('/upload', {
      method: 'POST',
      body: formData,
    });
  }

  async processStatement(sessionId: string, pin?: string): Promise<ProcessResponse> {
    return this.request<ProcessResponse>('/process', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        pin: pin,
      }),
    });
  }

  async downloadFile(downloadToken: string): Promise<Blob> {
    const response = await fetch(`${API_BASE}/download/${downloadToken}`);
    
    if (!response.ok) {
      throw new Error('Download failed');
    }

    return response.blob();
  }

  async healthCheck(): Promise<{ status: string }> {
    return this.request('/health');
  }
}

export const apiService = new ApiService();
export default apiService;
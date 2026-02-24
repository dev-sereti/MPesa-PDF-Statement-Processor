// frontend/src/components/FileUpload/FileUpload.tsx
import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';

interface FileUploadProps {
  onUploadSuccess: (sessionId: string, isEncrypted: boolean) => void;
  onError: (message: string) => void;
  isLoading: boolean;
}

const FileUpload: React.FC<FileUploadProps> = ({ onUploadSuccess, onError, isLoading }) => {
  const [uploadProgress, setUploadProgress] = useState(0);

  const uploadFile = useCallback(async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/v1/upload', {
        method: 'POST',
        body: formData,
        // Note: Don't set Content-Type header - browser sets it with boundary
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }

      const data = await response.json();
      onUploadSuccess(data.session_id, data.is_encrypted);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Upload failed');
    }
  }, [onUploadSuccess, onError]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (file) uploadFile(file);
  }, [uploadFile]);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024, // 10MB
    disabled: isLoading,
  });

  return (
    <div className="upload-container">
      <div
        {...getRootProps()}
        className={`dropzone ${isDragActive ? 'active' : ''} ${isLoading ? 'disabled' : ''}`}
      >
        <input {...getInputProps()} />
        <div className="dropzone-content">
          <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
          </svg>
          {isDragActive ? (
            <p>Drop your MPesa statement here...</p>
          ) : (
            <>
              <p><strong>Drop your MPesa PDF statement here</strong></p>
              <p className="subtitle">or click to browse files</p>
              <p className="constraints">PDF files only • Maximum 10MB</p>
            </>
          )}
        </div>
      </div>

      {fileRejections.length > 0 && (
        <div className="error-message">
          {fileRejections[0].errors[0].message}
        </div>
      )}
    </div>
  );
};

export default FileUpload;
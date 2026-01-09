/**
 * Certificate Uploader Component (CAB-313)
 *
 * Allows users to upload and validate client certificates for mTLS subscriptions.
 * Features:
 * - Drag & drop or click to upload
 * - PEM file validation
 * - Certificate preview with validity status
 * - Expiration warnings
 */

import { useState, useCallback, useRef } from 'react';
import {
  Upload,
  FileCheck,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  X,
  Shield,
  Calendar,
  Key,
  Building,
  Loader2,
} from 'lucide-react';
import {
  uploadCertificate,
  validateCertificate,
  formatCertificateDate,
  type CertificateInfo,
  type CertificateValidationResult,
} from '../../services/certificateValidator';

interface CertificateUploaderProps {
  onCertificateValidated?: (result: CertificateValidationResult) => void;
  onCertificateCleared?: () => void;
  required?: boolean;
  className?: string;
}

export function CertificateUploader({
  onCertificateValidated,
  onCertificateCleared,
  required = false,
  className = '',
}: CertificateUploaderProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<CertificateValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setIsLoading(true);
      setError(null);

      try {
        // Check file size (max 1MB for certificates)
        if (file.size > 1024 * 1024) {
          setError('File too large. Maximum size is 1MB.');
          setIsLoading(false);
          return;
        }

        // Check file extension
        const validExtensions = ['.pem', '.crt', '.cer', '.cert'];
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();
        if (!validExtensions.includes(ext)) {
          setError(`Invalid file type. Allowed: ${validExtensions.join(', ')}`);
          setIsLoading(false);
          return;
        }

        const validationResult = await uploadCertificate(file);
        setResult(validationResult);
        onCertificateValidated?.(validationResult);
      } catch (err) {
        setError('Failed to validate certificate');
      } finally {
        setIsLoading(false);
      }
    },
    [onCertificateValidated]
  );

  const handlePaste = useCallback(
    async (event: React.ClipboardEvent) => {
      const text = event.clipboardData.getData('text');
      if (text.includes('-----BEGIN CERTIFICATE-----')) {
        setIsLoading(true);
        setError(null);

        try {
          const validationResult = await validateCertificate(text);
          setResult(validationResult);
          onCertificateValidated?.(validationResult);
        } catch {
          setError('Failed to validate pasted certificate');
        } finally {
          setIsLoading(false);
        }
      }
    },
    [onCertificateValidated]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setIsDragOver(false);

      const file = event.dataTransfer.files[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInput = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const handleClear = useCallback(() => {
    setResult(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    onCertificateCleared?.();
  }, [onCertificateCleared]);

  const getStatusIcon = (cert: CertificateInfo) => {
    if (cert.is_expired) return <AlertCircle className="h-5 w-5 text-red-500" />;
    if (cert.expires_soon) return <AlertTriangle className="h-5 w-5 text-amber-500" />;
    if (cert.is_valid) return <CheckCircle className="h-5 w-5 text-green-500" />;
    return <AlertCircle className="h-5 w-5 text-gray-500" />;
  };

  const getStatusText = (cert: CertificateInfo) => {
    if (cert.is_expired) return 'Expired';
    if (cert.expires_soon) return `Expires in ${cert.days_until_expiry} days`;
    if (cert.is_valid) return 'Valid';
    return 'Unknown';
  };

  const getStatusColor = (cert: CertificateInfo) => {
    if (cert.is_expired) return 'border-red-300 bg-red-50';
    if (cert.expires_soon) return 'border-amber-300 bg-amber-50';
    if (cert.is_valid) return 'border-green-300 bg-green-50';
    return 'border-gray-300 bg-gray-50';
  };

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700">
          Client Certificate {required && <span className="text-red-500">*</span>}
        </label>
        {result && (
          <button
            type="button"
            onClick={handleClear}
            className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <X className="h-4 w-4" />
            Clear
          </button>
        )}
      </div>

      {!result ? (
        // Upload Area
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onPaste={handlePaste}
          onClick={handleClick}
          className={`
            relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
            transition-colors duration-200
            ${isDragOver ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-gray-400'}
            ${isLoading ? 'pointer-events-none opacity-60' : ''}
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pem,.crt,.cer,.cert"
            onChange={handleFileInput}
            className="hidden"
          />

          {isLoading ? (
            <div className="flex flex-col items-center">
              <Loader2 className="h-10 w-10 text-primary-500 animate-spin mb-3" />
              <p className="text-sm text-gray-600">Validating certificate...</p>
            </div>
          ) : (
            <>
              <Upload className="h-10 w-10 text-gray-400 mx-auto mb-3" />
              <p className="text-sm text-gray-600 mb-1">
                <span className="text-primary-600 font-medium">Click to upload</span> or drag and
                drop
              </p>
              <p className="text-xs text-gray-500">PEM, CRT, CER files (max 1MB)</p>
              <p className="text-xs text-gray-400 mt-2">Or paste PEM content directly</p>
            </>
          )}
        </div>
      ) : (
        // Certificate Preview
        <div className={`rounded-lg border-2 p-4 ${getStatusColor(result.certificate!)}`}>
          {result.certificate && (
            <div className="space-y-3">
              {/* Status Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {getStatusIcon(result.certificate)}
                  <span className="font-medium text-gray-900">{getStatusText(result.certificate)}</span>
                </div>
                <FileCheck className="h-5 w-5 text-gray-400" />
              </div>

              {/* Certificate Details */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div className="flex items-start gap-2">
                  <Building className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-gray-500 text-xs">Subject</p>
                    <p className="text-gray-900 break-all">{result.certificate.subject}</p>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Shield className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-gray-500 text-xs">Issuer</p>
                    <p className="text-gray-900 break-all">{result.certificate.issuer}</p>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Calendar className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-gray-500 text-xs">Valid From</p>
                    <p className="text-gray-900">{formatCertificateDate(result.certificate.valid_from)}</p>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Calendar className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-gray-500 text-xs">Valid To</p>
                    <p className="text-gray-900">{formatCertificateDate(result.certificate.valid_to)}</p>
                  </div>
                </div>

                <div className="flex items-start gap-2 md:col-span-2">
                  <Key className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-gray-500 text-xs">Fingerprint (SHA-256)</p>
                    <p className="text-gray-900 font-mono text-xs break-all">
                      {result.certificate.fingerprint_sha256}
                    </p>
                  </div>
                </div>

                {result.certificate.san.length > 0 && (
                  <div className="flex items-start gap-2 md:col-span-2">
                    <Shield className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-gray-500 text-xs">Subject Alternative Names</p>
                      <p className="text-gray-900 text-xs">{result.certificate.san.join(', ')}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Warnings */}
              {result.warnings.length > 0 && (
                <div className="mt-3 p-2 bg-amber-100 rounded-lg">
                  {result.warnings.map((warning, idx) => (
                    <p key={idx} className="text-sm text-amber-800 flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                      {warning}
                    </p>
                  ))}
                </div>
              )}

              {/* Errors */}
              {result.errors.length > 0 && (
                <div className="mt-3 p-2 bg-red-100 rounded-lg">
                  {result.errors.map((err, idx) => (
                    <p key={idx} className="text-sm text-red-800 flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 flex-shrink-0" />
                      {err}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Help Text */}
      <p className="text-xs text-gray-500">
        Upload your client certificate for mTLS authentication. The certificate must be in PEM
        format and not expired.
      </p>
    </div>
  );
}

export default CertificateUploader;

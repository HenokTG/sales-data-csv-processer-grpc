import React, { useState, useEffect, useRef } from "react";
import axios, { type AxiosProgressEvent } from "axios";

import { Upload, Loader, AlertTriangle, CheckCircle } from "lucide-react";

import type {
  JobStatusResponse,
  CompleteJobResult,
  FailedJobStatus,
  JobStatus,
  ProcessResult,
  DownloadResult,
  UploadResponse,
  OngoingJobStatus,
} from "./types";

import { formatBytes, generateSummaryItems } from "./utility";
import DownloadButton from "./components/DownloadButton";

// --- React Component ---
function App() {
  const apiKey = import.meta.env.VITE_API_KEY;
  const apiURL = import.meta.env.VITE_GATEWAY_URL;
  const pollingInterval = Number(import.meta.env.VITE_POLL_INTERVAL);

  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus>("idle");
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [processProgress, setProcessProgress] = useState<number>(0);
  const [result, setResult] = useState<
    CompleteJobResult | OngoingJobStatus | null
  >(null);

  const [fileSizeBytes, setFileSizeBytes] = useState<number>(0);
  const [processingMessage, setProcessingMessage] = useState("");

  const pollIntervalRef = useRef<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetState = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setFile(null);
    setJobId(null);
    setJobStatus("idle");
    setError(null);
    setResult(null);
    setFileSizeBytes(0);
    setUploadProgress(0);
    setProcessProgress(0);

    setProcessingMessage("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleFileChange = (selectedFile: File) => {
    if (selectedFile?.type !== "text/csv") {
      setError("Please select a valid CSV file.");
      setFileSizeBytes(0);
      setFile(null);
    } else {
      setError(null);
      setFile(selectedFile);
      setFileSizeBytes(selectedFile.size);
    }
  };

  const handleClick = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.target.files && e.target.files.length > 0) {
      handleFileChange(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const pollStatus = async () => {
    if (!jobId) return;

    try {
      const response = await axios.get<JobStatusResponse>(
        `${apiURL}/status/${jobId}`,
        { headers: { "X-API-Key": apiKey } }
      );
      const resultData = response.data;

      // Update local states based on backend status
      setFileSizeBytes(resultData?.file_size_bytes || fileSizeBytes); // Update size if necessary

      if (resultData.status === "complete") {
        setResult(resultData as CompleteJobResult);
        setJobStatus("complete");
        setProcessProgress(resultData.processed_percentage);

        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      } else if (resultData.status === "failed") {
        setError((resultData as FailedJobStatus).error || "Processing failed.");
        setJobStatus("failed");
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      } else if (resultData.status === "processing") {
        // This confirms the job is actively being tracked by the backend
        setJobStatus("processing");
        setResult(resultData as OngoingJobStatus);
        setProcessProgress(resultData.processed_percentage);
        setProcessingMessage(resultData.message || "Processing...");
      }
    } catch (err: any) {
      console.error("Polling Error:", err);
      // Only set to failed if polling explicitly returns a failure or HTTP error
      if (err.response?.status === 404) {
        // Job might have been cleaned up or ID was wrong.
        // In a real app, this would be handled better. For now, we assume failure.
        setError(
          "Job status could not be retrieved. It may have failed or expired."
        );
        setJobStatus("failed");
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }
    }
  };

  const isRunning = jobStatus === "uploading" || jobStatus === "processing";

  // Polling Effect
  useEffect(() => {
    if (jobId && isRunning) {
      // Clear any existing interval before setting a new one
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }

      // Set up the new polling interval
      pollIntervalRef.current = window.setInterval(pollStatus, pollingInterval);
    }

    // Cleanup function to clear the interval when the component unmounts or dependencies change
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [jobId, jobStatus]); // Depend on jobId and jobStatus

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file, file.name);

    // 1. Send file size to the gateway
    formData.append("file_size_bytes", file.size.toString());

    // Reset previous job results and status
    resetState();
    setJobStatus("uploading");
    setFileSizeBytes(file.size); // Set the size immediately in state

    try {
      const { data } = await axios.post<UploadResponse>(
        `${apiURL}/upload`,
        formData,
        {
          headers: {
            "Content-Type": `multipart/form-data; boundary=${
              formData.getBoundary ? formData.getBoundary() : "---boundary---"
            }`,
            "X-API-Key": apiKey,
          },
          onUploadProgress: (progressEvent: AxiosProgressEvent) => {
            const total = progressEvent.total || 0;
            const percent = Math.round((progressEvent.loaded * 100) / total);
            setUploadProgress(percent);
          },
          // Setting maxContentLength/maxBodyLength to Infinity ensures Axios does not prematurely cut off large streams.
          maxContentLength: Infinity,
          maxBodyLength: Infinity,
        }
      );

      // Success! Job is now processing on the backend
      setJobId(data.job_id);
      setUploadProgress(100);
      setJobStatus("processing");
    } catch (err) {
      console.error("Upload error:", err);
      let errorMsg = "File upload failed.";
      if (axios.isAxiosError(err)) {
        errorMsg = err.response?.data?.detail || "File upload failed.";
        if (err.code === "ERR_NETWORK") {
          errorMsg =
            "Cannot connect to server. Is the gateway running on port 8000?";
        }
      }
      setError(errorMsg);
      setJobStatus("failed");
    }
  };

  const summaryItems =
    jobStatus === "complete"
      ? generateSummaryItems(result as ProcessResult)
      : [];

  return (
    <div className="container">
      <header>
        <h1>High-Performance CSV Processor</h1>
        <p>
          Upload a large file for streaming aggregation via FastAPI Gateway and
          Bi-directional gRPC.
        </p>
      </header>

      <main>
        <form onSubmit={handleSubmit} className="upload-form">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`file-dropzone ${file ? "file-selected" : ""}`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleClick}
              className="hidden"
            />
            <div className="flex flex-col items-center text-center">
              <Upload
                size={32}
                className={`${file ? "file-selected" : "text-indigo-500"}`}
              />
              <p className={`${file ? "file-selected" : ""}`}>
                {file
                  ? `File Selected: ${file.name}`
                  : "Drag and drop your CSV file here"}
              </p>
            </div>
          </div>

          <button
            type="submit"
            disabled={!file || isRunning}
            className="submit-button"
          >
            {isRunning ? (
              <div className="btn-lable-icon">
                <Loader className="spinner" />
                <span>Processing...</span>
              </div>
            ) : (
              "Upload and Process"
            )}
          </button>
        </form>

        {jobStatus !== "idle" && (
          <div className="status-container">
            {isRunning && (
              <div className="status-progress-wrapper">
                <div className="progress-label-wrapper">
                  <p className="progress-label">
                    {jobStatus === "uploading"
                      ? `Uploading... ${uploadProgress}% Complete`
                      : processingMessage}
                  </p>
                  {isRunning && jobId && (
                    <p className="job-id-label">
                      Job ID: {result?.filename} - {jobId}
                    </p>
                  )}
                </div>

                {/* Show upload progress bar only during the uploading phase */}
                {jobStatus === "uploading" && (
                  <div className="progress-bar">
                    <div
                      className="progress-bar-inner uploading"
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
                  </div>
                )}
                {/* Show estimated progress bar during the processing phase */}
                {jobStatus === "processing" && (
                  <div className="progress-bar">
                    <div
                      className="progress-bar-inner processing"
                      style={{ width: `${processProgress}%` }}
                    ></div>
                  </div>
                )}
              </div>
            )}

            {jobStatus === "failed" && (
              <div className="status-error btn-lable-icon">
                <AlertTriangle />
                <strong>Error:</strong> {error}
              </div>
            )}

            {jobStatus === "complete" && result && (
              <div className="status-complete">
                <h3 className="btn-lable-icon">
                  <CheckCircle />
                  Processing Complete!
                </h3>
                <div className="result-card">
                  <h4>Original File:</h4>
                  <ul className="summary-list">
                    <li>
                      <span style={{ fontSize: 16 }}>{result.filename}</span>
                      <strong>Size: {formatBytes(fileSizeBytes)}</strong>
                    </li>
                  </ul>

                  <h4>Summary:</h4>
                  <ul className="summary-list">
                    {summaryItems.map((item, index) => (
                      <li key={index}>
                        <span style={{ fontSize: 16 }}>{item.label}</span>
                        <strong>{item.value}</strong>
                      </li>
                    ))}
                  </ul>
                  <DownloadButton
                    label="Download Result"
                    result={result as DownloadResult}
                  />
                </div>
              </div>
            )}
          </div>
        )}
        {jobStatus !== "idle" && (
          <button onClick={resetState} className="reset-button">
            Start Over
          </button>
        )}
      </main>
    </div>
  );
}

export default App;

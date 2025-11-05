// --- Type Definitions ---
export type JobStatus =
  | "idle"
  | "uploading"
  | "processing"
  | "complete"
  | "failed";

export interface CompleteJobResult {
  status: "complete";
  filename: string;
  job_id: string;
  rows_processed: number;
  malformed_rows: number;
  total_sales: number;
  unique_departments: number;
  processed_percentage: number;
  processing_time_seconds: number;
  result_file_name: string;
  result_file_url: string;
  file_size_bytes: number;
}

export interface OngoingJobStatus {
  status: "processing" | "queued"; // Status from backend (main.py)
  job_id: string;
  filename: string;
  rows_processed: number; // New field for real-time processing progress
  malformed_rows: number; // New field for real-time processing progress
  processed_percentage: number; // New field for real-time processing progress
  message?: string;
  file_size_bytes: number;
}

export interface FailedJobStatus {
  status: "failed";
  job_id: string;
  filename: string;
  error: string;
  file_size_bytes: number;
}

// Type for the data from /status/{job_id}
export type JobStatusResponse =
  | OngoingJobStatus
  | CompleteJobResult
  | FailedJobStatus;

// Type for the data from /upload
export interface UploadResponse {
  job_id: string;
}

// Export the structure of the function input
export interface ProcessResult {
  rows_processed: number;
  malformed_rows: number;
  total_sales: number;
  unique_departments: number;
  processing_time_seconds: number;
}

// Export for download button
export interface DownloadResult {
  result_file_url: string;
  result_file_name?: string;
  filename?: string;
}

// Export the shape of the items in the output array
export interface SummaryItem {
  label: string;
  value: string;
}

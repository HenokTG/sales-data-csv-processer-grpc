import React from "react";
import { Download } from "lucide-react";

import type { DownloadResult } from "../types";

interface DownloadButtonProps {
  result: DownloadResult;
  label?: string;
  className?: string;
}

const DownloadButton: React.FC<DownloadButtonProps> = ({
  label,
  result,
  className = "download-button btn-lable-icon",
}) => {
  const apiKey = import.meta.env.VITE_API_KEY;
  const apiURL = import.meta.env.VITE_GATEWAY_URL;

  const handleDownload = async (): Promise<void> => {
    try {
      const response = await fetch(`${apiURL}${result.result_file_url}`, {
        headers: {
          "X-API-Key": apiKey,
        },
      });

      if (!response.ok) {
        throw new Error(
          `Download failed: ${response.status} ${response.statusText}`
        );
      }

      const blob: Blob = await response.blob();
      const url: string = window.URL.createObjectURL(blob);
      const a: HTMLAnchorElement = document.createElement("a");
      a.style.display = "none";
      a.href = url;

      // Extract filename from response headers or use a default
      const contentDisposition: string | null = response.headers.get(
        "Content-Disposition"
      );

      let filename: string = "Processed_results.csv";

      if (contentDisposition) {
        const filenameMatch: RegExpMatchArray | null =
          contentDisposition.match(/filename="(.+)"/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1];
        }
      } else if (result.filename) {
        // Fallback to using the original filename from result
        filename = `processed_${result.filename}_${Date.now()}`;
      } else if (result.result_file_name) {
        // Use the result file name if available [UUID]
        filename = result.result_file_name;
      }

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error("Download error:", error);
      alert("Download failed. Please try again.");
    }
  };

  return (
    <span onClick={handleDownload} className={className}>
      <Download />
      <span>{label ?? "Download"}</span>
    </span>
  );
};

export default DownloadButton;

import { type ProcessResult, type SummaryItem } from "./types";

// Formatters
const formatBytes = (bytes: number | null) => {
  if (bytes === null) return "N/A";
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (
    (bytes / Math.pow(1024, i)).toFixed(2) +
    " " +
    ["B", "KB", "MB", "GB", "TB"][i]
  );
};

const formatTimeShort = (s: number): string => {
  s = Math.floor(s);
  if (s < 0 || !Number.isInteger(s)) return "Invalid input";

  const H = Math.floor(s / 3600);
  const M = Math.floor((s % 3600) / 60);
  const S = s % 60;

  const pad = (n: number) => n.toString().padStart(2, "0");

  // Build the string conditionally using template literals and ternaries
  const hhPart = s >= 3600 ? `${pad(H)} Hr:` : "";
  const mmPart = s >= 60 ? `${pad(M)} Mins:` : "";
  const ssPart = `${pad(S)} secs`;

  // The logic is embedded in the variable definitions above
  return `${hhPart}${mmPart}${ssPart}`;
};

const generateSummaryItems = (
  result: ProcessResult | undefined
): SummaryItem[] => {
  if (!result) {
    // Return an empty array or default items if the result is missing
    return [];
  }

  const summaryItems: SummaryItem[] = [
    {
      label: "Rows Processed:",
      value: result.rows_processed.toLocaleString(),
    },
    {
      label: "Malformed Rows:",
      value: result.malformed_rows.toLocaleString(),
    },
    {
      label: "Total Sales:",
      value: result.total_sales.toLocaleString(),
    },
    {
      label: "Unique Departments:",
      value: result.unique_departments.toLocaleString(),
    },
    {
      label: "Time Taken (Backend):",
      // Since 'result' is guaranteed to exist here, we remove the '?' and the 'as number' assertion
      value: `${formatTimeShort(result.processing_time_seconds)}`,
    },
  ];

  return summaryItems;
};

export { formatBytes, formatTimeShort, generateSummaryItems };

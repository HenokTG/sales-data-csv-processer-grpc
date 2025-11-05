"""
Core CSV Streaming Processor.

This module contains the logic for incrementally reading and aggregating
sales data from a CSV file stream. It is designed for low memory footprint
(O(D) where D is the number of unique departments) and handles streaming I/O.
"""

import csv
import logging
from io import StringIO
from typing import Dict, Optional
from dataclasses import dataclass
from collections import defaultdict

from .storage import StorageBackend

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@dataclass
class ProcessingStats:
    """Statistics about the CSV processing operation."""

    rows_processed: int = 0
    malformed_rows: int = 0
    processed_bytes: int = 0
    unique_departments: int = 0
    total_sales: int = 0


class CSVProcessingError(Exception):
    """Custom exception for CSV processing errors."""

    pass


class StreamProcessor:
    """
    Processes a CSV stream chunk by chunk, aggregating sales
    per department in memory, with O(D) space complexity (where D = number of unique departments),
    without loading the entire file into memory.
    """

    def __init__(self, storage_backend: Optional[StorageBackend] = None):
        self.department_sales: Dict[str, int] = defaultdict(int)
        self._buffer: str = ""
        self._is_header: bool = True
        self._stats = ProcessingStats()

        self.storage_backend = storage_backend

        log.info("StreamProcessor initialized.")

    def process_chunk(self, chunk: bytes) -> None:
        """
        Process a single raw chunk of bytes from the stream.
        Handles partial lines by buffering.

        Args:
            chunk: A raw bytes chunk from the file stream.

        Raises:
            CSVProcessingError: If chunk processing fails critically.
        """
        try:
            decoded_chunk = self._decode_chunk(chunk)
            self._stats.processed_bytes += len(chunk)

            data = self._buffer + decoded_chunk
            lines = data.splitlines(keepends=True)

            self._buffer = self._handle_partial_line(data, lines)
            self._process_complete_lines(lines)

        except Exception as e:
            log.error(f"Failed to process chunk: {e}")
            raise CSVProcessingError(f"Chunk processing failed: {e}") from e

    def _decode_chunk(self, chunk: bytes) -> str:
        """Decode bytes chunk to string with error handling."""
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError as e:
            log.warning(f"Unicode decode error in chunk: {e}")
            # Attempt to recover by replacing problematic characters
            return chunk.decode("utf-8", errors="replace")

    def _handle_partial_line(self, data: str, lines: list[str]) -> str:
        """Handle partial line at the end of chunk."""
        if not data.endswith("\n") and lines:
            return lines.pop()
        return ""

    def _process_complete_lines(self, lines: list[str]) -> None:
        """Process all complete lines from the chunk."""
        for line in lines:
            if self._is_header:
                self._handle_header(line.strip())
            else:
                self._process_row(line.strip())

    def _handle_header(self, header_line: str) -> None:
        """Process and validate CSV header."""
        log.info(f"CSV Header found: {header_line}")
        # Optional: Validate header format
        expected_columns = 3
        try:
            f = StringIO(header_line)
            reader = csv.reader(f)
            header_columns = next(reader)
            if len(header_columns) != expected_columns:
                log.warning(
                    f"Unexpected header format. Expected {expected_columns} columns, got {len(header_columns)}"
                )
        except (csv.Error, StopIteration) as e:
            log.warning(f"Failed to parse header: {e}")

        self._is_header = False

    def _process_row(self, row_str: str) -> None:
        """
        Parses a single row string and updates department_sales.
        Includes comprehensive error handling for malformed rows.
        """
        try:
            department, _, sales_str = self._parse_csv_row(row_str)

            if not self._validate_row_data(department, sales_str):
                self._stats.malformed_rows += 1
                return

            sales = int(sales_str)
            if sales < 0:
                log.warning(f"Skipping row with negative sales: {row_str}")
                self._stats.malformed_rows += 1
                return

            # Core aggregation
            self.department_sales[department] += sales
            self._stats.rows_processed += 1

        except Exception as e:
            log.warning(f"Malformed row (parse error): {row_str} - Error: {e}")
            self._stats.malformed_rows += 1

    def _parse_csv_row(self, row_str: str) -> tuple[str, str, str]:
        """Parse a CSV row into its components."""
        f = StringIO(row_str)
        reader = csv.reader(f)
        parts = next(reader)

        if len(parts) != 3:
            raise ValueError(f"Expected 3 columns, got {len(parts)}")

        return parts[0].strip(), parts[1].strip(), parts[2].strip()

    def _validate_row_data(self, department: str, sales_str: str) -> bool:
        """Validate row data for required format."""
        if not department:
            log.warning("Malformed row: empty department")
            return False

        if not sales_str:
            log.warning("Malformed row: empty sales value")
            return False

        # Validate sales is numeric
        if not sales_str.isdigit() and (
            sales_str[0] == "-" and not sales_str[1:].isdigit()
        ):
            log.warning(f"Malformed row: sales value is not numeric: {sales_str}")
            return False

        return True

    def finalize(self, output_path: str, use_storage: bool = False) -> ProcessingStats:
        """
        Writes the aggregated results to a new CSV file and returns stats.
        Must be called after all chunks have been processed.

        Args:
            output_path: The full path to the result CSV file.
            use_storage: If True, use the configured storage backend

        Returns:
            ProcessingStats: Statistics about the processing operation.

        Raises:
            CSVProcessingError: If file writing fails.
        """
        log.info(f"Finalizing aggregation. Writing results to {output_path}")

        self._process_remaining_buffer()
        self._update_final_stats()

        if use_storage and self.storage_backend:
            # Use storage backend (S3 or other)
            content = self._generate_csv_content()
            stored_path = self.storage_backend.save_file(output_path, content)
            log.info(f"Results saved via storage backend: {stored_path}")
        else:
            # Use local filesystem (original behavior)
            self._write_output_file(output_path)

        log.info("Successfully wrote result file.")

        return self._stats

    def _process_remaining_buffer(self) -> None:
        """Process any remaining data in the buffer."""
        if self._buffer and not self._is_header:
            log.info("Processing final buffered row.")
            self._process_row(self._buffer.strip())

    def _update_final_stats(self) -> None:
        """Update statistics with final values."""
        self._stats.unique_departments = len(self.department_sales)
        self._stats.total_sales = sum(self.department_sales.values())

    def _write_output_file(self, output_path: str) -> None:
        """Write aggregated results to output CSV file."""
        try:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Write Header
                writer.writerow(["Department Name", "Total Number of Sales"])

                # Write data sorted by department name for consistent output
                for department, sales in sorted(self.department_sales.items()):
                    writer.writerow([department, sales])

        except IOError as e:
            error_msg = f"Failed to write output file at {output_path}: {e}"
            log.error(error_msg)
            raise CSVProcessingError(error_msg) from e

    def _generate_csv_content(self) -> str:
        """Generate CSV content as string for storage backends."""
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Write Header
        writer.writerow(["Department Name", "Total Number of Sales"])

        # Write data sorted by department name
        for department, sales in sorted(self.department_sales.items()):
            writer.writerow([department, sales])

        return output.getvalue()

    def get_storage_file_url(self, file_path: str) -> Optional[str]:
        """Get accessible URL for stored file."""
        if self.storage_backend:
            return self.storage_backend.get_file_url(file_path)
        return None

    @property
    def rows_processed(self) -> int:
        """Returns the number of rows processed so far."""
        return self._stats.rows_processed

    @property
    def malformed_rows(self) -> int:
        """Returns the number of malformed rows encountered so far."""
        return self._stats.malformed_rows

    @property
    def processed_bytes(self) -> int:
        """Returns the number of bytes processed so far."""
        return self._stats.processed_bytes

    @property
    def stats(self) -> ProcessingStats:
        """Returns current processing statistics."""
        return ProcessingStats(
            rows_processed=self._stats.rows_processed,
            malformed_rows=self._stats.malformed_rows,
            processed_bytes=self._stats.processed_bytes,
            unique_departments=len(self.department_sales),
            total_sales=sum(self.department_sales.values()),
        )

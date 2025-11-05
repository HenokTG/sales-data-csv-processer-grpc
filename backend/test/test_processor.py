import os
import sys
import csv
import pytest
from collections import defaultdict

# Add the parent directory to Python path so we can import processor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from processor.processor import StreamProcessor


# Fixture for a processor instance
@pytest.fixture
def processor():
    """Returns a new StreamProcessor instance for each test."""
    return StreamProcessor()


def test_init(processor):
    """Test StreamProcessor initialization."""
    assert processor.department_sales == defaultdict(int)
    assert processor._buffer == ""
    assert processor._is_header == True
    assert processor.rows_processed == 0


def test_simple_aggregation(processor):
    """Test basic CSV processing and aggregation."""
    header = b"Department Name,Date,Number of Sales\n"
    row1 = b"Electronics,2023-08-01,100\n"
    row2 = b"Clothing,2023-08-01,200\n"
    row3 = b"Electronics,2023-08-02,150\n"

    processor.process_chunk(header)
    processor.process_chunk(row1)
    processor.process_chunk(row2)
    processor.process_chunk(row3)

    assert processor.department_sales["Electronics"] == 250
    assert processor.department_sales["Clothing"] == 200
    assert processor.rows_processed == 3


def test_chunk_splitting(processor, tmp_path):
    """Test processing chunks with split rows."""
    processor.process_chunk(b"Department Name,Date,Number of Sales\n")
    processor.process_chunk(b"Electronics,2023-08-01,100\nClot")  # Partial row
    processor.process_chunk(b"hing,2023-08-01,200\n")  # Complete partial row
    processor.process_chunk(b"Electronics,2023-08-02,150")  # No newline

    # Before finalize, only complete rows are processed
    assert processor.department_sales["Electronics"] == 100
    assert processor.department_sales["Clothing"] == 200

    # Process the final buffered chunk
    output_file = tmp_path / "test_output.csv"
    processor.finalize(str(output_file))

    # After finalize, all rows should be processed
    assert processor.department_sales["Electronics"] == 250
    assert processor.department_sales["Clothing"] == 200
    assert processor.rows_processed == 3


def test_malformed_rows(processor):
    """Test handling of malformed rows."""
    header = b"Department Name,Date,Number of Sales\n"
    processor.process_chunk(header)
    processor.process_chunk(b"Electronics,2023-08-01,100\n")
    processor.process_chunk(b"Clothing,not-a-date,200\n")  # Valid, date is ignored
    processor.process_chunk(b"Books,2023-08-01,not-a-number\n")  # Malformed
    processor.process_chunk(b"Too,few,cols\n")  # Malformed
    processor.process_chunk(b"Electronics,2023-08-02,50\n")
    processor.process_chunk(b"Home,2023-08-02,-50\n")  # Malformed (negative sales)
    processor.process_chunk(b",2023-08-02,10\n")  # Malformed (empty dept)

    assert processor.department_sales["Electronics"] == 150
    assert processor.department_sales["Clothing"] == 200
    assert processor.rows_processed == 3
    assert processor.malformed_rows == 4


def test_finalize_output_file(processor, tmp_path):
    """Test final output file generation."""
    output_file = tmp_path / "results.csv"

    header = b"Department Name,Date,Number of Sales\n"
    processor.process_chunk(header)
    processor.process_chunk(b"A,2023-08-01,10\n")
    processor.process_chunk(b"B,2023-08-01,20\n")
    processor.process_chunk(b"A,2023-08-02,30\n")

    stats = processor.finalize(str(output_file))

    assert stats.rows_processed == 3
    assert stats.total_sales == 60
    assert stats.unique_departments == 2

    assert output_file.exists()

    with open(output_file, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["Department Name", "Total Number of Sales"]

        data = {row[0]: int(row[1]) for row in reader}
        assert data == {"A": 40, "B": 20}


def test_no_data_rows(processor, tmp_path):
    """Test processing with only header and no data rows."""
    output_file = tmp_path / "no_data_results.csv"

    processor.process_chunk(b"Department Name,Date,Number of Sales\n")

    stats = processor.finalize(str(output_file))

    assert stats.rows_processed == 0
    assert stats.total_sales == 0
    assert stats.unique_departments == 0

    with open(output_file, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["Department Name", "Total Number of Sales"]
        # Should be no more rows
        assert len(list(reader)) == 0


def test_unicode_handling(processor):
    """Test handling of unicode characters."""
    header = b"Department Name,Date,Number of Sales\n"
    processor.process_chunk(header)
    # Test with unicode department names
    processor.process_chunk("Electrónicos,2023-08-01,100\n".encode("utf-8"))
    processor.process_chunk("Vêtements,2023-08-01,200\n".encode("utf-8"))

    assert processor.department_sales["Electrónicos"] == 100
    assert processor.department_sales["Vêtements"] == 200
    assert processor.rows_processed == 2


if __name__ == "__main__":
    # Run tests manually if needed
    pytest.main([__file__])

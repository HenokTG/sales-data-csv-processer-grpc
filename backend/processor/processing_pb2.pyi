from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CsvChunk(_message.Message):
    __slots__ = ("data", "file_size_bytes")
    DATA_FIELD_NUMBER: _ClassVar[int]
    FILE_SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    data: bytes
    file_size_bytes: int
    def __init__(self, data: _Optional[bytes] = ..., file_size_bytes: _Optional[int] = ...) -> None: ...

class ProgressUpdate(_message.Message):
    __slots__ = ("status_update", "summary")
    STATUS_UPDATE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    status_update: ProcessingStatus
    summary: ProcessSummary
    def __init__(self, status_update: _Optional[_Union[ProcessingStatus, _Mapping]] = ..., summary: _Optional[_Union[ProcessSummary, _Mapping]] = ...) -> None: ...

class ProcessingStatus(_message.Message):
    __slots__ = ("rows_processed", "malformed_rows", "processed_percentage", "message")
    ROWS_PROCESSED_FIELD_NUMBER: _ClassVar[int]
    MALFORMED_ROWS_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_PERCENTAGE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    rows_processed: int
    malformed_rows: int
    processed_percentage: float
    message: str
    def __init__(self, rows_processed: _Optional[int] = ..., malformed_rows: _Optional[int] = ..., processed_percentage: _Optional[float] = ..., message: _Optional[str] = ...) -> None: ...

class ProcessSummary(_message.Message):
    __slots__ = ("result_file_name", "rows_processed", "malformed_rows", "processed_percentage", "total_sales", "unique_departments", "processing_time_seconds", "storage_result_file_url")
    RESULT_FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROWS_PROCESSED_FIELD_NUMBER: _ClassVar[int]
    MALFORMED_ROWS_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_PERCENTAGE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SALES_FIELD_NUMBER: _ClassVar[int]
    UNIQUE_DEPARTMENTS_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    STORAGE_RESULT_FILE_URL_FIELD_NUMBER: _ClassVar[int]
    result_file_name: str
    rows_processed: int
    malformed_rows: int
    processed_percentage: float
    total_sales: int
    unique_departments: int
    processing_time_seconds: float
    storage_result_file_url: str
    def __init__(self, result_file_name: _Optional[str] = ..., rows_processed: _Optional[int] = ..., malformed_rows: _Optional[int] = ..., processed_percentage: _Optional[float] = ..., total_sales: _Optional[int] = ..., unique_departments: _Optional[int] = ..., processing_time_seconds: _Optional[float] = ..., storage_result_file_url: _Optional[str] = ...) -> None: ...

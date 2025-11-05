# gRPC Streaming CSV Sales Processor

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![React (Vite)](https://img.shields.io/badge/React-Vite-blue)](https://vitejs.dev/)
[![gRPC](https://img.shields.io/badge/gRPC-Streaming-brightgreen)](https://grpc.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-blue)](https://fastapi.tiangolo.com/)
[![Go](https://img.shields.io/badge/Go-Generator-cyan)](https://golang.org/)

This project demonstrates a high-performance, memory-efficient backend system for processing massive CSV files (tested up to 6GB+). It uses a Python gRPC service for the core processing, a FastAPI gateway to handle web traffic, and a React frontend for user interaction.

The system is designed to aggregate total sales per department from a large CSV file without ever loading the entire file into memory.

<p align="center">
  <a href="https://github.com/HenokTG/sales-data-csv-processer-grpc/archive/refs/heads/main.zip" style="text-decoration:none;">
    <img src="https://img.shields.io/badge/Download-Project_ZIP-green?style=for-the-badge&logo=github" alt="Download Project ZIP" />
  </a>
</p>

---

## Architecture

This project uses a decoupled, three-service architecture to ensure scalability and separation of concerns:



1.  **gRPC Processor (`backend/processor`)**
    * The Python "worker" service.
    * Exposes a bi-directional gRPC stream (`ProcessCsv`).
    * Receives file chunks, processes them in real-time, and streams status updates (rows processed) back to the gateway.
    * Performs the aggregation logic with minimal memory.

2.  **FastAPI Gateway (`backend/gateway`)**
    * The "bridge" between the web and the gRPC service.
    * Accepts a standard HTTP file upload from the React frontend.
    * Manages processing "jobs" in memory.
    * In a background task, it streams the uploaded file chunk-by-chunk to the gRPC Processor.
    * Provides RESTful endpoints for the frontend to poll job status (`/status/{job_id}`) and download results (`/download/{filename}`).

3.  **React Frontend (`frontend`)**
    * A simple UI built with Vite + React + TypeScript.
    * Allows a user to upload a CSV file.
    * Communicates *only* with the FastAPI Gateway (it has no knowledge of gRPC).
    * Polls the `/status` endpoint to show real-time processing progress (based on bytes processed) and provides a download link when complete.

4.  **Go CSV Generator (`generator`)**
    * A utility script written in Go to efficiently generate massive (1M+, 10M+) CSV files for testing.

---

## Algorithm & Memory-Efficiency Strategy

The core challenge is processing a multi-gigabyte file without loading it into memory. This system achieves this through a 3-step streaming pipeline.

### Memory-Efficiency
The system's memory footprint is **O(D)**, where **D** is the number of *unique departments*.

This means a 10GB file with 1 billion rows (`N=1B`) but only 100 unique departments (`D=100`) will consume almost no memory, as it only needs to store a hash map with 100 keys (e.g., `{"Electronics": 120500, "Clothing": 98000, ...}`).

The file itself is never loaded, only read chunk-by-chunk.

### Algorithm
1.  **HTTP Upload:** The React app uploads the file to the FastAPI Gateway. FastAPI efficiently spools this upload to a temporary file on disk, keeping the gateway's memory usage low.
2.  **Job Creation:** The gateway creates a unique `job_id` and adds the job to its in-memory `jobs_db`. It then returns the `job_id` to the React app immediately.
3.  **gRPC Stream (Client-to-Server):** In a background task, the gateway opens the temporary file and reads it in 1MB chunks. It streams these chunks to the gRPC Processor's `ProcessCsv` endpoint.
4.  **Real-time Aggregation:** The gRPC server receives each chunk and appends it to a `_buffer`. It processes the buffer line-by-line:
    * It maintains a single `defaultdict(int)` (a hash map) to store `department_name -> total_sales`.
    * For each valid line, it updates the map: `sales_map[dept] += sales_amount`.
    * Any partial line left at the end of a chunk is kept in the `_buffer` to be prepended to the next chunk.
5.  **gRPC Stream (Server-to-Client):** While processing, the gRPC server periodically sends `ProgressUpdate` messages (containing current rows processed and bytes processed) back to the gateway.
6.  **Status Polling:** The React app, which has been polling `/status/{job_id}`, receives these progress updates from the gateway and displays them on the UI.
7.  **Finalization:** When the client stream ends, the gRPC server finalizes the aggregation, writes the `sales_map` to a new result CSV, and sends a final `ProcessSummary` message.
8.  **Download:** The gateway updates the job status to "complete". The React app displays a download link pointing to the gateway's `/download/{filename}` endpoint.

---

## Big O Complexity

* **Time Complexity: `O(N)`**
    * Where `N` is the total number of rows in the input CSV. The system must read every row at least once. Parsing and hash map updates are (on average) `O(1)` operations. The final sorting of departments is `O(D log D)`, which is negligible compared to `O(N)`.

* **Space Complexity: `O(D)`**
    * Where `D` is the number of **unique departments**. This is the key benefit. The memory usage does *not* depend on the file size or total number of rows, only on the number of departments to be aggregated.

---

## How to Run the Application

### Prerequisites
* [Python 3.9+](https://www.python.org/)
* [Node.js 18+](https://nodejs.org/)
* [Go 1.18+](https://go.dev/)
* Git

### 1. Clone the Repository
```bash
git clone [https://github.com/HenokTG/sales-data-csv-processer-grpc.git](https://github.com/HenokTG/sales-data-csv-processer-grpc.git)
cd sales-data-csv-processer-grpc
```

### 2. Generate test csv
```bash
# Navigate to the generator directory
cd go-csv-generator

# Run the Go script (generates csv in its root folder)
# You can custimzise the number of diparment and record to generate in config.json file then run the script with again with
go run main.go
```

### 2. Run the Backend (Python) services
```bash
# Navigate to the backend directory
cd backend

# Create and activate a virtual environment
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# IMPORTANT: Generate the gRPC Python code [this is not necesssary since the generated files are already in the repo... but if you update the protos file (`protos/processinf.proto`)** for them reason you need to run it
python -m grpc_tools.protoc -I=protos --python_out=backend/processor/ --pyi_out=backend/processor/ --grpc_python_out=backend/processor/ protos/processing.proto

# (From the 'backend' directory with venv active) start the services
# Terminal 1: gRPC service
python -m processor.server
# Output: INFO:__main__:gRPC Server started on port 50051...

# Terminal 2: FastAPI gatwway service
uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
# Output: INFO: Uvicorn running on [http://127.0.0.1:8000](http://127.0.0.1:8000)
```

### 3. Run the Frontend (React/Vite - TS) service
```bash
# (From the 'root' directory) Navigate to the frontend directory
cd frontend

# Install Node.js dependencies
npm install

# Run the Vite development server
npm run dev
# Output: Local: http://localhost:5173/
```
### . How to Test [Unit Tests (gRPC service)] - This project includes unit tests for the core StreamProcessor logic.
1. Navigate to the backend directory.
2. Ensure your virtual environment is active.
```bash
pip install pytest # this is in the requirment but it is important this packege in the enviroment for the test
# (From the 'backend' directory with venv active) run the test
python -m pytest test/ -v
# You should see
====================================================================================== test session starts ======================================================================================
platform win32 -- Python 3.10.3, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\SAMSUNG\Desktop\MyProjects\Mereb-gRPC-test\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\SAMSUNG\Desktop\MyProjects\Mereb-gRPC-test\backend
plugins: anyio-4.11.0
collected 7 items                                                                                                                                                                                

test/test_processor.py::test_init PASSED                                                                                                                                                   [ 14%]
test/test_processor.py::test_simple_aggregation PASSED                                                                                                                                     [ 28%]
test/test_processor.py::test_chunk_splitting PASSED                                                                                                                                        [ 42%]
test/test_processor.py::test_malformed_rows PASSED                                                                                                                                         [ 57%]
test/test_processor.py::test_finalize_output_file PASSED                                                                                                                                   [ 71%]
test/test_processor.py::test_no_data_rows PASSED                                                                                                                                           [ 85%]
test/test_processor.py::test_unicode_handling PASSED  
```

### 5. Use the App
Open your browser and go to http://localhost:5173. Upload the departments_1M_sales.csv file (or any other CSV) and watch the real-time processing.

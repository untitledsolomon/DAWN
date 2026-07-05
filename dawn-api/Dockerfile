FROM python:3.11-slim

WORKDIR /app

# System deps — includes tesseract-ocr for PDF OCR fallback
# Note: libgl1-mesa-glx was removed in Debian Trixie, use libgl1 instead
# libglib2.0-0 was renamed to libglib2.0-0t64 in Trixie
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0t64 \
    nmap \
    arp-scan \
    && rm -rf /var/lib/apt/lists/*

# Install llama-cpp-python with CPU-only build (no CUDA needed)
ENV CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS"
RUN pip install --no-cache-dir llama-cpp-python==0.2.78

# Install rest of requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Models directory (mount your .gguf file here)
RUN mkdir -p /models

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

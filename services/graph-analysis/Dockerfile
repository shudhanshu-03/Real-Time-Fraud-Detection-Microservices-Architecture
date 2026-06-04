FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ./services/graph-analysis/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared library first to install it
COPY ./shared /shared
RUN cd /shared && pip install -e .

COPY ./services/graph-analysis/app ./app

CMD ["python", "-m", "app.main"]

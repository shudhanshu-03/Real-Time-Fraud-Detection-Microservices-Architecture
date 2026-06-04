FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/rule-engine/pyproject.toml .
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --no-root --no-interaction --no-ansi

# Copy proto definitions from the root
COPY proto/ /app/proto/

# Copy the service code
COPY services/rule-engine/ /app/

# Generate gRPC Python code
RUN python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/rule_engine.proto /app/proto/google/protobuf/timestamp.proto || \
    python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/rule_engine.proto

EXPOSE 8003 50051

CMD ["python", "main.py"]

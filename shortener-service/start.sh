#!/bin/sh
set -e

echo "Generating gRPC stubs..."
python -m grpc_tools.protoc \
  -I ./proto \
  --python_out=. \
  --grpc_python_out=. \
  ./proto/analytics.proto

echo "Starting shortener-service..."
exec uvicorn main:app --host 0.0.0.0 --port 8000

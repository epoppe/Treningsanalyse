#!/bin/bash

# Start backend server
echo "Starter backend server på port 8002..."
cd /workspace/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8002 &
BACKEND_PID=$!

# Start frontend server
echo "Starter frontend server på port 3001..."
cd /workspace/frontend
PORT=3001 npm run dev &
FRONTEND_PID=$!

echo "Backend server PID: $BACKEND_PID"
echo "Frontend server PID: $FRONTEND_PID"
echo "Backend: http://localhost:8002"
echo "Frontend: http://localhost:3001"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
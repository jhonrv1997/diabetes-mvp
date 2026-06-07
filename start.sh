#!/bin/bash
# Diabetes MVP - Start Script
# Starts backend API and frontend dev server

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "  Diabetes MVP - Detección Temprana"
echo "  Starting development environment..."
echo "========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3.11+ is required"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js 20+ is required"
    exit 1
fi

# --- Backend Setup ---
echo "[1/4] Setting up backend..."
cd "$PROJECT_DIR/backend"

if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "  Installing Python dependencies..."
pip install -q -r requirements.txt

# Initialize database if not exists
if [ ! -f "diabetes_mvp.db" ]; then
    echo "  Initializing database with sample data..."
    python init_db.py
fi

echo "  Starting FastAPI backend on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# --- Frontend Setup ---
echo ""
echo "[2/4] Setting up frontend..."
cd "$PROJECT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo "  Installing Node.js dependencies..."
    npm install
fi

echo "  Starting Vite dev server on port 5173..."
npm run dev &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# --- BLE Simulator (optional) ---
echo ""
echo "[3/4] BLE Simulator (optional - press 's' to start, any other key to skip)"
read -t 5 -n 1 -s BLE_CHOICE
if [ "$BLE_CHOICE" = "s" ]; then
    cd "$PROJECT_DIR/backend"
    source venv/bin/activate
    echo "  Starting BLE simulator..."
    python -m ble_service.simulator &
    SIMULATOR_PID=$!
    echo "  Simulator PID: $SIMULATOR_PID"
fi

echo ""
echo "[4/4] All services started!"
echo ""
echo "========================================="
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "========================================="
echo ""
echo "Default credentials:"
echo "  Admin:     admin / admin123"
echo "  Enfermera: enfermera / enfermera123"
echo ""
echo "Press Ctrl+C to stop all services"

# Trap exit
trap "echo 'Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Wait
wait
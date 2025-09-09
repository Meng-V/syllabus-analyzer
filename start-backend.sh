#!/bin/bash

# Syllabus Analyzer Backend Startup Script

echo "🚀 Starting Syllabus Analyzer Backend..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Navigate to backend directory
cd "$(dirname "$0")/backend"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Please create one based on env.example"
    echo "   You'll need to add your OpenAI API key and optionally Primo API configuration."
    echo "   Copy env.example to .env and fill in your API keys."
    read -p "   Press Enter to continue anyway or Ctrl+C to exit..."
fi

# Start the FastAPI server
echo "🌟 Starting FastAPI server on http://localhost:8000"
echo "📖 API documentation available at http://localhost:8000/docs"
echo "🛑 Press Ctrl+C to stop the server"
echo ""

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

#!/bin/bash

# Syllabus Analyzer Frontend Startup Script

echo "🚀 Starting Syllabus Analyzer Frontend..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is required but not installed."
    echo "   Please install Node.js from https://nodejs.org/"
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is required but not installed."
    exit 1
fi

# Navigate to project root
cd "$(dirname "$0")"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing Node.js dependencies..."
    npm install
fi

# Set environment variable for API URL
export NEXT_PUBLIC_API_URL="http://localhost:8000"

# Start the Next.js development server
echo "🌟 Starting Next.js development server on http://localhost:3000"
echo "🔗 Make sure the backend is running on http://localhost:8000"
echo "🛑 Press Ctrl+C to stop the server"
echo ""

npm run dev

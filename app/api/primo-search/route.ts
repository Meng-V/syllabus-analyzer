import { type NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.BACKEND_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { jobId } = body
    
    if (!jobId) {
      return NextResponse.json({ error: "Job ID is required" }, { status: 400 })
    }
    
    // Forward request to Python backend
    const response = await fetch(`${API_BASE_URL}/api/check-primo/${jobId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })

    const data = await response.json()
    
    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error("Primo search API error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

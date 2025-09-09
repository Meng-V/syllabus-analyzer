import { type NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.BACKEND_URL || "http://localhost:8000"

export async function GET(request: NextRequest) {
  try {
    // Forward request to Python backend
    const response = await fetch(`${API_BASE_URL}/api/metadata-fields`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    })

    const data = await response.json()
    
    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error("Metadata fields API error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

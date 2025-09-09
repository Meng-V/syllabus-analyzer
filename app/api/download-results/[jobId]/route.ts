import { type NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.BACKEND_URL || "http://localhost:8000"

export async function GET(request: NextRequest, { params }: { params: { jobId: string } }) {
  try {
    const { jobId } = params

    // Forward request to Python backend
    const response = await fetch(`${API_BASE_URL}/api/download-results/${jobId}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    })

    if (!response.ok) {
      const data = await response.json()
      return NextResponse.json(data, { status: response.status })
    }

    // For file downloads, we need to handle the blob response
    const blob = await response.blob()
    const headers = new Headers()
    headers.set('Content-Type', response.headers.get('Content-Type') || 'application/json')
    headers.set('Content-Disposition', response.headers.get('Content-Disposition') || 'attachment')

    return new NextResponse(blob, {
      status: 200,
      headers,
    })
  } catch (error) {
    console.error("Download results API error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

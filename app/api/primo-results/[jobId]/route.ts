import { type NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.BACKEND_URL || "http://localhost:8000"

export async function GET(request: NextRequest, { params }: { params: { jobId: string } }) {
  try {
    const { jobId } = params

    // Check for Primo results from backend
    const response = await fetch(`${API_BASE_URL}/api/results/${jobId}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    })

    const data = await response.json()
    
    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    // Transform backend results to match frontend expectations
    const transformedResults = {
      jobId,
      status: "completed",
      searchResults: [] as any[],
      summary: {
        totalSearched: 0,
        itemsFound: 0,
        itemsNotFound: 0,
        availableItems: 0,
        checkedOutItems: 0,
        digitalResources: 0,
      },
    }

    if (data.results) {
      // Process each result to extract library matches
      data.results.forEach((result: any) => {
        if (result.library_matches && Array.isArray(result.library_matches)) {
          result.library_matches.forEach((match: any) => {
            transformedResults.searchResults.push({
              originalQuery: match.originalQuery || "Unknown",
              matches: match.matches || [],
              matchScore: match.matchScore || 0,
              note: match.note
            })
          })
        }
      })
    }

    return NextResponse.json(transformedResults)
  } catch (error) {
    console.error("Primo results error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

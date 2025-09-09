"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ExternalLink, Book, Monitor, Calendar } from "lucide-react"
import type { LibraryResource } from "@/lib/primo-integration"

interface LibraryResourceCardProps {
  resource: LibraryResource
}

export function LibraryResourceCard({ resource }: LibraryResourceCardProps) {
  const getAvailabilityColor = (availability: string) => {
    switch (availability) {
      case "available":
        return "bg-green-100 text-green-800 border-green-200"
      case "checked_out":
        return "bg-yellow-100 text-yellow-800 border-yellow-200"
      case "unavailable":
        return "bg-red-100 text-red-800 border-red-200"
      default:
        return "bg-gray-100 text-gray-800 border-gray-200"
    }
  }

  const getFormatIcon = (format: string) => {
    if (format.toLowerCase().includes("ebook") || format.toLowerCase().includes("online")) {
      return <Monitor className="w-4 h-4" />
    }
    return <Book className="w-4 h-4" />
  }

  return (
    <Card className="h-full hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex gap-3">
          {resource.coverImage && (
            <img
              src={resource.coverImage || "/placeholder.svg"}
              alt={`Cover of ${resource.title}`}
              className="w-16 h-20 object-cover rounded border"
            />
          )}
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm font-medium leading-tight text-balance">{resource.title}</CardTitle>
            {resource.authors.length > 0 && (
              <p className="text-xs text-muted-foreground mt-1">by {resource.authors.join(", ")}</p>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0 space-y-3">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className={getAvailabilityColor(resource.availability)}>
            {resource.availability === "available"
              ? "Available"
              : resource.availability === "checked_out"
                ? "Checked Out"
                : "Unavailable"}
          </Badge>

          <Badge variant="secondary" className="flex items-center gap-1">
            {getFormatIcon(resource.format)}
            <span className="text-xs">{resource.format}</span>
          </Badge>
        </div>

        <div className="space-y-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <span className="font-medium">Location:</span>
            <span>{resource.location}</span>
          </div>

          {resource.callNumber && (
            <div className="flex items-center gap-1">
              <span className="font-medium">Call Number:</span>
              <span className="font-mono">{resource.callNumber}</span>
            </div>
          )}

          {resource.dueDate && (
            <div className="flex items-center gap-1 text-yellow-600">
              <Calendar className="w-3 h-3" />
              <span>Due: {new Date(resource.dueDate).toLocaleDateString()}</span>
            </div>
          )}
        </div>

        <Button
          variant="outline"
          size="sm"
          className="w-full bg-transparent"
          onClick={() => window.open(resource.link, "_blank")}
        >
          <ExternalLink className="w-3 h-3 mr-1" />
          View in Catalog
        </Button>
      </CardContent>
    </Card>
  )
}

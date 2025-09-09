"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { LibraryResourceCard } from "@/components/library-resource-card"
import { Upload, Download, FileText, CheckCircle, AlertCircle, Book, Loader2, Star, BookOpen, Brain, Database, BarChart3 } from "lucide-react"

interface ExtractedMetadata {
  filename: string
  metadata: {
    year?: string
    semester?: string
    class_name?: string
    class_number?: string
    instructor?: string
    university?: string
    main_topic?: string
    reading_materials?: any[]
  }
}

interface JobStatus {
  job_id: string
  status: string
  progress: number
  message: string
  files_found?: number
  files_downloaded?: number
  files_processed?: number
  selected_fields?: string[]
  results_file?: string
  primo_results_file?: string
}

interface MetadataField {
  id: string
  label: string
  description: string
}

interface LibraryMatch {
  originalQuery: string
  matches: Array<{
    title: string
    authors: string[]
    isbn: string
    availability: "available" | "checked_out" | "unavailable"
    format: string
    location: string
    callNumber: string
    link: string
    coverImage?: string
    dueDate?: string
  }>
  matchScore: number
  note?: string
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function SyllabusAnalyzer() {
  const [syllabusUrl, setSyllabusUrl] = useState<string>("")
  const [jobName, setJobName] = useState<string>("")
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentStep, setCurrentStep] = useState<"upload" | "download" | "metadata" | "extract" | "results">("upload")
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [availableFields, setAvailableFields] = useState<MetadataField[]>([])
  const [extractedResults, setExtractedResults] = useState<ExtractedMetadata[]>([])
  const [libraryMatches, setLibraryMatches] = useState<LibraryMatch[]>([])
  const [currentJob, setCurrentJob] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [jobs, setJobs] = useState<JobStatus[]>([])
  const [libraryMatchingStatus, setLibraryMatchingStatus] = useState<{
    isProcessing: boolean
    progress: number
    message: string
    error: string | null
  }>({ isProcessing: false, progress: 0, message: "", error: null })

  // Load available metadata fields on component mount
  useEffect(() => {
    fetchAvailableFields()
    loadJobs()
  }, [])

  // Poll job status when processing
  useEffect(() => {
    if (currentJob && ["pending", "downloading", "processing"].includes(currentJob.status)) {
      const interval = setInterval(() => {
        pollJobStatus(currentJob.job_id)
      }, 2000) // Poll every 2 seconds for better performance
      return () => clearInterval(interval)
    }
  }, [currentJob])

  // Poll for library matching progress when in results step
  useEffect(() => {
    if (currentStep === "results" && currentJob && libraryMatches.length === 0 && selectedFields.includes("reading_materials")) {
      const interval = setInterval(() => {
        checkLibraryMatchingProgress(currentJob.job_id)
      }, 3000) // Poll every 3 seconds for library matching
      return () => clearInterval(interval)
    }
  }, [currentStep, currentJob, libraryMatches.length, selectedFields])

  const fetchAvailableFields = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/metadata-fields`)
      const data = await response.json()
      setAvailableFields(data.fields)
    } catch (err) {
      console.error("Failed to fetch metadata fields:", err)
    }
  }

  const loadJobs = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/jobs`)
      const data = await response.json()
      setJobs(data.jobs)
    } catch (err) {
      console.error("Failed to load jobs:", err)
    }
  }

  const pollJobStatus = async (jobId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/job-status/${jobId}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch job status: ${response.status}`)
      }
      
      const jobStatus = await response.json()
      setCurrentJob(jobStatus)
      
      if (jobStatus.status === "completed" && currentStep === "download") {
        setIsProcessing(false)
        // Don't auto-transition - let user click continue button
      } else if (jobStatus.status === "completed" && currentStep === "extract") {
        await loadResults(jobId)
        setCurrentStep("results")
        setIsProcessing(false)
      } else if (jobStatus.status === "completed" && currentStep === "results") {
        // Reload results to get updated library matches after Primo check
        await loadResults(jobId)
        // Update library matching status if it was processing
        if (libraryMatchingStatus.isProcessing) {
          setLibraryMatchingStatus({
            isProcessing: false,
            progress: 100,
            message: "Library resource matching completed!",
            error: null
          })
        }
      } else if (jobStatus.status === "error" || jobStatus.status === "failed") {
        setError(jobStatus.message || "Job failed with unknown error")
        setIsProcessing(false)
      }
    } catch (err) {
      console.error("Failed to poll job status:", err)
      setError("Failed to check job status. Please refresh and try again.")
      setIsProcessing(false)
    }
  }

  const startProcessing = async () => {
    if (!syllabusUrl.trim()) {
      setError("Please provide a valid URL")
      return
    }

    setIsProcessing(true)
    setCurrentStep("download")
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/api/discover-syllabi`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: syllabusUrl,
          job_name: jobName || undefined
        }),
      })

      const data = await response.json()
      
      if (response.ok) {
        // Start polling for job status
        const jobStatus = await fetch(`${API_BASE_URL}/api/job-status/${data.job_id}`)
        const job = await jobStatus.json()
        setCurrentJob(job)
      } else {
        throw new Error(data.detail || "Failed to start processing")
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start processing")
      setIsProcessing(false)
    }
  }

  const toggleFieldSelection = (fieldId: string) => {
    setSelectedFields(prev => 
      prev.includes(fieldId) 
        ? prev.filter(id => id !== fieldId)
        : [...prev, fieldId]
    )
  }

  const selectAllFields = () => {
    setSelectedFields(availableFields.map(field => field.id))
  }

  const deselectAllFields = () => {
    setSelectedFields([])
  }

  const startExtraction = async () => {
    console.log("Starting extraction with:", { currentJob, selectedFields })
    
    if (!currentJob || selectedFields.length === 0) {
      setError("Please select metadata fields to extract")
      return
    }

    // Check if Reading Materials is selected (required field)
    if (!selectedFields.includes("reading_materials")) {
      setError("Reading Materials is required. Please select it to continue.")
      return
    }

    if (!currentJob.job_id) {
      setError("No valid job found. Please restart the process.")
      return
    }

    // Clear any existing errors
    setError(null)

    try {
      console.log("Sending extraction request to:", `${API_BASE_URL}/api/extract-metadata`)
      
      // Add timeout to prevent hanging
      const controller = new AbortController()
      const timeoutId = setTimeout(() => {
        controller.abort()
        console.log("Request timed out after 120 seconds")
      }, 120000) // 120 second timeout
      
      const response = await fetch(`${API_BASE_URL}/api/extract-metadata`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          job_id: currentJob.job_id,
          selected_fields: selectedFields
        }),
        signal: controller.signal
      })

      clearTimeout(timeoutId)
      console.log("Extraction response status:", response.status)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error("Extraction error response:", errorText)
        let errorMessage = "Failed to start extraction"
        try {
          const errorJson = JSON.parse(errorText)
          errorMessage = errorJson.detail || errorMessage
        } catch {
          errorMessage = `Server error (${response.status}): ${errorText}`
        }
        throw new Error(errorMessage)
      }

      const result = await response.json()
      console.log("Extraction started successfully:", result)
      
      // Immediately transition to extract step
      setCurrentStep("extract")
      
      // Update current job with processing status
      setCurrentJob(prev => prev ? { ...prev, status: "processing", progress: 0, message: "Starting extraction..." } : null)
      
    } catch (err) {
      console.error("Extraction failed:", err)
      
      if (err instanceof Error && err.name === 'AbortError') {
        setError("Request timed out. Please check your connection and try again.")
      } else {
        setError(err instanceof Error ? err.message : "Failed to start extraction")
      }
    }
  }

  const loadResults = async (jobId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/results/${jobId}`)
      const data = await response.json()
      setExtractedResults(data.results)
      
      // Process library matches from the results
      const matches: LibraryMatch[] = []
      if (data.results) {
        data.results.forEach((result: any) => {
          if (result.library_matches && Array.isArray(result.library_matches)) {
            matches.push(...result.library_matches)
          }
        })
      }
      setLibraryMatches(matches)
      
      // Start Primo check if reading materials are selected and no library matches yet
      if (selectedFields.includes("reading_materials") && matches.length === 0) {
        setLibraryMatchingStatus({
          isProcessing: true,
          progress: 0,
          message: "Starting library resource matching...",
          error: null
        })
        await startPrimoCheck(jobId)
      }
    } catch (err) {
      console.error("Failed to load results:", err)
      setError("Failed to load results. Please try again.")
    }
  }

  const startPrimoCheck = async (jobId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/check-primo/${jobId}`, {
        method: "POST"
      })
      
      if (!response.ok) {
        throw new Error(`Failed to start library matching: ${response.status}`)
      }
      
      // Results will be updated via polling
    } catch (err) {
      console.error("Failed to start Primo check:", err)
      setLibraryMatchingStatus({
        isProcessing: false,
        progress: 0,
        message: "",
        error: "Failed to start library resource matching. Please check your connection and try again."
      })
    }
  }

  const checkLibraryMatchingProgress = async (jobId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/job-status/${jobId}`)
      if (!response.ok) {
        throw new Error(`Failed to check status: ${response.status}`)
      }
      
      const jobStatus = await response.json()
      
      // Check if this is a library matching operation in progress
      if (jobStatus.status === "processing" && jobStatus.message && 
          (jobStatus.message.includes("Checking resources") || 
           jobStatus.message.includes("library resources") ||
           jobStatus.message.includes("Primo API"))) {
        setLibraryMatchingStatus({
          isProcessing: true,
          progress: jobStatus.progress || 0,
          message: jobStatus.message,
          error: null
        })
      } else if (jobStatus.status === "completed") {
        // Check if we now have library matches
        await loadResults(jobId)
      } else if (jobStatus.status === "error" || jobStatus.status === "failed") {
        setLibraryMatchingStatus({
          isProcessing: false,
          progress: 0,
          message: "",
          error: jobStatus.message || "Library resource matching failed"
        })
      }
    } catch (err) {
      console.error("Failed to check library matching progress:", err)
      setLibraryMatchingStatus(prev => ({
        ...prev,
        error: "Unable to check progress. Please refresh the page."
      }))
    }
  }

  const downloadResults = async () => {
    if (!currentJob) return
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/download-results/${currentJob.job_id}`)
      if (response.ok) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `syllabus_analysis_${currentJob.job_id}.json`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      }
    } catch (err) {
      console.error("Failed to download results:", err)
    }
  }

  const resetAnalysis = () => {
    setCurrentStep("upload")
    setExtractedResults([])
    setLibraryMatches([])
    setSelectedFields([])
    setSyllabusUrl("")
    setJobName("")
    setCurrentJob(null)
    setError(null)
    setIsProcessing(false)
    setLibraryMatchingStatus({ isProcessing: false, progress: 0, message: "", error: null })
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 bg-accent rounded-lg">
              <Brain className="w-6 h-6 text-accent-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Syllabus Analyzer</h1>
              <p className="text-muted-foreground">AI-powered metadata extraction and library resource matching</p>
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        {/* Progress Steps */}
        <div className="mb-8">
          <div className="flex items-center justify-between max-w-2xl mx-auto">
            {[
              { key: "upload", label: "Upload", icon: Upload },
              { key: "download", label: "Download", icon: FileText },
              { key: "metadata", label: "Metadata", icon: Brain },
              { key: "extract", label: "Extract", icon: Database },
              { key: "results", label: "Results", icon: CheckCircle },
            ].map((step, index) => {
              const Icon = step.icon
              const isActive = currentStep === step.key
              const isCompleted = ["upload", "download", "metadata", "extract", "results"].indexOf(currentStep) > index

              return (
                <div key={step.key} className="flex flex-col items-center">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center border-2 ${
                      isActive
                        ? "bg-accent border-accent text-accent-foreground"
                        : isCompleted
                          ? "bg-accent border-accent text-accent-foreground"
                          : "bg-muted border-border text-muted-foreground"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>
                  <span
                    className={`text-sm mt-2 ${isActive ? "text-foreground font-medium" : "text-muted-foreground"}`}
                  >
                    {step.label}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert className="max-w-2xl mx-auto mb-6" variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Upload Section */}
        {currentStep === "upload" && (
          <Card className="max-w-2xl mx-auto">
            <CardHeader>
              <CardTitle className="text-balance">Discover Syllabus PDFs</CardTitle>
              <CardDescription>
                Provide a URL that contains links to syllabus PDFs. Our system will discover and download all PDFs from that page.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="job-name">Job Name (Optional)</Label>
                <Input
                  id="job-name"
                  type="text"
                  placeholder="My Syllabus Analysis"
                  value={jobName}
                  onChange={(e) => setJobName(e.target.value)}
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="syllabus-url">Syllabus Directory URL</Label>
                <Input
                  id="syllabus-url"
                  type="url"
                  placeholder="https://arts.ufl.edu/syllabi/"
                  value={syllabusUrl}
                  onChange={(e) => setSyllabusUrl(e.target.value)}
                />
              </div>

              <Button
                onClick={startProcessing}
                disabled={!syllabusUrl.trim() || isProcessing}
                className="w-full"
              >
                {isProcessing ? "Starting..." : "Discover & Download PDFs"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Download Progress Section */}
        {currentStep === "download" && (
          <Card className="max-w-2xl mx-auto">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5" />
                Discovering & Downloading Syllabi
                {currentJob?.status === "completed" && (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                )}
              </CardTitle>
              <CardDescription>
                {currentJob?.status === "completed" 
                  ? "Download completed successfully! Preparing metadata selection..."
                  : "Scanning for PDF files and downloading them..."
                }
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {currentJob && (
                <>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Progress</span>
                      <span>{currentJob.progress}%</span>
                    </div>
                    <Progress 
                      value={currentJob.progress} 
                      className={`w-full transition-all duration-300 ${
                        currentJob.status === "completed" ? "bg-green-100" : ""
                      }`} 
                    />
                  </div>

                  <div className={`text-sm ${
                    currentJob.status === "completed" 
                      ? "text-green-700 font-medium" 
                      : "text-muted-foreground"
                  }`}>
                    {currentJob.message}
                  </div>

                  {currentJob.files_found !== undefined && (
                    <div className="grid grid-cols-2 gap-4 text-sm p-4 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          Found
                        </Badge>
                        <span className="font-medium">{currentJob.files_found} files</span>
                      </div>
                      {currentJob.files_downloaded !== undefined && (
                        <div className="flex items-center gap-2">
                          <Badge 
                            variant={currentJob.status === "completed" ? "default" : "secondary"}
                            className="text-xs"
                          >
                            Downloaded
                          </Badge>
                          <span className="font-medium">{currentJob.files_downloaded} files</span>
                        </div>
                      )}
                    </div>
                  )}

                  {currentJob.status === "completed" && (
                    <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg flex flex-col gap-4">
                      <div className="flex items-center gap-2 text-green-800 mb-3">
                        <CheckCircle className="w-4 h-4" />
                        <span className="font-medium">Download Complete!</span>
                      </div>
                      <p className="text-sm text-green-700 mb-4">
                        Successfully downloaded {currentJob.files_downloaded} PDF files. Ready to select metadata fields for extraction.
                      </p>
                      <Button 
                        onClick={() => setCurrentStep("metadata")}
                        className="w-full"
                        size="sm"
                      >
                        Continue to Metadata Selection
                      </Button>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* Metadata Selection Section */}
        {currentStep === "metadata" && (
          <Card className="max-w-4xl mx-auto">
            <CardHeader>
              <CardTitle>Select Metadata to Extract</CardTitle>
              <CardDescription>
                Choose which metadata fields you want our AI to extract from your syllabi.
                {currentJob && currentJob.files_downloaded && (
                  <span className="block mt-1 font-medium">Ready to process {currentJob.files_downloaded} PDF files</span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Select All / Deselect All Controls */}
              <div className="flex justify-between items-center mb-6 p-4 bg-muted/30 rounded-lg border">
                <div className="text-sm font-medium">
                  {selectedFields.length} of {availableFields.length} fields selected
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={selectAllFields}
                    disabled={selectedFields.length === availableFields.length}
                  >
                    Select All
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={deselectAllFields}
                    disabled={selectedFields.length === 0}
                  >
                    Deselect All
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {availableFields.map((field) => {
                  const isSelected = selectedFields.includes(field.id)
                  return (
                    <Card
                      key={field.id}
                      className={`cursor-pointer transition-colors border-2 ${
                        isSelected ? "bg-accent/10 border-accent" : "hover:bg-accent/5 hover:border-accent"
                      }`}
                      onClick={() => toggleFieldSelection(field.id)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="space-y-1">
                            <h4 className="font-medium text-sm">{field.label}</h4>
                            <p className="text-xs text-muted-foreground">{field.description}</p>
                          </div>
                          <Badge variant={isSelected ? "default" : "secondary"} className="ml-2">
                            {isSelected ? "Selected" : "Select"}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>

              <div className="mt-6 space-y-4">
                {selectedFields.length === 0 && (
                  <div className="text-center text-sm text-muted-foreground">
                    Please select at least one metadata field to continue
                  </div>
                )}
                
                {selectedFields.length > 0 && !selectedFields.includes("reading_materials") && (
                  <div className="text-center text-sm text-amber-600 bg-amber-50 p-3 rounded-lg border border-amber-200">
                    ⚠️ Reading Materials is required for library resource matching
                  </div>
                )}
                
                <div className="flex justify-center">
                  <Button 
                    onClick={startExtraction} 
                    size="lg" 
                    disabled={selectedFields.length === 0 || !selectedFields.includes("reading_materials")}
                    className="min-w-[300px]"
                  >
                    {selectedFields.length > 0 && selectedFields.includes("reading_materials")
                      ? `Extract Selected Metadata (${selectedFields.length} fields)`
                      : selectedFields.length > 0
                      ? "Reading Materials Required"
                      : "Select Metadata Fields"
                    }
                  </Button>
                </div>
                
                {selectedFields.length > 0 && selectedFields.includes("reading_materials") && (
                  <div className="text-center text-sm text-green-600">
                    ✓ Ready to extract {selectedFields.length} metadata field{selectedFields.length !== 1 ? 's' : ''}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {currentStep === "extract" && (
          <Card className="max-w-2xl mx-auto">
            <CardHeader>
              <CardTitle>Extracting Metadata & Matching Resources</CardTitle>
              <CardDescription>AI is analyzing your syllabi and searching library resources...</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {currentJob && (
                <>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Extraction Progress</span>
                      <span>{currentJob.progress}%</span>
                    </div>
                    <Progress value={currentJob.progress} className="w-full" />
                  </div>

                  <div className="text-sm text-muted-foreground">
                    {currentJob.message}
                  </div>

                  {currentJob.files_processed !== undefined && (
                    <div className="text-sm">
                      <span className="font-medium">Processed:</span> {currentJob.files_processed} files
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        )}

        {currentStep === "results" && (
          <div className="space-y-8">
            {/* Results Summary */}
            <Card className="max-w-4xl mx-auto">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5" />
                  Analysis Complete
                </CardTitle>
                <CardDescription>
                  Successfully processed {extractedResults.length} syllabi and found{" "}
                  {libraryMatches.reduce((acc, match) => acc + match.matches.length, 0)} library resources
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-accent">{extractedResults.length}</div>
                    <div className="text-sm text-muted-foreground">Syllabi Processed</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-accent">{selectedFields.length}</div>
                    <div className="text-sm text-muted-foreground">Metadata Fields</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-accent">
                      {libraryMatches.reduce((acc, match) => acc + match.matches.length, 0)}
                    </div>
                    <div className="text-sm text-muted-foreground">Resources Found</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-accent">
                      {libraryMatches.reduce(
                        (acc, match) => acc + match.matches.filter((m) => m.availability === "available").length,
                        0,
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">Available Now</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Extracted Metadata Results */}
            <div className="max-w-6xl mx-auto space-y-6">
              <h2 className="text-xl font-semibold">Extracted Metadata</h2>

              {extractedResults.map((result, index) => (
                <Card key={index}>
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <FileText className="w-5 h-5" />
                      {result.filename}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {Object.entries(result.metadata).map(([key, value]) => {
                        if (key === "reading_materials" && Array.isArray(value)) {
                          return (
                            <div key={key} className="space-y-2">
                              <div className="flex items-center gap-2">
                                <span className="font-medium capitalize">
                                  {key.replace("_", " ")}
                                </span>
                              </div>
                              <ul className="list-disc list-inside space-y-2 text-sm">
                                {value.map((item, idx) => {
                                  if (typeof item === 'object' && item !== null) {
                                    const title = item.title || 'Unknown Title'
                                    const type = item.type || item.requirement || 'unknown'
                                    const creator = item.creator || item.author
                                    const isRequired = item.requirement === 'required'
                                    return (
                                      <li key={idx} className="text-muted-foreground flex items-start gap-2">
                                        {isRequired && <Star className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />}
                                        <div className="flex-1">
                                          <span className="font-medium text-foreground">{title}</span>
                                          {creator && <span className="text-xs"> by {creator}</span>}
                                          <span className="ml-2 px-2 py-0.5 bg-secondary text-secondary-foreground rounded-full text-xs capitalize">
                                            {type}
                                          </span>
                                        </div>
                                      </li>
                                    )
                                  } else {
                                    return (
                                      <li key={idx} className="text-muted-foreground">
                                        <span className="font-medium text-foreground">{String(item)}</span>
                                        <span className="ml-2 px-2 py-0.5 bg-secondary text-secondary-foreground rounded-full text-xs">
                                          book
                                        </span>
                                      </li>
                                    )
                                  }
                                })}
                              </ul>
                            </div>
                          )
                        }
                        
                        if (key === "main_topic") {
                          // Shorten main topic summary
                          const shortValue = typeof value === 'string' && value.length > 200 
                            ? value.substring(0, 200) + '...' 
                            : value
                          return (
                            <div key={key} className="space-y-2">
                              <div className="flex items-center gap-2">
                                <span className="font-medium capitalize">
                                  {key.replace("_", " ")}
                                </span>
                              </div>
                              <span className="text-sm text-muted-foreground">{String(shortValue)}</span>
                            </div>
                          )
                        }
                        
                        return (
                          <div key={key} className="space-y-2">
                            <div className="flex items-center gap-2">
                              <span className="font-medium capitalize">
                                {key.replace("_", " ")}
                              </span>
                            </div>
                            {Array.isArray(value) ? (
                              <ul className="list-disc list-inside space-y-1 text-sm">
                                {value.map((item, idx) => (
                                  <li key={idx} className="text-muted-foreground">
                                    {typeof item === 'object' ? item.title || JSON.stringify(item) : item}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-sm text-muted-foreground">{String(value)}</span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Library Resource Matches */}
            <div className="max-w-6xl mx-auto space-y-6">
              <h2 className="text-xl font-semibold">Library Resource Matches</h2>
              
              {libraryMatches.length === 0 ? (
                <Card>
                  <CardContent className="py-8">
                    {!selectedFields.includes("reading_materials") ? (
                      <div className="text-center">
                        <Book className="w-12 h-12 mx-auto mb-4 opacity-50" />
                        <p className="text-muted-foreground">
                          No reading materials selected for library matching.
                        </p>
                      </div>
                    ) : libraryMatchingStatus.error ? (
                      <div className="text-center space-y-4">
                        <AlertCircle className="w-12 h-12 mx-auto mb-4 text-red-500" />
                        <div>
                          <p className="text-red-600 font-medium mb-2">Library Matching Error</p>
                          <p className="text-sm text-muted-foreground mb-4">{libraryMatchingStatus.error}</p>
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => {
                              setLibraryMatchingStatus({ isProcessing: false, progress: 0, message: "", error: null })
                              if (currentJob) startPrimoCheck(currentJob.job_id)
                            }}
                          >
                            Retry Library Matching
                          </Button>
                        </div>
                      </div>
                    ) : libraryMatchingStatus.isProcessing ? (
                      <div className="space-y-4">
                        <div className="flex items-center justify-center gap-3 mb-4">
                          <Loader2 className="w-6 h-6 animate-spin text-accent" />
                          <span className="font-medium">Matching Library Resources</span>
                        </div>
                        
                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span>Progress</span>
                            <span>{libraryMatchingStatus.progress}%</span>
                          </div>
                          <Progress value={libraryMatchingStatus.progress} className="w-full" />
                        </div>
                        
                        <p className="text-sm text-muted-foreground text-center">
                          {libraryMatchingStatus.message || "Searching library catalog for reading materials..."}
                        </p>
                        
                        <div className="text-xs text-muted-foreground text-center space-y-1">
                          <p>• Analyzing extracted reading materials</p>
                          <p>• Searching library catalog via Primo API</p>
                          <p>• Checking availability and formats</p>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center">
                        <Book className="w-12 h-12 mx-auto mb-4 opacity-50" />
                        <p className="text-muted-foreground mb-4">
                          Ready to search library resources for reading materials.
                        </p>
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => {
                            if (currentJob) {
                              setLibraryMatchingStatus({
                                isProcessing: true,
                                progress: 0,
                                message: "Starting library resource matching...",
                                error: null
                              })
                              startPrimoCheck(currentJob.job_id)
                            }
                          }}
                        >
                          Start Library Matching
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ) : (
                libraryMatches.map((match, index) => (
                <Card key={index}>
                  <CardHeader>
                    <CardTitle className="text-base">{match.originalQuery}</CardTitle>
                    <CardDescription className="flex items-center gap-2">
                      <Badge variant="outline">Match Score: {(match.matchScore * 100).toFixed(0)}%</Badge>
                      <Badge variant="secondary">
                        {match.matches.length} {match.matches.length === 1 ? "resource" : "resources"} found
                      </Badge>
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {match.matches.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {match.matches.map((resource, resourceIndex) => (
                          <LibraryResourceCard key={resourceIndex} resource={resource} />
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <Book className="w-12 h-12 mx-auto mb-2 opacity-50" />
                        <p className="font-medium">Not Found</p>
                        <p className="text-sm">This resource was not found in the library catalog</p>
                        <p className="text-xs mt-1">Consider requesting this resource or checking alternative sources</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
                ))
              )}
            </div>

            {/* Action Buttons */}
            <div className="max-w-4xl mx-auto flex justify-center gap-4">
              <Button variant="outline" onClick={resetAnalysis}>
                Analyze New Syllabi
              </Button>
              <Button onClick={downloadResults} className="flex items-center gap-2">
                <Download className="w-4 h-4" />
                Export Results
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

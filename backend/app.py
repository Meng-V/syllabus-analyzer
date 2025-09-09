#!/usr/bin/env python3
"""
Syllabus Analyzer Backend API
FastAPI server providing endpoints for the complete syllabus analysis workflow
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional
import os
import json
import asyncio
import uuid
from pathlib import Path
import shutil
from datetime import datetime
import csv
import io

# Import your existing modules
import sys
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

from florida_pdf_downloader_v2 import UFLSyllabiDownloader

# Import primo integration
from primo_integration import check_metadata_availability

# Import extraction functions
def get_extraction_functions():
    """
    Dynamically import extraction functions with graceful fallback handling.
    
    Returns:
        Tuple of (extract_text_func, llm_extract_func, heuristic_func, extract_tables_func)
        
    Raises:
        Exception: If no extraction functions are available
    """
    try:
        # Import from parent directory scripts folder
        sys.path.append(str(Path(__file__).parent.parent / "scripts"))
        from syllabus_extractor import (
            extract_text_from_pdf,
            call_llm_for_metadata,
            heuristic_parse,
            extract_tables_from_pdf
        )
        return extract_text_from_pdf, call_llm_for_metadata, heuristic_parse, extract_tables_from_pdf
    except ImportError as e:
        print(f"Warning: Enhanced extraction functions unavailable: {e}")
        # Create minimal fallback functions
        def basic_extract_text(pdf_path):
            """Basic text extraction fallback."""
            import fitz
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
            
        def no_llm_extract(text):
            raise Exception("OpenAI LLM extraction not available - missing dependencies or API key")
            
        def basic_heuristic(text):
            """Minimal heuristic extraction."""
            return {
                "year": "Unknown",
                "semester": "Unknown", 
                "class_name": "Unknown",
                "class_number": "Unknown",
                "instructor": "Unknown",
                "university": "Unknown",
                "main_topic": "Unknown",
                "reading_materials": []
            }
            
        def no_tables(pdf_path):
            return []
            
        return basic_extract_text, no_llm_extract, basic_heuristic, no_tables

app = FastAPI(title="Syllabus Analyzer API", version="1.0.0")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for job status
jobs_status = {}
DOWNLOADS_DIR = Path(__file__).parent / "downloads"
RESULTS_DIR = Path(__file__).parent / "results"

# Ensure directories exist
DOWNLOADS_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# Pydantic models
class URLInput(BaseModel):
    url: HttpUrl
    job_name: Optional[str] = None

class MetadataSelection(BaseModel):
    job_id: str
    selected_fields: List[str]

class JobStatus(BaseModel):
    job_id: str
    status: str  # "pending", "downloading", "processing", "completed", "error"
    progress: int  # 0-100
    message: str
    files_found: Optional[int] = None
    files_downloaded: Optional[int] = None
    files_processed: Optional[int] = None
    results: Optional[Dict[str, Any]] = None

class CustomDownloader(UFLSyllabiDownloader):
    """Extended downloader with progress tracking"""
    
    def __init__(self, base_url: str, download_folder: str, job_id: str):
        super().__init__(base_url, download_folder)
        self.job_id = job_id
        self.progress_callback = None
        # Ensure all required attributes are initialized
        if not hasattr(self, 'downloaded_files'):
            self.downloaded_files = set()
    
    def set_progress_callback(self, callback):
        self.progress_callback = callback
    
    def update_progress(self, message: str, progress: int, **kwargs):
        if self.progress_callback:
            self.progress_callback(message, progress, **kwargs)
        
        # Update global job status
        if self.job_id in jobs_status:
            jobs_status[self.job_id].update({
                "message": message,
                "progress": progress,
                **kwargs
            })

@app.get("/")
async def root():
    return {"message": "Syllabus Analyzer API is running"}

@app.post("/api/discover-syllabi", response_model=Dict[str, str])
async def discover_syllabi(url_input: URLInput, background_tasks: BackgroundTasks):
    """Step 1: Discover syllabus PDFs from provided URL"""
    job_id = str(uuid.uuid4())
    job_folder = DOWNLOADS_DIR / job_id
    job_folder.mkdir(exist_ok=True)
    
    # Initialize job status
    jobs_status[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Starting PDF discovery...",
        "url": str(url_input.url),
        "job_name": url_input.job_name or f"Job_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "created_at": datetime.now().isoformat(),
        "files_found": None,
        "files_downloaded": None
    }
    
    # Start background task
    background_tasks.add_task(discover_and_download_pdfs, str(url_input.url), job_id, str(job_folder))
    
    return {"job_id": job_id, "status": "started"}

async def discover_and_download_pdfs(url: str, job_id: str, download_folder: str):
    """Background task to discover and download PDFs"""
    try:
        # Update status
        jobs_status[job_id]["status"] = "downloading"
        jobs_status[job_id]["message"] = "Discovering PDF files..."
        jobs_status[job_id]["progress"] = 10
        
        # Create custom downloader
        downloader = CustomDownloader(url, download_folder, job_id)
        
        def progress_callback(message: str, progress: int, **kwargs):
            jobs_status[job_id].update({
                "message": message,
                "progress": progress,
                **kwargs
            })
        
        downloader.set_progress_callback(progress_callback)
        
        # Get semester links
        semester_links = downloader.get_semester_links()
        if not semester_links:
            semester_links = [url]
        
        # Collect all PDF links
        all_pdf_links = []
        progress_callback("Scanning for PDF files...", 20)
        
        for i, semester_url in enumerate(semester_links):
            pdf_links = downloader.get_pdf_links_from_page(semester_url)
            all_pdf_links.extend(pdf_links)
            progress = 20 + (30 * (i + 1) / len(semester_links))
            progress_callback(f"Scanned {i+1}/{len(semester_links)} pages", int(progress))
        
        # Remove duplicates
        unique_pdfs = {}
        for pdf in all_pdf_links:
            unique_pdfs[pdf['url']] = pdf
        all_pdf_links = list(unique_pdfs.values())
        
        jobs_status[job_id]["files_found"] = len(all_pdf_links)
        progress_callback(f"Found {len(all_pdf_links)} PDF files", 50)
        
        # TESTING MODIFICATION: Limit downloads to 5 files for local testing
        # TO REVERT: Remove the [:5] slice below to download all files
        limited_pdf_links = all_pdf_links[:5]
        progress_callback(f"TESTING MODE: Limited to {len(limited_pdf_links)} files (out of {len(all_pdf_links)} found)", 50)
        
        # Download PDFs
        successful_downloads = 0
        for i, pdf_info in enumerate(limited_pdf_links):
            try:
                success = downloader.download_pdf(pdf_info)
                if success:
                    successful_downloads += 1
                
                progress = 50 + (40 * (i + 1) / len(limited_pdf_links))
                progress_callback(f"Downloaded {successful_downloads}/{len(limited_pdf_links)} files", int(progress))
                
            except Exception as e:
                print(f"Error downloading {pdf_info['url']}: {e}")
        
        jobs_status[job_id]["files_downloaded"] = successful_downloads
        jobs_status[job_id]["status"] = "completed"
        jobs_status[job_id]["progress"] = 100
        jobs_status[job_id]["message"] = f"Download complete! {successful_downloads}/{len(limited_pdf_links)} files downloaded (TESTING MODE: limited from {len(all_pdf_links)} total)"
        
    except Exception as e:
        jobs_status[job_id]["status"] = "error"
        jobs_status[job_id]["message"] = f"Error: {str(e)}"
        jobs_status[job_id]["progress"] = 0

@app.get("/api/job-status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the current status of a job"""
    if job_id not in jobs_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatus(**jobs_status[job_id])

@app.get("/api/jobs")
async def list_jobs():
    """List all jobs"""
    return {"jobs": list(jobs_status.values())}

@app.get("/api/metadata-fields")
async def get_available_metadata_fields():
    """Get list of available metadata fields for extraction"""
    return {
        "fields": [
            {"id": "year", "label": "Year", "description": "Academic year"},
            {"id": "semester", "label": "Semester", "description": "Academic semester"},
            {"id": "class_name", "label": "Class Name", "description": "Course title"},
            {"id": "class_number", "label": "Class Number", "description": "Course code"},
            {"id": "instructor", "label": "Instructor", "description": "Course instructor"},
            {"id": "university", "label": "University", "description": "Institution name"},
            {"id": "main_topic", "label": "Main Topic", "description": "Course subject/topic"},
            {"id": "reading_materials", "label": "Reading Materials", "description": "Required and suggested readings"}
        ]
    }

@app.post("/api/extract-metadata")
async def extract_metadata(selection: MetadataSelection, background_tasks: BackgroundTasks):
    """Step 3: Extract metadata from downloaded PDFs"""
    if selection.job_id not in jobs_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_folder = DOWNLOADS_DIR / selection.job_id
    if not job_folder.exists():
        raise HTTPException(status_code=404, detail="Job folder not found")
    
    # Update job status
    jobs_status[selection.job_id]["status"] = "processing"
    jobs_status[selection.job_id]["progress"] = 0
    jobs_status[selection.job_id]["message"] = "Starting metadata extraction..."
    jobs_status[selection.job_id]["selected_fields"] = selection.selected_fields
    
    # Start background task
    background_tasks.add_task(extract_metadata_background, selection.job_id, selection.selected_fields)
    
    return {"status": "started", "message": "Metadata extraction started"}

async def extract_metadata_background(job_id: str, selected_fields: List[str]):
    """Background task to extract metadata from PDFs using o4-mini"""
    try:
        # Get extraction functions
        extract_text_func, llm_extract_func, heuristic_func, extract_tables_func = get_extraction_functions()
        
        job_folder = DOWNLOADS_DIR / job_id
        pdf_files = list(job_folder.glob("*.pdf"))
        
        if not pdf_files:
            jobs_status[job_id]["status"] = "error"
            jobs_status[job_id]["message"] = "No PDF files found"
            return
        
        results = []
        
        for i, pdf_path in enumerate(pdf_files):
            try:
                # Update progress
                progress = int((i / len(pdf_files)) * 80)
                jobs_status[job_id]["progress"] = progress
                jobs_status[job_id]["message"] = f"Processing {pdf_path.name} ({i+1}/{len(pdf_files)})"
                
                # Extract text and tables (enhanced extraction)
                text = extract_text_func(pdf_path)
                
                if not text:
                    continue
                
                # Extract tables and enhance text
                try:
                    table_markdowns = extract_tables_func(pdf_path)
                    if table_markdowns:
                        text += "\n\n# TABLES (markdown format)\n" + "\n\n".join(table_markdowns)
                        print(f"Enhanced text with {len(table_markdowns)} tables for {pdf_path.name}")
                except Exception as e:
                    print(f"Table extraction failed for {pdf_path.name}: {e}")
                    # Continue with just text
                
                # Try AI extraction first, fall back to heuristic
                try:
                    if llm_extract_func:
                        # Use o4-mini extraction
                        metadata = llm_extract_func(text)
                        print(f"Successfully extracted metadata using o4-mini for {pdf_path.name}")
                except Exception as e:
                    print(f"o4-mini extraction failed for {pdf_path.name}: {e}")
                    # Use heuristic fallback
                    try:
                        metadata = heuristic_func(text)
                        print(f"Used heuristic fallback for {pdf_path.name}")
                    except Exception as fallback_error:
                        print(f"Heuristic fallback also failed for {pdf_path.name}: {fallback_error}")
                        metadata = {}
                        for field in selected_fields:
                            metadata[field] = "Unknown"
                
                # Filter to selected fields only
                filtered_metadata = {}
                for field in selected_fields:
                    if field in metadata:
                        filtered_metadata[field] = metadata[field]
                    else:
                        filtered_metadata[field] = "Unknown"
                
                results.append({
                    "filename": pdf_path.name,
                    "metadata": filtered_metadata
                })
                
            except Exception as e:
                print(f"Error processing {pdf_path}: {e}")
                continue
        
        # Save results
        results_file = RESULTS_DIR / f"{job_id}_metadata.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        jobs_status[job_id]["status"] = "completed"
        jobs_status[job_id]["progress"] = 100
        jobs_status[job_id]["message"] = f"Metadata extraction complete! Processed {len(results)} files"
        jobs_status[job_id]["files_processed"] = len(results)
        jobs_status[job_id]["results_file"] = str(results_file)
        
    except Exception as e:
        jobs_status[job_id]["status"] = "error"
        jobs_status[job_id]["message"] = f"Error: {str(e)}"

@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    """Get extraction results for a job"""
    # Check for Primo results first, then regular results
    primo_file = RESULTS_DIR / f"{job_id}_primo_results.json"
    regular_file = RESULTS_DIR / f"{job_id}_metadata.json"
    
    if primo_file.exists():
        with open(primo_file, 'r') as f:
            results = json.load(f)
        return {"results": results}
    elif regular_file.exists():
        with open(regular_file, 'r') as f:
            results = json.load(f)
        return {"results": results}
    else:
        raise HTTPException(status_code=404, detail="Results not found")

@app.post("/api/check-primo/{job_id}")
async def check_primo_resources(job_id: str, background_tasks: BackgroundTasks):
    """Step 4: Check reading materials against Primo API"""
    if job_id not in jobs_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if job is already processing library matching
    current_status = jobs_status[job_id].get("status")
    if current_status == "processing":
        current_message = jobs_status[job_id].get("message", "")
        if "Primo" in current_message or "library" in current_message.lower():
            return {"status": "already_running", "message": "Library matching is already in progress"}
    
    results_file = RESULTS_DIR / f"{job_id}_metadata.json"
    if not results_file.exists():
        raise HTTPException(status_code=404, detail="Metadata results not found. Please ensure metadata extraction completed successfully.")
    
    # Validate results file
    try:
        with open(results_file, 'r') as f:
            results = json.load(f)
        if not results:
            raise HTTPException(status_code=400, detail="No metadata results found to process")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata results file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading metadata results: {str(e)}")
    
    # Start background task
    background_tasks.add_task(check_primo_background, job_id)
    
    return {"status": "started", "message": "Library resource matching started successfully"}

async def check_primo_background(job_id: str):
    """Background task to check reading materials via Primo API"""
    try:
        results_file = RESULTS_DIR / f"{job_id}_metadata.json"
        
        if not results_file.exists():
            jobs_status[job_id]["status"] = "error"
            jobs_status[job_id]["message"] = "Metadata results file not found"
            return
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        if not results:
            jobs_status[job_id]["status"] = "error"
            jobs_status[job_id]["message"] = "No results found to process"
            return
        
        jobs_status[job_id]["status"] = "processing"
        jobs_status[job_id]["progress"] = 0
        jobs_status[job_id]["message"] = "Starting library resource matching via Primo API..."
        
        total_files = len(results)
        processed_files = 0
        successful_matches = 0
        
        for i, result in enumerate(results):
            try:
                # Update progress with detailed status
                progress = int((i / total_files) * 90)  # Reserve 10% for final processing
                jobs_status[job_id]["progress"] = progress
                jobs_status[job_id]["message"] = f"Checking resources for {result['filename']} ({i+1}/{total_files})"
                
                # Check if reading materials exist
                reading_materials = result.get('metadata', {}).get('reading_materials', [])
                if not reading_materials:
                    result['primo_check'] = {
                        "found": False,
                        "error": "No reading materials found in metadata",
                        "metadata": result['metadata']
                    }
                    result['library_matches'] = []
                    continue
                
                # Check reading materials using the metadata-based approach
                primo_result = await check_metadata_availability(result['metadata'])
                result['primo_check'] = primo_result
                
                # Extract properly formatted library matches
                library_matches = primo_result.get('library_matches', [])
                result['library_matches'] = library_matches
                
                if library_matches:
                    successful_matches += 1
                    
                processed_files += 1
                
            except Exception as e:
                print(f"Error processing {result.get('filename', 'unknown')}: {str(e)}")
                result['primo_check'] = {
                    "found": False,
                    "error": f"API error: {str(e)}",
                    "metadata": result.get('metadata', {})
                }
                result['library_matches'] = []
                processed_files += 1
        
        # Final processing
        jobs_status[job_id]["progress"] = 95
        jobs_status[job_id]["message"] = "Saving library matching results..."
        
        # Save updated results
        primo_results_file = RESULTS_DIR / f"{job_id}_primo_results.json"
        with open(primo_results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Complete with summary
        jobs_status[job_id]["status"] = "completed"
        jobs_status[job_id]["progress"] = 100
        jobs_status[job_id]["message"] = f"Library matching complete! Found matches for {successful_matches}/{processed_files} syllabi"
        jobs_status[job_id]["primo_results_file"] = str(primo_results_file)
        
    except FileNotFoundError:
        jobs_status[job_id]["status"] = "error"
        jobs_status[job_id]["message"] = "Results file not found. Please ensure metadata extraction completed successfully."
    except json.JSONDecodeError:
        jobs_status[job_id]["status"] = "error"
        jobs_status[job_id]["message"] = "Invalid results file format. Please re-run metadata extraction."
    except Exception as e:
        print(f"Unexpected error in check_primo_background: {str(e)}")
        jobs_status[job_id]["status"] = "error"
        jobs_status[job_id]["message"] = f"Library matching failed: {str(e)}"

@app.get("/api/download-results/{job_id}")
async def download_results(job_id: str):
    """Download results as JSON file"""
    if job_id not in jobs_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check for Primo results first, then regular results
    primo_file = RESULTS_DIR / f"{job_id}_primo_results.json"
    regular_file = RESULTS_DIR / f"{job_id}_metadata.json"
    
    if primo_file.exists():
        return FileResponse(primo_file, filename=f"syllabus_analysis_{job_id}_complete.json")
    elif regular_file.exists():
        return FileResponse(regular_file, filename=f"syllabus_analysis_{job_id}_metadata.json")
    else:
        raise HTTPException(status_code=404, detail="Results not found")

@app.get("/api/download-csv/{job_id}")
async def download_csv(job_id: str):
    """Download results as CSV file"""
    if job_id not in jobs_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check for Primo results first, then regular results
    primo_file = RESULTS_DIR / f"{job_id}_primo_results.json"
    regular_file = RESULTS_DIR / f"{job_id}_metadata.json"
    
    results_file = primo_file if primo_file.exists() else regular_file
    if not results_file.exists():
        raise HTTPException(status_code=404, detail="Results not found")
    
    try:
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Create CSV content
        csv_content = generate_csv_from_results(results)
        
        # Create streaming response
        def iter_csv():
            yield csv_content.encode('utf-8')
        
        headers = {
            'Content-Disposition': f'attachment; filename="syllabus_analysis_{job_id}.csv"',
            'Content-Type': 'text/csv; charset=utf-8'
        }
        
        return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating CSV: {str(e)}")

def generate_csv_from_results(results: List[Dict]) -> str:
    """Generate CSV content from results data"""
    if not results:
        return "No data available"
    
    # Create CSV in memory
    output = io.StringIO()
    
    # Determine all possible fields from all results
    all_fields = set(['filename'])
    for result in results:
        if 'metadata' in result:
            all_fields.update(result['metadata'].keys())
    
    # Remove reading_materials from regular fields (we'll handle it separately)
    regular_fields = [f for f in sorted(all_fields) if f != 'reading_materials']
    
    # Add reading materials columns
    reading_materials_fields = [
        'reading_materials_count',
        'required_materials',
        'optional_materials',
        'reading_materials_list'
    ]
    
    # Add library matching fields
    library_fields = [
        'library_matches_count',
        'available_resources',
        'unavailable_resources'
    ]
    
    fieldnames = regular_fields + reading_materials_fields + library_fields
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for result in results:
        row = {}
        
        # Add filename
        row['filename'] = result.get('filename', '')
        
        # Add regular metadata fields
        metadata = result.get('metadata', {})
        for field in regular_fields:
            if field == 'filename':
                continue
            value = metadata.get(field, '')
            # Convert lists to string representation (except reading_materials)
            if isinstance(value, list) and field != 'reading_materials':
                row[field] = '; '.join(str(item) for item in value)
            else:
                row[field] = str(value) if value is not None else ''
        
        # Handle reading materials
        reading_materials = metadata.get('reading_materials', [])
        if reading_materials:
            required_materials = []
            optional_materials = []
            all_materials = []
            
            for item in reading_materials:
                if isinstance(item, dict):
                    title = item.get('title', 'Unknown Title')
                    author = item.get('creator') or item.get('author', '')
                    requirement = item.get('requirement', 'optional')
                    material_type = item.get('type', 'book')
                    
                    material_str = f"{title}"
                    if author:
                        material_str += f" by {author}"
                    material_str += f" ({material_type})"
                    
                    all_materials.append(material_str)
                    if requirement == 'required':
                        required_materials.append(material_str)
                    else:
                        optional_materials.append(material_str)
                else:
                    material_str = str(item)
                    all_materials.append(material_str)
                    optional_materials.append(material_str)
            
            row['reading_materials_count'] = len(reading_materials)
            row['required_materials'] = '; '.join(required_materials)
            row['optional_materials'] = '; '.join(optional_materials)
            row['reading_materials_list'] = '; '.join(all_materials)
        else:
            row['reading_materials_count'] = 0
            row['required_materials'] = ''
            row['optional_materials'] = ''
            row['reading_materials_list'] = ''
        
        # Handle library matches
        library_matches = result.get('library_matches', [])
        if library_matches:
            available_count = 0
            unavailable_count = 0
            available_resources = []
            unavailable_resources = []
            
            for match in library_matches:
                if isinstance(match, dict) and 'matches' in match:
                    for resource in match.get('matches', []):
                        if isinstance(resource, dict):
                            title = resource.get('title', 'Unknown')
                            availability = resource.get('availability', 'unknown')
                            if availability == 'available':
                                available_count += 1
                                available_resources.append(title)
                            else:
                                unavailable_count += 1
                                unavailable_resources.append(f"{title} ({availability})")
            
            row['library_matches_count'] = len(library_matches)
            row['available_resources'] = '; '.join(available_resources)
            row['unavailable_resources'] = '; '.join(unavailable_resources)
        else:
            row['library_matches_count'] = 0
            row['available_resources'] = ''
            row['unavailable_resources'] = ''
        
        writer.writerow(row)
    
    return output.getvalue()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

#!/usr/bin/env python3
"""
Syllabus Metadata Extractor
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Core module for extracting structured metadata from PDF syllabi using o4-mini.

This module provides functions for:
- PDF text extraction with PyMuPDF
- Table extraction and markdown conversion
- AI-powered metadata extraction using o4-mini
- Heuristic fallback parsing

Used by the Syllabus Analyzer backend for processing uploaded PDFs.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List

import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration ----------------------------------------------------------------
load_dotenv()
API_KEY: str | None = os.getenv("OPENAI_API_KEY")

# Model configuration
LLM_MODEL = "o4-mini"  # Using o4-mini for enhanced extraction

# Initialize OpenAI client
client = None
if API_KEY:
    client = OpenAI(api_key=API_KEY)

# ---------------------------------------------------------------------------
# Helper functions -------------------------------------------------------------

def extract_year_semester_from_filename(filename: str) -> dict:
    # Example: "BIO101_Fall2023_Smith.pdf"
    semester_match = SEMESTER_RE.search(filename)
    year_match = YEAR_RE.search(filename)
    semester = semester_match.group(1) if semester_match else None
    year = year_match.group(1) if year_match else None
    return {"year": year, "semester": semester}
    
def extract_text_from_pdf(pdf_path: Path) -> str:
    """Return **all** text contained in *pdf_path*."""
    doc = fitz.open(pdf_path)
    text_chunks: List[str] = []
    for page in doc:
        text_chunks.append(page.get_text("text"))  # raw text
    doc.close()
    return "\n".join(text_chunks)

def extract_tables_from_pdf(pdf_path: Path) -> List[str]:
    """Extract all tables from the PDF and return as markdown strings (one per table)."""
    doc = fitz.open(pdf_path)
    table_markdowns = []
    for page in doc:
        try:
            tables = page.find_tables()
            for table in tables:
                df = table.to_pandas()
                # Clean up empty rows/columns
                df = df.dropna(how='all').dropna(axis=1, how='all')
                if not df.empty:
                    table_markdowns.append(df.to_markdown(index=False))
        except Exception as e:
            continue  # If table extraction fails on a page, skip
    doc.close()
    return table_markdowns


def call_llm_for_metadata(pdf_text: str) -> Dict:
    """
    Extract structured metadata from syllabus text using o4-mini.
    
    Args:
        pdf_text: Complete text content of the PDF including tables
        
    Returns:
        Dict containing structured metadata with keys:
        year, semester, class_name, class_number, instructor, university, 
        main_topic, reading_materials
        
    Raises:
        Exception: If OpenAI client is not initialized or API call fails
    """
    if not client or not API_KEY:
        raise Exception("OpenAI client not initialized - API key missing")
        
    system_prompt = (
        "You are a precise academic metadata extraction assistant. "
        "Extract structured information from university course syllabi. "
        "Return ONLY valid JSON with these exact keys: "
        "year, semester, class_name, class_number, instructor, university, main_topic, reading_materials.\n\n"
        "Rules:\n"
        "- main_topic: Course focus, objectives, and key learning outcomes\n"
        "- reading_materials: Array of objects with keys: title, media_type, requirement, ISBN, url, journal_names, certainty\n"
        "- media_type options: 'books', 'journal articles', 'book chapters', 'websites', 'videos', 'equipment'\n"
        "- requirement: 'required' or 'suggested'\n"
        "- certainty: 0-100 (confidence in extraction accuracy)\n"
        "- Use 'Unknown' for missing information\n"
        "- No hallucination - only extract what is clearly present"
    )

    user_prompt = (
        "Extract the requested fields from the following syllabus text.\n\n" + pdf_text
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content.strip()

    # Ensure the assistant responded with pure JSON.  Trim code fencing if any.
    content = re.sub(r"^```json|```$", "", content).strip()
    data = json.loads(content)
    return data


# Regex patterns for heuristic fallback parsing
SEMESTER_RE = re.compile(r"\b(Spring|Summer|Fall|Winter)\b", re.I)
YEAR_RE = re.compile(r"(20\d{2})")
COURSE_CODE_RE = re.compile(r"([A-Z]{2,4}[\s-]?\d{3,4})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.edu)")
INSTRUCTOR_RE = re.compile(r"(?:Instructor|Professor|Dr\.|Teacher):\s*([^\n]+)", re.I)


def heuristic_parse(text: str) -> Dict:
    """
    Fallback parser using regex patterns when o4-mini fails.
    
    Args:
        text: Raw text content from PDF
        
    Returns:
        Dict with basic metadata extracted using pattern matching
    """
    semester_match = SEMESTER_RE.search(text)
    year_match = YEAR_RE.search(text)
    code_match = COURSE_CODE_RE.search(text)
    email_match = EMAIL_RE.search(text)
    instructor_match = INSTRUCTOR_RE.search(text)

    # Extract basic information
    semester = semester_match.group(1) if semester_match else "Unknown"
    year = year_match.group(1) if year_match else "Unknown"
    class_number = code_match.group(1) if code_match else "Unknown"
    instructor = instructor_match.group(1).strip() if instructor_match else "Unknown"

    # Find potential class title from first meaningful line
    class_name = "Unknown"
    for line in text.splitlines()[:10]:  # Check first 10 lines
        line = line.strip()
        if 10 < len(line) < 100 and any(c.isupper() for c in line):
            class_name = line
            break

    # Extract university from email domain
    university = "Unknown"
    if email_match:
        domain_parts = email_match.group(1).split(".")
        if len(domain_parts) >= 2:
            university = domain_parts[0].upper()

    return {
        "year": year,
        "semester": semester,
        "class_name": class_name,
        "class_number": class_number,
        "instructor": instructor,
        "university": university,
        "main_topic": "Unknown",
        "reading_materials": [],
    }


# ---------------------------------------------------------------------------
# Standalone script execution (when run directly) -----------------------------

def process_pdfs_batch(pdf_directory: Path, output_file: Path, start_idx: int = 0, end_idx: int = None):
    """
    Process a batch of PDFs for metadata extraction.
    
    Args:
        pdf_directory: Directory containing PDF files
        output_file: Path for CSV output file
        start_idx: Starting index for processing
        end_idx: Ending index for processing (None for all)
    """
    if not pdf_directory.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_directory}")
    
    pdf_files = sorted(pdf_directory.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {pdf_directory}")
        return
    
    # Apply range filtering
    if end_idx is None:
        end_idx = len(pdf_files)
    pdf_files = pdf_files[start_idx:end_idx]
    
    print(f"Processing {len(pdf_files)} PDFs from {pdf_directory}")
    
    rows = []
    for i, pdf_path in enumerate(pdf_files):
        print(f"\n→ Processing {pdf_path.name} ({i+1}/{len(pdf_files)})")
        
        try:
            # Extract text and tables
            text = extract_text_from_pdf(pdf_path)
            table_markdowns = extract_tables_from_pdf(pdf_path)
            combined_text = text
            if table_markdowns:
                combined_text += "\n\n# TABLES (markdown format)\n" + "\n\n".join(table_markdowns)

            # Try o4-mini extraction first
            try:
                data = call_llm_for_metadata(combined_text)
                print(f"   ✓ o4-mini extraction successful")
            except Exception as exc:
                print(f"   ⚠ o4-mini failed, using heuristics: {exc}")
                data = heuristic_parse(text)

            # Add filename and prepare for CSV
            data["filename"] = pdf_path.name
            data["reading_materials_json"] = json.dumps(data.get("reading_materials", []), ensure_ascii=False)
            data.pop("reading_materials", None)  # Remove nested structure for CSV
            
            rows.append(data)
            
        except Exception as e:
            print(f"   ✗ Failed to process {pdf_path.name}: {e}")
            continue

    # Write results to CSV
    if rows:
        print(f"\nWriting {len(rows)} results to {output_file}")
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)
        print("✓ Batch processing complete")
    else:
        print("No PDFs were successfully processed")


if __name__ == "__main__":
    # Default batch processing configuration
    default_dir = Path(__file__).parent / "pdfs"
    default_output = Path(__file__).parent / "syllabus_metadata_extracted.csv"
    
    # Process PDFs if directory exists
    if default_dir.exists():
        process_pdfs_batch(default_dir, default_output)
    else:
        print(f"Default PDF directory not found: {default_dir}")
        print("This module is primarily used by the Syllabus Analyzer backend.")
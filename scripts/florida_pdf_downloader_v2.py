#!/usr/bin/env python3
"""
Florida PDF Downloader v2

Enhanced PDF downloader for University of Florida syllabus collection with:
- Concurrent downloads with rate limiting
- Filename sanitization and preservation
- Progress tracking and error handling
- Configurable download limits for testing

Used by the Syllabus Analyzer backend for automated PDF collection.
"""

import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class UFLSyllabiDownloader:
    """
    Downloader for University of Florida College of Arts syllabi PDFs.
    
    Features:
    - Concurrent downloads with configurable thread pool
    - Progress tracking and error handling
    - Filename sanitization for cross-platform compatibility
    - Download limiting for testing purposes
    """
    
    def __init__(self, base_url="https://arts.ufl.edu/syllabi/", download_folder="florida"):
        """
        Initialize the downloader.
        
        Args:
            base_url: Base URL for UFL syllabi website
            download_folder: Local folder for downloaded PDFs
        """
        self.base_url = base_url
        self.download_folder = Path(download_folder)
        self.downloaded_count = 0
        self.failed_count = 0
        self.lock = threading.Lock()
        self.downloaded_files = set()  # Track downloaded filenames to avoid duplicates
        
        # Create download folder if it doesn't exist
        self.download_folder.mkdir(exist_ok=True)
        print(f"Download folder: {self.download_folder.absolute()}")
        
    def create_session(self):
        """Create a new session with proper headers."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        return session
        
    def create_download_folder(self):
        """Create the download folder if it doesn't exist."""
        self.download_folder.mkdir(exist_ok=True)
        print(f"Created/verified download folder: {self.download_folder.absolute()}")
    
    def get_semester_links(self):
        """Get all semester page links from the main syllabi page."""
        try:
            session = self.create_session()
            response = session.get(self.base_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            semester_links = []
            # Look for links that contain semester patterns
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/syllabi/' in href and any(term in href.lower() for term in ['spring', 'summer', 'fall']):
                    full_url = urljoin(self.base_url, href)
                    semester_links.append(full_url)
            
            # Remove duplicates and sort
            semester_links = list(set(semester_links))
            semester_links.sort()
            
            print(f"Found {len(semester_links)} semester pages:")
            for link in semester_links:
                print(f"  - {link}")
            
            return semester_links
            
        except Exception as e:
            print(f"Error getting semester links: {e}")
            return []
    
    def get_pdf_links_from_page(self, url):
        """Extract all PDF links from a given page."""
        try:
            print(f"Scanning page: {url}")
            session = self.create_session()
            response = session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            pdf_links = []
            # Find all links that point to PDF files
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.lower().endswith('.pdf'):
                    full_url = urljoin(url, href)
                    pdf_links.append({
                        'url': full_url,
                        'title': link.get_text(strip=True) or 'Untitled'
                    })
            
            print(f"  Found {len(pdf_links)} PDF links")
            return pdf_links
            
        except Exception as e:
            print(f"Error scanning page {url}: {e}")
            return []
    
    def sanitize_filename(self, filename):
        """Sanitize filename for safe file system storage."""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove extra whitespace and limit length
        filename = ' '.join(filename.split())[:200]
        return filename
    
    def download_pdf(self, pdf_info, session=None):
        """Download a single PDF file."""
        if session is None:
            session = self.create_session()
            
        url = pdf_info['url']
        title = pdf_info['title']
        
        try:
            # Generate filename from URL if title is not useful
            parsed_url = urlparse(url)
            url_filename = os.path.basename(parsed_url.path)
            
            if len(title) > 10 and not title.lower().startswith('http'):
                base_filename = self.sanitize_filename(title)
                if not base_filename.lower().endswith('.pdf'):
                    base_filename += '.pdf'
            else:
                base_filename = url_filename if url_filename.endswith('.pdf') else 'syllabus.pdf'
            
            # Ensure unique filename (thread-safe)
            with self.lock:
                counter = 1
                filename = base_filename
                while filename in self.downloaded_files:
                    name, ext = os.path.splitext(base_filename)
                    filename = f"{name}_{counter}{ext}"
                    counter += 1
                
                file_path = self.download_folder / filename
                
                # Skip if file already exists
                if file_path.exists():
                    print(f"  Skipping (already exists): {filename}")
                    self.downloaded_files.add(filename)
                    return True
                
                # Mark as being downloaded
                self.downloaded_files.add(filename)
            
            # Download the file
            print(f"  Downloading: {filename}")
            response = session.get(url, timeout=30)
            response.raise_for_status()
            
            # Write file
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content)
            print(f"  ✓ Downloaded: {filename} ({file_size} bytes)")
            return True
            
        except Exception as e:
            print(f"  ✗ Error downloading {url}: {e}")
            # Remove from downloaded set if failed
            with self.lock:
                self.downloaded_files.discard(filename)
            return False
    
    def run(self):
        """Main method to run the complete download process."""
        print("UFL Arts Syllabi PDF Downloader v2")
        print("=" * 50)
        
        # Create download folder
        self.create_download_folder()
        
        # Get all semester pages
        semester_links = self.get_semester_links()
        if not semester_links:
            print("No semester pages found. Trying main page only.")
            semester_links = [self.base_url]
        
        # Collect all PDF links
        all_pdf_links = []
        for semester_url in semester_links:
            pdf_links = self.get_pdf_links_from_page(semester_url)
            all_pdf_links.extend(pdf_links)
            time.sleep(1)  # Be respectful to the server
        
        # Remove duplicates based on URL
        unique_pdfs = {}
        for pdf in all_pdf_links:
            unique_pdfs[pdf['url']] = pdf
        all_pdf_links = list(unique_pdfs.values())
        
        print(f"\nTotal unique PDFs found: {len(all_pdf_links)}")
        
        if not all_pdf_links:
            print("No PDF files found on the website.")
            return
        
        # Download all PDFs with limited concurrency
        print(f"\nStarting downloads to: {self.download_folder.absolute()}")
        print("-" * 50)
        
        successful_downloads = 0
        
        # Use ThreadPoolExecutor for concurrent downloads (but limited)
        max_workers = 3  # Conservative to be respectful to server
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks
            future_to_pdf = {}
            for i, pdf_info in enumerate(all_pdf_links):
                future = executor.submit(self.download_pdf, pdf_info)
                future_to_pdf[future] = (i + 1, pdf_info)
            
            # Process completed downloads
            for future in as_completed(future_to_pdf):
                i, pdf_info = future_to_pdf[future]
                try:
                    success = future.result()
                    if success:
                        successful_downloads += 1
                    print(f"Progress: {i}/{len(all_pdf_links)} completed")
                except Exception as e:
                    print(f"  ✗ Unexpected error: {e}")
        
        print("\n" + "=" * 50)
        print(f"Download complete!")
        print(f"Successfully downloaded: {successful_downloads}/{len(all_pdf_links)} files")
        print(f"Files saved to: {self.download_folder.absolute()}")


def main():
    """Main function to run the downloader."""
    downloader = UFLSyllabiDownloader()
    downloader.run()


if __name__ == "__main__":
    main()

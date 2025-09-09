#!/usr/bin/env python3
"""
Primo API Integration Module
Checks if reading materials are available in the library repository via Primo Search API
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus, urlencode
import os
from dotenv import load_dotenv

load_dotenv()

class PrimoAPIClient:
    def __init__(self, api_base_url: str = None, api_key: str = None, vid: str = None, tab: str = None, scope: str = None):
        """
        Initialize Primo Search API client
        
        Args:
            api_base_url: Primo Search API base URL 
            api_key: API key for authentication
            vid: View ID 
            tab: Search tab 
            scope: Search scope 
        """
        self.api_base_url = api_base_url or os.getenv("PRIMO_API_BASE_URL")
        self.api_key = api_key or os.getenv("PRIMO_API_KEY")
        self.vid = vid or os.getenv("PRIMO_VID")
        self.tab = tab or os.getenv("PRIMO_TAB")
        self.scope = scope or os.getenv("PRIMO_SCOPE")
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search_by_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search for resources using extracted syllabus metadata with filtering
        
        Args:
            metadata: Dictionary containing extracted metadata fields
            
        Returns:
            Dictionary containing search results, availability info, and library matches
        """
        if not self.session:
            raise RuntimeError("PrimoAPIClient must be used as async context manager")
        
        try:
            # Extract reading materials from metadata
            reading_materials = metadata.get('reading_materials', [])
            if not reading_materials:
                return {
                    "found": False,
                    "error": "No reading materials found in metadata",
                    "metadata": metadata,
                    "library_matches": []
                }
            
            results = []
            library_matches = []
            
            # Process each reading material with filtering
            for material in reading_materials:
                if isinstance(material, dict):
                    title = material.get('title', '')
                    author = material.get('creator', '')
                    material_type = material.get('type', material.get('media_type', '')).lower()
                    requirement = material.get('requirement', '').lower()
                    existing_url = material.get('url', '')
                    
                    # Filter 1: Skip equipment
                    if requirement == 'equipment' or material_type == 'equipment':
                        continue
                    
                    # Filter 2: Handle existing URLs directly (skip if URL is "Unknown" or empty)
                    if existing_url and existing_url.lower() not in ['unknown', '', 'none']:
                        library_matches.append({
                            "originalQuery": title,
                            "matchScore": 1.0,
                            "matches": [{
                                "title": title,
                                "authors": [author] if author else [],
                                "availability": "available",
                                "format": "Online Resource",
                                "location": "Online",
                                "link": existing_url,
                                "callNumber": None,
                                "dueDate": None,
                                "coverImage": None
                            }]
                        })
                        continue
                    
                elif isinstance(material, str):
                    title = material
                    author = ''
                else:
                    continue
                
                # Filter 3: Search via Primo API if not filtered out
                if title:
                    if self.api_key:
                        search_result = await self._search_single_item(title, author)
                        search_result['original_material'] = material
                        results.append(search_result)
                        
                        # Transform to library match format
                        if search_result.get('found') and search_result.get('results'):
                            matches = []
                            for primo_result in search_result['results']:
                                match = {
                                    "title": primo_result.get('title', 'Unknown'),
                                    "authors": [primo_result.get('creator', 'Unknown')] if primo_result.get('creator') else [],
                                    "availability": self._determine_availability_status(primo_result),
                                    "format": primo_result.get('type', 'Unknown'),
                                    "location": self._extract_location_info(primo_result),
                                    "link": self._extract_access_link(primo_result),
                                    "callNumber": None,  # Could extract from holdings if needed
                                    "dueDate": None,
                                    "coverImage": None
                                }
                                matches.append(match)
                            
                            library_matches.append({
                                "originalQuery": title,
                                "matchScore": 0.8,  # Could calculate based on relevance
                                "matches": matches
                            })
                        else:
                            # Filter 4: Handle "not found" cases
                            library_matches.append({
                                "originalQuery": title,
                                "matchScore": 0.0,
                                "matches": []  # Empty matches indicates "not found"
                            })
                    else:
                        # No API key - mark as not found
                        library_matches.append({
                            "originalQuery": title,
                            "matchScore": 0.0,
                            "matches": []
                        })
            
            return {
                "found": len([r for r in results if r.get('found', False)]) > 0,
                "results": results,
                "metadata": metadata,
                "total_materials": len(reading_materials),
                "found_materials": len([r for r in results if r.get('found', False)]),
                "library_matches": library_matches
            }
                    
        except Exception as e:
            return {
                "found": False,
                "error": str(e),
                "metadata": metadata,
                "library_matches": []
            }
    
    async def _search_single_item(self, title: str, author: str = None) -> Dict[str, Any]:
        """
        Search for a single item in Primo Search API
        
        Args:
            title: Book/article title to search for
            author: Optional author name
            
        Returns:
            Dictionary containing search results and availability info
        """
        try:
            # Build search query
            query_parts = []
            
            if title:
                clean_title = self._clean_search_term(title)
                query_parts.append(f"title,contains,{clean_title}")
            
            if author:
                clean_author = self._clean_search_term(author)
                query_parts.append(f"creator,contains,{clean_author}")
            
            if not query_parts:
                return {
                    "found": False,
                    "error": "No search terms provided",
                    "title": title
                }
            
            # Join query parts with AND
            query = ";AND;".join(query_parts) if len(query_parts) > 1 else query_parts[0]
            
            # Build search parameters
            params = {
                "apikey": self.api_key,
                "q": query,
                "tab": self.tab,
                "scope": self.scope,
                "vid": self.vid,
                "lang": "en",
                "offset": "0",
                "limit": "5",
                "sort": "rank"
            }
            
            # Make API request
            search_url = f"{self.api_base_url}/search"
            
            async with self.session.get(search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_search_results(data, title, author)
                else:
                    error_text = await response.text()
                    return {
                        "found": False,
                        "error": f"API request failed with status {response.status}: {error_text}",
                        "title": title
                    }
                    
        except Exception as e:
            return {
                "found": False,
                "error": str(e),
                "title": title
            }
    
    def _clean_search_term(self, term: str) -> str:
        """Clean search term for API query"""
        if not term:
            return ""
        
        # Remove common prefixes and suffixes
        term = term.strip()
        
        # Remove edition information
        import re
        term = re.sub(r'\b\d+(?:st|nd|rd|th)?\s+ed(?:ition)?\b', '', term, flags=re.IGNORECASE)
        term = re.sub(r'\b(?:edition|ed\.)\b', '', term, flags=re.IGNORECASE)
        
        # Remove publisher information
        term = re.sub(r'\b(?:by|published by|publisher)\s+.*$', '', term, flags=re.IGNORECASE)
        
        # Remove ISBN/ISSN
        term = re.sub(r'\b(?:ISBN|ISSN)[\s:-]*\d+[\d\-X]*\b', '', term, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        term = ' '.join(term.split())
        
        return quote_plus(term)
    
    def _parse_search_results(self, data: Dict[str, Any], original_title: str, author: str = None) -> Dict[str, Any]:
        """Parse Primo Search API results"""
        try:
            docs = data.get("docs", [])
            
            if not docs:
                return {
                    "found": False,
                    "title": original_title,
                    "author": author,
                    "message": "No results found"
                }
            
            # Process results
            results = []
            for doc in docs[:3]:  # Limit to top 3 results
                pnx = doc.get("pnx", {})
                display = pnx.get("display", {})
                addata = pnx.get("addata", {})
                delivery = doc.get("delivery", {})
                
                # Extract title - handle both string and array formats
                title_field = display.get("title", [])
                if isinstance(title_field, list) and title_field:
                    title = title_field[0]
                elif isinstance(title_field, str):
                    title = title_field
                else:
                    title = "Unknown"
                
                # Extract creator/author
                creator_field = display.get("creator", [])
                if isinstance(creator_field, list) and creator_field:
                    creator = creator_field[0]
                elif isinstance(creator_field, str):
                    creator = creator_field
                else:
                    creator = "Unknown"
                
                # Extract other fields
                resource_type = display.get("type", ["Unknown"])
                if isinstance(resource_type, list) and resource_type:
                    resource_type = resource_type[0]
                
                date_field = addata.get("date", [])
                if isinstance(date_field, list) and date_field:
                    date = date_field[0]
                else:
                    date = "Unknown"
                
                result = {
                    "title": title,
                    "creator": creator,
                    "type": resource_type,
                    "date": date,
                    "isbn": addata.get("isbn", []),
                    "issn": addata.get("issn", []),
                    "publisher": addata.get("pub", []),
                    "availability": self._check_availability(doc),
                    "links": self._extract_links(delivery)
                }
                
                results.append(result)
            
            return {
                "found": True,
                "title": original_title,
                "author": author,
                "results": results,
                "total_results": data.get("info", {}).get("total", len(docs))
            }
            
        except Exception as e:
            return {
                "found": False,
                "title": original_title,
                "author": author,
                "error": f"Error parsing results: {str(e)}"
            }
    
    def _check_availability(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Check availability information from Primo Search API document"""
        try:
            delivery = doc.get("delivery", {})
            availability = {
                "available": False,
                "locations": [],
                "online_access": False,
                "physical_copies": 0,
                "delivery_category": []
            }
            
            # Check delivery category
            delcategory = delivery.get("delcategory", [])
            if delcategory:
                availability["delivery_category"] = delcategory
                # If there are delivery options, consider it available
                availability["available"] = True
            
            # Check for online access
            links = delivery.get("link", [])
            if links:
                availability["online_access"] = True
                availability["available"] = True
            
            # Check holdings information
            holdings = doc.get("holdings", [])
            for holding in holdings:
                # Extract location information
                location_info = holding.get("location", {})
                if location_info:
                    location_name = location_info.get("mainLocation", "Unknown")
                    if location_name not in availability["locations"]:
                        availability["locations"].append(location_name)
                
                # Check availability status
                items = holding.get("items", [])
                for item in items:
                    if item.get("availability") == "available":
                        availability["physical_copies"] += 1
                        availability["available"] = True
            
            return availability
            
        except Exception as e:
            return {
                "available": False,
                "locations": [],
                "online_access": False,
                "physical_copies": 0,
                "error": f"Could not determine availability: {str(e)}"
            }
    
    def _extract_links(self, delivery: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract access links from delivery information"""
        try:
            links = []
            link_data = delivery.get("link", [])
            
            for link in link_data:
                if isinstance(link, dict):
                    link_info = {
                        "url": link.get("linkURL", ""),
                        "display_label": link.get("displayLabel", "Access Resource"),
                        "link_type": link.get("linkType", "unknown")
                    }
                    if link_info["url"]:
                        links.append(link_info)
            
            return links
            
        except Exception:
            return []
    
    def _determine_availability_status(self, primo_result: Dict[str, Any]) -> str:
        """Determine availability status from Primo result for frontend"""
        availability_info = primo_result.get('availability', {})
        if availability_info.get('available', False):
            return "available"
        elif availability_info.get('online_access', False):
            return "available"
        else:
            return "unavailable"
    
    def _extract_location_info(self, primo_result: Dict[str, Any]) -> str:
        """Extract location information from Primo result"""
        availability_info = primo_result.get('availability', {})
        locations = availability_info.get('locations', [])
        if locations:
            return locations[0]
        elif availability_info.get('online_access', False):
            return "Online"
        else:
            return "Unknown"
    
    def _extract_access_link(self, primo_result: Dict[str, Any]) -> str:
        """Extract access link from Primo result"""
        links = primo_result.get('links', [])
        if links and len(links) > 0:
            return links[0].get('url', '#')
        else:
            return '#'  # Placeholder link

# Convenience functions
async def check_primo_availability(title: str, author: str = None, api_base_url: str = None, api_key: str = None, vid: str = None) -> Dict[str, Any]:
    """
    Check if a title is available in Primo
    
    Args:
        title: Title to search for
        author: Optional author name
        api_base_url: Optional Primo API base URL
        api_key: Optional API key
        vid: Optional view ID
        
    Returns:
        Dictionary with availability information
    """
    async with PrimoAPIClient(api_base_url, api_key, vid) as client:
        return await client._search_single_item(title, author)

async def check_metadata_availability(metadata: Dict[str, Any], api_base_url: str = None, api_key: str = None, vid: str = None) -> Dict[str, Any]:
    """
    Check availability of reading materials from extracted metadata
    
    Args:
        metadata: Extracted syllabus metadata
        api_base_url: Optional Primo API base URL
        api_key: Optional API key
        vid: Optional view ID
        
    Returns:
        Dictionary with availability information for all reading materials
    """
    async with PrimoAPIClient(api_base_url, api_key, vid) as client:
        return await client.search_by_metadata(metadata)

# Batch processing function
async def check_multiple_metadata(metadata_list: List[Dict[str, Any]], api_base_url: str = None, api_key: str = None, vid: str = None) -> List[Dict[str, Any]]:
    """
    Check multiple syllabi metadata in batch
    
    Args:
        metadata_list: List of extracted metadata dictionaries
        api_base_url: Optional Primo API base URL
        api_key: Optional API key
        vid: Optional view ID
        
    Returns:
        List of dictionaries with availability information
    """
    async with PrimoAPIClient(api_base_url, api_key, vid) as client:
        tasks = []
        for metadata in metadata_list:
            tasks.append(client.search_by_metadata(metadata))
        
        return await asyncio.gather(*tasks)

# Example usage and testing
async def test_primo_integration():
    """Test function for Primo integration"""
    # Test with sample metadata
    test_metadata = {
        "class_name": "Introduction to Psychology",
        "instructor": "Dr. Smith",
        "reading_materials": [
            {
                "title": "Psychology: The Science of Mind and Behaviour",
                "creator": "Passer",
                "requirement": "required"
            },
            "Introduction to Psychology by Myers",
            "Cognitive Psychology by Sternberg"
        ]
    }
    
    print("Testing Primo Search API integration...")
    
    result = await check_metadata_availability(test_metadata)
    print(f"\nSearch completed for {result.get('total_materials', 0)} materials")
    print(f"Found {result.get('found_materials', 0)} materials in library")
    
    if result.get('found'):
        for item_result in result.get('results', []):
            if item_result.get('found'):
                print(f"\n✓ Found: {item_result.get('title')}")
                for resource in item_result.get('results', []):
                    print(f"  - {resource.get('title')} by {resource.get('creator')}")
                    print(f"    Type: {resource.get('type')}, Available: {resource.get('availability', {}).get('available', False)}")
            else:
                print(f"\n✗ Not found: {item_result.get('title')} - {item_result.get('error', 'No results')}")

if __name__ == "__main__":
    asyncio.run(test_primo_integration())

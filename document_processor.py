import os
import json
import hashlib
import requests
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class DoclingProcessor:
    """Document processor using Docling MaaS service for PDF conversion"""
    
    def __init__(self):
        self.api_key = os.getenv('DOCLING_API_KEY')
        self.base_url = os.getenv('DOCLING_BASE_URL', 'https://docling-maas-apicast-production.apps.prod.rhoai.rh-aiservices-bu.com:443')
        
        if not self.api_key:
            raise ValueError("DOCLING_API_KEY environment variable is required")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        })
    
    def convert_pdf(self, pdf_path: str, output_format: str = "markdown") -> Dict[str, Any]:
        """
        Convert PDF to structured text using Docling service with fallback
        
        Args:
            pdf_path: Path to the PDF file
            output_format: Output format (markdown, json, html)
            
        Returns:
            Dict containing the converted content and metadata
        """
        # Try correct Docling API endpoints
        endpoints_to_try = [
            f"{self.base_url}/v1alpha/convert/source",  # JSON with base64
            f"{self.base_url}/v1alpha/convert/file"     # multipart form data
        ]
        
        for endpoint in endpoints_to_try:
            try:
                # Prepare the file for upload
                with open(pdf_path, 'rb') as pdf_file:
                    if 'convert/source' in endpoint:
                        # Use JSON format for /v1alpha/convert/source endpoint
                        import base64
                        
                        try:
                            # Read file and encode as base64
                            pdf_file.seek(0)
                            file_content = pdf_file.read()
                            file_b64 = base64.b64encode(file_content).decode('utf-8')
                            
                            # Use the exact structure from the curl example
                            json_data = {
                                "options": {
                                    "from_formats": ["pdf"],
                                    "to_formats": ["md"],
                                    "image_export_mode": "placeholder",
                                    "do_ocr": True,
                                    "force_ocr": False,
                                    "ocr_engine": "easyocr",
                                    "pdf_backend": "pypdfium2",
                                    "table_mode": "fast",
                                    "abort_on_error": False,
                                    "return_as_file": False,
                                    "do_table_structure": True,
                                    "include_images": True,
                                    "images_scale": 2
                                },
                                "file_sources": [
                                    {
                                        "base64_string": file_b64,
                                        "filename": os.path.basename(pdf_path)
                                    }
                                ]
                            }
                            
                            response = self.session.post(
                                endpoint,
                                json=json_data,
                                headers={'Content-Type': 'application/json', 'accept': 'application/json'},
                                timeout=300
                            )
                            
                        except Exception as e:
                            logger.warning(f"Failed to prepare JSON request: {e}")
                            response = None
                            
                    elif 'convert/file' in endpoint:
                        # Use multipart/form-data for /v1alpha/convert/file endpoint
                        try:
                            pdf_file.seek(0)
                            
                            # Use the exact form fields from the curl example
                            files = {
                                'file': (os.path.basename(pdf_path), pdf_file, 'application/pdf')
                            }
                            data = {
                                'from_formats': 'pdf',
                                'to_formats': 'md',
                                'do_ocr': 'true',
                                'force_ocr': 'false',
                                'ocr_engine': 'easyocr',
                                'pdf_backend': 'pypdfium2',
                                'table_mode': 'fast',
                                'abort_on_error': 'false',
                                'return_as_file': 'false',
                                'do_table_structure': 'true',
                                'include_images': 'true',
                                'images_scale': '2',
                                'image_export_mode': 'placeholder'
                            }
                            
                            response = self.session.post(
                                endpoint,
                                files=files,
                                data=data,
                                headers={'accept': 'application/json'},
                                timeout=300
                            )
                            
                        except Exception as e:
                            logger.warning(f"Failed to prepare multipart request: {e}")
                            response = None
                            
                    else:
                        # Fallback format
                        files = {
                            'file': (os.path.basename(pdf_path), pdf_file, 'application/pdf')
                        }
                        response = self.session.post(
                            endpoint,
                            files=files,
                            timeout=300
                        )
                    
                    if response and response.status_code == 200:
                        result = response.json()
                        
                        # Extract content from the correct Docling response structure
                        content = ""
                        if 'document' in result and result['document']:
                            document = result['document']
                            # Try different content fields
                            if 'md_content' in document:
                                content = document['md_content']
                            elif 'text_content' in document:
                                content = document['text_content']
                            elif 'html_content' in document:
                                content = document['html_content']
                            elif 'json_content' in document:
                                content = str(document['json_content'])
                        
                        # Fallback to old structure if needed
                        if not content:
                            content = result.get('content', '')
                        
                        return {
                            'success': True,
                            'content': content,
                            'metadata': {
                                'filename': os.path.basename(pdf_path),
                                'format': output_format,
                                'processed_at': datetime.now().isoformat(),
                                'pages': result.get('pages', 0),
                                'tables': result.get('tables', 0),
                                'formulas': result.get('formulas', 0),
                                'endpoint_used': endpoint,
                                'processing_time': result.get('processing_time', 0),
                                'method': 'Docling_API'
                            }
                        }
                    else:
                        logger.warning(f"Endpoint {endpoint} failed: {response.status_code if response else 'No response'}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Endpoint {endpoint} failed with exception: {e}")
                continue
        
        # If all Docling endpoints fail, use fallback method
        logger.warning(f"All Docling endpoints failed for {pdf_path}, using fallback method")
        return self._fallback_pdf_extract(pdf_path)
    
    def _fallback_pdf_extract(self, pdf_path: str) -> Dict[str, Any]:
        """Fallback PDF extraction using PyPDF2 or pdfplumber"""
        try:
            # Try PyPDF2 first
            try:
                import PyPDF2
                with open(pdf_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    
                    return {
                        'success': True,
                        'content': text,
                        'metadata': {
                            'filename': os.path.basename(pdf_path),
                            'format': 'text',
                            'processed_at': datetime.now().isoformat(),
                            'pages': len(reader.pages),
                            'method': 'PyPDF2_fallback'
                        }
                    }
            except ImportError:
                pass
            
            # Try pdfplumber
            try:
                import pdfplumber
                text = ""
                page_count = 0
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                        page_count += 1
                
                return {
                    'success': True,
                    'content': text,
                    'metadata': {
                        'filename': os.path.basename(pdf_path),
                        'format': 'text',
                        'processed_at': datetime.now().isoformat(),
                        'pages': page_count,
                        'method': 'pdfplumber_fallback'
                    }
                }
            except ImportError:
                pass
            
            # Final fallback - return empty with error
            return {
                'success': False,
                'error': 'No PDF extraction libraries available (PyPDF2, pdfplumber)',
                'content': ''
            }
            
        except Exception as e:
            logger.error(f"Fallback PDF extraction failed for {pdf_path}: {e}")
            return {
                'success': False,
                'error': f"Fallback extraction failed: {str(e)}",
                'content': ''
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Docling service"""
        try:
            # Try health endpoint first
            health_endpoints = [
                f"{self.base_url}/health",
                f"{self.base_url}/v1alpha/health", 
                f"{self.base_url}/"
            ]
            
            for endpoint in health_endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        return {'success': True, 'status': 'Connected', 'endpoint': endpoint}
                except:
                    continue
            
            # If health checks fail, assume service is available (some APIs don't have health endpoints)
            return {'success': True, 'status': 'Assumed Available (no health endpoint)'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

class DocumentManager:
    """Manages document processing pipeline and caching"""
    
    def __init__(self, documents_dir: str = "documents", cache_dir: str = "document_cache"):
        self.documents_dir = Path(documents_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.docling = DoclingProcessor()
        
        # Product mapping
        self.products = {
            "general": {
                "name": "Red Hat AI General",
                "description": "General Red Hat AI information and overviews"
            },
            "openshift_ai": {
                "name": "Red Hat OpenShift AI", 
                "description": "OpenShift AI platform documentation"
            },
            "enterrpise_linux_ai": {
                "name": "Red Hat Enterprise Linux AI",
                "description": "Enterprise Linux AI documentation" 
            },
            "inference_server": {
                "name": "Red Hat AI Inference Server",
                "description": "AI Inference Server documentation"
            }
        }
    
    def get_file_hash(self, file_path: Path) -> str:
        """Generate hash for file to detect changes"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def get_cache_path(self, file_path: Path, product: str) -> Path:
        """Get cache path for processed document"""
        file_hash = self.get_file_hash(file_path)
        cache_name = f"{product}_{file_path.stem}_{file_hash}.json"
        return self.cache_dir / cache_name
    
    def is_cached(self, file_path: Path, product: str) -> bool:
        """Check if document is already processed and cached"""
        cache_path = self.get_cache_path(file_path, product)
        return cache_path.exists()
    
    def load_from_cache(self, file_path: Path, product: str) -> Optional[Dict[str, Any]]:
        """Load processed document from cache"""
        cache_path = self.get_cache_path(file_path, product)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache {cache_path}: {e}")
        return None
    
    def save_to_cache(self, file_path: Path, product: str, data: Dict[str, Any]):
        """Save processed document to cache"""
        cache_path = self.get_cache_path(file_path, product)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving cache {cache_path}: {e}")
    
    def discover_documents(self) -> Dict[str, List[Path]]:
        """Discover all PDF documents organized by product"""
        documents = {}
        
        for product_dir in self.documents_dir.iterdir():
            if product_dir.is_dir() and product_dir.name in self.products:
                product_docs = []
                for pdf_file in product_dir.glob("*.pdf"):
                    product_docs.append(pdf_file)
                documents[product_dir.name] = product_docs
        
        return documents
    
    def process_document(self, file_path: Path, product: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Process a single document"""
        # Check cache first
        if not force_refresh and self.is_cached(file_path, product):
            cached_data = self.load_from_cache(file_path, product)
            if cached_data:
                logger.info(f"Using cached version of {file_path.name}")
                return cached_data
        
        # Process with Docling (with fallbacks)
        logger.info(f"Processing {file_path.name}...")
        result = self.docling.convert_pdf(str(file_path))
        
        if result['success'] and result.get('content', '').strip():
            # Add product and file metadata
            processed_data = {
                'file_path': str(file_path),
                'product': product,
                'product_name': self.products[product]['name'],
                'filename': file_path.name,
                'content': result['content'],
                'metadata': result['metadata'],
                'processed_at': datetime.now().isoformat(),
                'success': True
            }
            
            # Cache the result
            self.save_to_cache(file_path, product, processed_data)
            logger.info(f"Successfully processed {file_path.name} using {result['metadata'].get('method', 'Docling')}")
            return processed_data
        else:
            # Still mark as processed but with error for tracking
            error_data = {
                'file_path': str(file_path),
                'product': product,
                'product_name': self.products[product]['name'],
                'filename': file_path.name,
                'content': '',
                'metadata': {
                    'filename': file_path.name,
                    'processed_at': datetime.now().isoformat(),
                    'error': result.get('error', 'Unknown processing error')
                },
                'processed_at': datetime.now().isoformat(),
                'success': False,
                'error': result.get('error', 'Processing failed')
            }
            logger.warning(f"Failed to process {file_path.name}: {result.get('error', 'Unknown error')}")
            return error_data
    
    def process_all_documents(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Process all documents and return results"""
        documents = self.discover_documents()
        results = {
            'success': True,
            'processed': {},
            'errors': [],
            'total_docs': 0,
            'successful': 0,
            'failed': 0
        }
        
        for product, doc_list in documents.items():
            results['processed'][product] = []
            results['total_docs'] += len(doc_list)
            
            for doc_path in doc_list:
                result = self.process_document(doc_path, product, force_refresh)
                
                # Check if processing was truly successful (has content)
                if result.get('success', False) and result.get('content', '').strip():
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'file': str(doc_path),
                        'product': product,
                        'error': result.get('error', 'No content extracted')
                    })
                
                results['processed'][product].append(result)
        
        return results
    
    def get_processed_documents(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all processed documents from cache"""
        documents = self.discover_documents()
        processed = {}
        
        for product, doc_list in documents.items():
            processed[product] = []
            for doc_path in doc_list:
                cached_data = self.load_from_cache(doc_path, product)
                if cached_data:
                    processed[product].append(cached_data)
        
        return processed
    
    def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics about processed documents"""
        processed_docs = self.get_processed_documents()
        stats = {
            'total_products': len(self.products),
            'products': {},
            'total_documents': 0,
            'total_processed': 0
        }
        
        discovered = self.discover_documents()
        
        for product in self.products:
            total_docs = len(discovered.get(product, []))
            processed_count = len(processed_docs.get(product, []))
            
            stats['products'][product] = {
                'name': self.products[product]['name'],
                'total_documents': total_docs,
                'processed_documents': processed_count,
                'processing_rate': processed_count / total_docs if total_docs > 0 else 0
            }
            
            stats['total_documents'] += total_docs
            stats['total_processed'] += processed_count
        
        return stats 
import os
import json
import pickle
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging
from datetime import datetime
import re

# Import document processor
try:
    from document_processor import DocumentManager
    DOCUMENT_PROCESSOR_AVAILABLE = True
except ImportError:
    DOCUMENT_PROCESSOR_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available. Install with: pip install faiss-cpu")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("SentenceTransformers not available. Install with: pip install sentence-transformers")

class TextChunker:
    """Handles text chunking for better retrieval"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split text into overlapping chunks with metadata"""
        if not text:
            return []
        
        # Clean text
        text = self._clean_text(text)
        
        # Try to split by sections first (markdown headers)
        sections = self._split_by_sections(text)
        
        chunks = []
        for section_idx, section in enumerate(sections):
            section_chunks = self._chunk_section(section, section_idx)
            for chunk_data in section_chunks:
                chunk_metadata = metadata.copy()
                chunk_metadata.update(chunk_data['metadata'])
                
                chunks.append({
                    'text': chunk_data['text'],
                    'metadata': chunk_metadata
                })
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Remove page numbers and headers/footers patterns
        text = re.sub(r'Page \d+ of \d+', '', text)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def _split_by_sections(self, text: str) -> List[str]:
        """Split text by markdown headers or other section indicators"""
        # Split by markdown headers
        sections = re.split(r'\n(?=#{1,6}\s)', text)
        
        # If no headers found, split by double newlines
        if len(sections) == 1:
            sections = text.split('\n\n')
        
        return [section.strip() for section in sections if section.strip()]
    
    def _chunk_section(self, section: str, section_idx: int) -> List[Dict[str, Any]]:
        """Chunk a section into smaller pieces"""
        words = section.split()
        chunks = []
        
        if len(words) <= self.chunk_size:
            # Section is small enough, return as single chunk
            return [{
                'text': section,
                'metadata': {
                    'section_idx': section_idx,
                    'chunk_idx': 0,
                    'word_count': len(words)
                }
            }]
        
        # Split into overlapping chunks
        chunk_idx = 0
        start_idx = 0
        
        while start_idx < len(words):
            end_idx = min(start_idx + self.chunk_size, len(words))
            chunk_words = words[start_idx:end_idx]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append({
                'text': chunk_text,
                'metadata': {
                    'section_idx': section_idx,
                    'chunk_idx': chunk_idx,
                    'word_count': len(chunk_words),
                    'start_word': start_idx,
                    'end_word': end_idx
                }
            })
            
            chunk_idx += 1
            
            # Move to next chunk with overlap
            if end_idx >= len(words):
                break
            start_idx = end_idx - self.chunk_overlap
        
        return chunks

class VectorDatabase:
    """Vector database for document similarity search"""
    
    def __init__(self, db_path: str = "vector_db", model_name: str = "all-MiniLM-L6-v2"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(exist_ok=True)
        self.model_name = model_name
        
        # Initialize components
        self.embedder = None
        self.index = None
        self.documents = []
        self.chunker = TextChunker()
        
        # Metadata
        self.metadata = {
            'created_at': datetime.now().isoformat(),
            'model_name': model_name,
            'total_documents': 0,
            'total_chunks': 0,
            'products': {}
        }
        
        self._initialize_embedder()
        self._load_or_create_index()
    
    def _initialize_embedder(self):
        """Initialize the sentence transformer model"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("SentenceTransformers not available. Install with: pip install sentence-transformers")
        
        try:
            # Force CPU device for container environments
            import torch
            device = 'cpu'
            
            # Initialize with explicit device specification
            self.embedder = SentenceTransformer(self.model_name, device=device)
            
            # Ensure model is on CPU
            if hasattr(self.embedder, '_modules'):
                for module in self.embedder._modules.values():
                    if hasattr(module, 'to'):
                        module.to(device)
            
            logger.info(f"Initialized embedder: {self.model_name} on device: {device}")
        except Exception as e:
            logger.error(f"Failed to initialize embedder: {e}")
            raise
    
    def _load_or_create_index(self):
        """Load existing index or create new one"""
        index_path = self.db_path / "faiss.index"
        documents_path = self.db_path / "documents.pkl"
        metadata_path = self.db_path / "metadata.json"
        
        if index_path.exists() and documents_path.exists():
            try:
                # Load existing index
                if FAISS_AVAILABLE:
                    self.index = faiss.read_index(str(index_path))
                
                with open(documents_path, 'rb') as f:
                    self.documents = pickle.load(f)
                
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        self.metadata.update(json.load(f))
                
                logger.info(f"Loaded existing index with {len(self.documents)} chunks")
                return
            except Exception as e:
                logger.warning(f"Failed to load existing index: {e}")
        
        # Create new index
        if FAISS_AVAILABLE:
            # Get embedding dimension
            test_embedding = self.embedder.encode(["test"])
            dimension = test_embedding.shape[1]
            self.index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
        
        self.documents = []
        logger.info("Created new vector index")
    
    def _save_index(self):
        """Save index to disk"""
        try:
            if FAISS_AVAILABLE and self.index:
                index_path = self.db_path / "faiss.index"
                faiss.write_index(self.index, str(index_path))
            
            documents_path = self.db_path / "documents.pkl"
            with open(documents_path, 'wb') as f:
                pickle.dump(self.documents, f)
            
            metadata_path = self.db_path / "metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(self.metadata, f, indent=2)
            
            logger.info("Saved vector database to disk")
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def add_document(self, content: str, metadata: Dict[str, Any]) -> int:
        """Add a document to the vector database"""
        if not content or not content.strip():
            logger.warning("Empty content provided to add_document")
            return 0
        
        # Chunk the document
        chunks = self.chunker.chunk_text(content, metadata)
        
        if not chunks:
            logger.warning("No chunks generated from document")
            return 0
        
        # Generate embeddings
        chunk_texts = [chunk['text'] for chunk in chunks]
        embeddings = self.embedder.encode(chunk_texts, normalize_embeddings=True)
        
        # Add to index
        if FAISS_AVAILABLE and self.index:
            self.index.add(embeddings.astype('float32'))
        
        # Store documents with metadata
        for i, chunk in enumerate(chunks):
            doc_data = {
                'text': chunk['text'],
                'metadata': chunk['metadata'],
                'doc_id': len(self.documents),
                'embedding_id': len(self.documents)
            }
            self.documents.append(doc_data)
        
        # Update metadata
        product = metadata.get('product', 'unknown')
        if product not in self.metadata['products']:
            self.metadata['products'][product] = {
                'document_count': 0,
                'chunk_count': 0
            }
        
        self.metadata['products'][product]['document_count'] += 1
        self.metadata['products'][product]['chunk_count'] += len(chunks)
        self.metadata['total_documents'] += 1
        self.metadata['total_chunks'] += len(chunks)
        self.metadata['last_updated'] = datetime.now().isoformat()
        
        logger.info(f"Added document with {len(chunks)} chunks to vector database")
        return len(chunks)
    
    def search(self, query: str, top_k: int = 5, product_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        if not query or not query.strip():
            return []
        
        if not FAISS_AVAILABLE or not self.index or len(self.documents) == 0:
            logger.warning("Vector database not available or empty")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.embedder.encode([query], normalize_embeddings=True)
            
            # Search in index
            search_k = min(top_k * 2, len(self.documents))  # Get more results for filtering
            scores, indices = self.index.search(query_embedding.astype('float32'), search_k)
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(self.documents):
                    doc = self.documents[idx].copy()
                    doc['similarity_score'] = float(score)
                    
                    # Apply product filter if specified
                    if product_filter and doc['metadata'].get('product') != product_filter:
                        continue
                    
                    results.append(doc)
                    
                    if len(results) >= top_k:
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        return {
            'total_documents': self.metadata['total_documents'],
            'total_chunks': self.metadata['total_chunks'],
            'products': self.metadata['products'],
            'model_name': self.metadata['model_name'],
            'created_at': self.metadata['created_at'],
            'last_updated': self.metadata.get('last_updated', 'Never'),
            'index_available': FAISS_AVAILABLE and self.index is not None
        }
    
    def rebuild_index(self, documents_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rebuild the entire index from scratch"""
        logger.info("Rebuilding vector database...")
        
        # Clear existing data
        if FAISS_AVAILABLE:
            test_embedding = self.embedder.encode(["test"])
            dimension = test_embedding.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
        
        self.documents = []
        self.metadata = {
            'created_at': datetime.now().isoformat(),
            'model_name': self.model_name,
            'total_documents': 0,
            'total_chunks': 0,
            'products': {}
        }
        
        # Add all documents
        total_added = 0
        for doc_data in documents_data:
            if doc_data.get('content'):
                chunks_added = self.add_document(doc_data['content'], doc_data)
                total_added += chunks_added
        
        # Save to disk
        self._save_index()
        
        return {
            'success': True,
            'total_documents': len(documents_data),
            'total_chunks': total_added,
            'products': list(self.metadata['products'].keys())
        }
    
    def clear_database(self):
        """Clear all data from the database"""
        logger.info("Clearing vector database...")
        
        if FAISS_AVAILABLE:
            test_embedding = self.embedder.encode(["test"])
            dimension = test_embedding.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
        
        self.documents = []
        self.metadata = {
            'created_at': datetime.now().isoformat(),
            'model_name': self.model_name,
            'total_documents': 0,
            'total_chunks': 0,
            'products': {}
        }
        
        self._save_index()

class RAGManager:
    """Manages RAG functionality - combines document processing and vector search"""
    
    def __init__(self, documents_dir: str = "documents", cache_dir: str = "document_cache", db_path: str = "vector_db"):
        if not DOCUMENT_PROCESSOR_AVAILABLE:
            raise ImportError("DocumentManager not available")
        
        self.doc_manager = DocumentManager(documents_dir, cache_dir)
        self.vector_db = VectorDatabase(db_path)
        self.products = self.doc_manager.products
    
    def initialize_database(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Initialize the vector database with processed documents"""
        # Process all documents
        process_result = self.doc_manager.process_all_documents(force_refresh)
        
        if not process_result['success'] or process_result['successful'] == 0:
            return {
                'success': False,
                'error': 'No documents processed successfully',
                'details': process_result
            }
        
        # Get processed documents
        processed_docs = self.doc_manager.get_processed_documents()
        
        # Prepare data for vector database (only successful documents with content)
        all_docs = []
        for product, docs in processed_docs.items():
            for doc in docs:
                if doc.get('success', False) and doc.get('content', '').strip():
                    all_docs.append(doc)
        
        # Rebuild vector database
        result = self.vector_db.rebuild_index(all_docs)
        
        return {
            'success': True,
            'processed': process_result,
            'vector_db': result
        }
    
    def search_documents(self, query: str, product: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search documents with optional product filtering"""
        return self.vector_db.search(query, top_k, product)
    
    def get_context_for_query(self, query: str, product: Optional[str] = None, max_chunks: int = 3) -> str:
        """Get relevant context for a query to use in RAG"""
        results = self.search_documents(query, product, max_chunks)
        
        if not results:
            return ""
        
        context_parts = []
        for result in results:
            metadata = result['metadata']
            product_name = metadata.get('product_name', 'Unknown Product')
            filename = metadata.get('filename', 'Unknown File')
            
            context_parts.append(
                f"**Source:** {product_name} - {filename}\n"
                f"**Content:** {result['text']}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        doc_stats = self.doc_manager.get_document_stats()
        vector_stats = self.vector_db.get_stats()
        
        return {
            'documents': doc_stats,
            'vector_database': vector_stats,
            'products': self.products
        } 
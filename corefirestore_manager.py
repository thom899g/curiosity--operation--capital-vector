"""
Firebase Firestore Manager - Central Nervous System for Agent Colony
Handles all Firestore operations with robust error handling
"""
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import Client as FirestoreClient
from google.cloud.firestore_v1.document import DocumentReference
from typing import Dict, Any, Optional, List, Callable
import logging
import time
from datetime import datetime
import threading
from queue import Queue
import json

logger = logging.getLogger(__name__)

class FirestoreManager:
    """Singleton Firestore manager for agent coordination"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirestoreManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self._db: Optional[FirestoreClient] = None
            self._listeners: Dict[str, Any] = {}
            self._message_queue = Queue()
            self._is_connected = False
            self._connect_attempts = 0
            self._max_retries = 5
    
    def initialize(self, config) -> bool:
        """Initialize Firestore connection"""
        try:
            if not firebase_admin._apps:
                if config.firebase.credentials_path:
                    cred = credentials.Certificate(config.firebase.credentials_path)
                else:
                    cred = credentials.ApplicationDefault()
                
                firebase_admin.initialize_app(cred, {
                    'projectId': config.firebase.project_id
                })
            
            self._db = firestore.client()
            self._is_connected = True
            logger.info("Firestore connection established successfully")
            
            # Start message processor thread
            processor_thread = threading.Thread(
                target=self._process_message_queue,
                daemon=True,
                name="FirestoreProcessor"
            )
            processor_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Firestore initialization failed: {str(e)}")
            self._is_connected = False
            return False
    
    def _process_message_queue(self):
        """Background thread to process queued messages"""
        while True:
            try:
                message = self._message_queue.get()
                if message is None:  # Shutdown signal
                    break
                
                collection, data, callback = message
                self._write_with_retry(collection, data, callback)
                
            except Exception as e:
                logger.error(f"Message queue processing error: {str(e)}")
            finally:
                self._message_queue.task_done()
    
    def _write_with_retry(self, collection: str, data: Dict[str, Any], 
                         callback: Optional[Callable] = None):
        """Write with exponential backoff retry"""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                if not self._is_connected:
                    self._reconnect()
                
                doc_ref = self._db.collection(collection).document()
                data['created_at'] = firestore.SERVER_TIMESTAMP
                data['updated_at'] = firestore.SERVER_TIMESTAMP
                doc_ref.set(data)
                
                if callback:
                    callback(True, doc_ref.id)
                return
                
            except Exception as e:
                retry_count += 1
                wait_time = 2 ** retry_count
                logger.warning(f"Firestore write failed (attempt {retry_count}): {str(e)}")
                
                if retry_count < max_retries:
                    time.sleep(wait_time)
                else:
                    if callback:
                        callback(False, str(e))
                    break
    
    def _reconnect(self):
        """Attempt to reconnect to Firestore"""
        try:
            self._db = firestore.client()
            self._is_connected = True
            self._connect_attempts = 0
            logger.info("Firestore reconnection successful")
        except Exception as e:
            self._connect_attempts += 1
            logger.error(f"Firestore reconnection failed (attempt {self._connect_attempts}): {str(e)}")
            time.sleep(min(30, 2 ** self._connect_attempts))
    
    # Public API Methods
    
    def queue_message(self, collection: str, data: Dict[str, Any], 
                     callback: Optional[Callable] = None):
        """Queue a message for async processing"""
        if not self._is_connected:
            logger.warning("Firestore not connected, reconnecting...")
            self._reconnect()
        
        self._message_queue.put((collection, data, callback))
    
    def write_sync(self, collection: str, data: Dict[str, Any]) -> Optional[str]:
        """Synchronous write with immediate feedback"""
        try:
            if not self._is_connected:
                self._reconnect()
                if not self._is_connected:
                    raise ConnectionError("Firestore not available")
            
            doc_ref = self._db.collection(collection).document()
            data['created_at'] = firestore.SERVER_TIMESTAMP
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(data)
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Sync write failed: {str(e)}")
            return None
    
    def read_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Read a specific document"""
        try:
            if not self._is_connected:
                self._reconnect()
            
            doc_ref = self._db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
            
        except Exception as e:
            logger.error(f"Document read failed: {str(e)}")
            return None
    
    def query_collection(self, collection: str, 
                        filters: List[tuple] = None,
                        order_by: str = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        """Query collection with optional filters"""
        try:
            if not self._is_connected:
                self._reconnect()
            
            query = self._db.collection(collection)
            
            # Apply filters
            if filters:
                for field, op, value in filters:
                    query = query.where(field, op, value)
            
            # Apply ordering
            if order_by:
                query = query.order_by(order_by)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            results = []
            docs = query.stream()
            
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                results.append(data)
            
            return results
            
        except Exception as e:
            logger.error(f"Collection query failed: {str(e)}")
            return []
    
    def start_listener(self, collection: str, callback: Callable):
        """Start real-time listener on collection"""
        try:
            if not self._is_connected:
                self._reconnect()
            
            def on_snapshot(col_snapshot, changes, read_time):
                try:
                    for change in changes:
                        if change.type.name == 'ADDED':
                            doc_data = change.document.to_dict()
                            doc_data['id'] = change.document.id
                            callback('ADDED', doc_data)
                        elif change.type.name == 'MODIFIED':
                            doc_data = change.document.to_dict()
                            doc_data['id'] = change.document.id
                            callback('MODIFIED', doc_data)
                            
                except Exception as e:
                    logger.error(f"Listener callback error: {str(e)}")
            
            listener = self._db.collection(collection).on_snapshot(on_snapshot)
            self._listeners[collection] = listener
            logger.info(f"Started listener on collection: {collection}")
            
        except Exception as e:
            logger.error(f"Failed to start listener: {str(e)}")
    
    def stop_listener(self, collection: str):
        """Stop a specific listener"""
        if collection in self._listeners:
            self._listeners[collection]()
            del self._listeners[collection]
            logger.info(f"Stopped listener on collection: {collection}")
    
    def cleanup(self):
        """Cleanup resources"""
        # Stop all listeners
        for collection in list(self._listeners.keys()):
            self.stop_listener(collection)
        
        # Signal message processor to shutdown
        self._message_queue.put(None)
        
        logger.info("Firestore manager cleanup completed")
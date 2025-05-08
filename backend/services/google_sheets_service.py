"""
Google Sheets service for WellcomeAI application.
Handles logging to Google Sheets.
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

# Google API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

from backend.core.logging import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

# Path to service account file
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   'voiceai-459203-07959c3b9494.json')

class GoogleSheetsService:
    """Service for working with Google Sheets"""
    
    @staticmethod
    def _get_sheets_service():
        """
        Creates and returns an authenticated Google Sheets service
        
        Returns:
            Google Sheets service object
        """
        try:
            # Load credentials from service account file
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Build the service
            service = build('sheets', 'v4', credentials=credentials)
            return service
        except Exception as e:
            logger.error(f"Error creating Google Sheets service: {str(e)}")
            return None
    
    @staticmethod
    async def log_conversation(
        sheet_id: str,
        user_message: str,
        assistant_message: str,
        function_result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log conversation to Google Sheet
        
        Args:
            sheet_id: Google Sheet ID
            user_message: User message
            assistant_message: Assistant response
            function_result: Result of function execution (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not sheet_id:
            logger.warning("No sheet_id provided for logging")
            return False
        
        try:
            # Prepare values to append
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Prepare function result text
            function_text = "none"
            if function_result:
                try:
                    # Convert to string if dict or other complex type
                    if isinstance(function_result, dict):
                        function_text = json.dumps(function_result, ensure_ascii=False)
                    else:
                        function_text = str(function_result)
                except Exception as e:
                    logger.error(f"Error formatting function result: {str(e)}")
                    function_text = f"Error formatting result: {str(e)}"
            
            # Values row
            values = [[now, user_message, assistant_message, function_text]]
            
            # Create a loop to run the synchronous API call in a thread pool
            loop = asyncio.get_event_loop()
            
            # Run the synchronous API call in a thread pool
            result = await loop.run_in_executor(
                None,
                lambda: GoogleSheetsService._append_values(sheet_id, values)
            )
            
            return result
                        
        except Exception as e:
            logger.error(f"Error logging conversation to Google Sheet: {str(e)}")
            return False
    
    @staticmethod
    def _append_values(sheet_id, values):
        """
        Append values to a sheet using the Google API client
        
        Args:
            sheet_id: Google Sheet ID
            values: Values to append
            
        Returns:
            True if successful, False otherwise
        """
        try:
            service = GoogleSheetsService._get_sheets_service()
            if not service:
                return False
                
            body = {
                'values': values
            }
            
            result = service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range='A:D',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(f"Successfully logged conversation to Google Sheet: {sheet_id}")
            return True
        except HttpError as e:
            logger.error(f"Error appending values to sheet: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error appending values: {str(e)}")
            return False
    
    @staticmethod
    async def verify_sheet_access(sheet_id: str) -> Dict[str, Any]:
        """
        Verify access to Google Sheet
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            Dict with status and message
        """
        if not sheet_id:
            return {"success": False, "message": "No sheet ID provided"}
        
        try:
            # Run the synchronous API call in a thread pool
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(
                None,
                lambda: GoogleSheetsService._verify_sheet(sheet_id)
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error verifying Google Sheet access: {str(e)}")
            return {"success": False, "message": f"Error: {str(e)}"}

    @staticmethod
    def _verify_sheet(sheet_id):
        """
        Verify sheet access using the Google API client
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            Dict with verification results
        """
        try:
            service = GoogleSheetsService._get_sheets_service()
            if not service:
                return {"success": False, "message": "Failed to create Google Sheets service"}
                
            # Try to get sheet metadata to verify access
            sheet_metadata = service.spreadsheets().get(
                spreadsheetId=sheet_id,
                fields='properties.title'
            ).execute()
            
            title = sheet_metadata.get('properties', {}).get('title', 'Untitled Spreadsheet')
            return {
                "success": True, 
                "message": f"Successfully connected to Google Sheet: {title}",
                "title": title
            }
            
        except HttpError as e:
            error_message = f"Failed to access Google Sheet: {str(e)}"
            # Extract more details if available
            try:
                error_content = json.loads(e.content.decode())
                if 'error' in error_content and 'message' in error_content['error']:
                    error_message = error_content['error']['message']
            except:
                pass
            
            return {"success": False, "message": error_message}
            
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    @staticmethod
    async def setup_sheet(sheet_id: str) -> bool:
        """
        Set up sheet with headers if it's empty
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            True if successful, False otherwise
        """
        if not sheet_id:
            return False
            
        try:
            # Run the synchronous API call in a thread pool
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(
                None,
                lambda: GoogleSheetsService._setup_sheet_headers(sheet_id)
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error setting up Google Sheet: {str(e)}")
            return False
            
    @staticmethod
    def _setup_sheet_headers(sheet_id):
        """
        Set up sheet headers using the Google API client
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            service = GoogleSheetsService._get_sheets_service()
            if not service:
                return False
                
            # First check if headers already exist
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range='A1:D1'
            ).execute()
            
            values = result.get('values', [])
            
            # If no headers, add them
            if not values:
                headers = [['Дата и время', 'Пользователь', 'Ассистент', 'Результат функции']]
                
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range='A1:D1',
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                
                logger.info(f"Successfully set up headers in Google Sheet: {sheet_id}")
            
            return True
            
        except HttpError as e:
            logger.error(f"Error setting up sheet headers: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting up headers: {str(e)}")
            return False

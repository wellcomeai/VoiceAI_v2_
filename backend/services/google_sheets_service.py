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

from backend.core.logging import get_logger

logger = get_logger(__name__)

class GoogleSheetsService:
    """Service for working with Google Sheets"""
    
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
            values = [now, user_message, assistant_message, function_text]
            
            # Construct request URL
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A:D:append"
            
            # Use Google Sheets API v4 without authentication (works for public spreadsheets)
            # Note: This requires the spreadsheet to be accessible to "Anyone with the link" with "Editor" access
            async with aiohttp.ClientSession() as session:
                params = {
                    "valueInputOption": "RAW",
                    "insertDataOption": "INSERT_ROWS",
                }
                data = {
                    "values": [values]
                }
                
                async with session.post(url, params=params, json=data) as response:
                    if response.status == 200:
                        logger.info(f"Successfully logged conversation to Google Sheet: {sheet_id}")
                        return True
                    else:
                        try:
                            error_data = await response.json()
                            logger.error(f"Error logging to Google Sheet: {error_data}")
                        except:
                            logger.error(f"Error logging to Google Sheet: Status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error logging conversation to Google Sheet: {str(e)}")
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
            # Try to get sheet metadata to verify access
            async with aiohttp.ClientSession() as session:
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
                params = {
                    "fields": "properties/title"
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = data.get("properties", {}).get("title", "Untitled Spreadsheet")
                        return {
                            "success": True, 
                            "message": f"Successfully connected to Google Sheet: {title}",
                            "title": title
                        }
                    else:
                        error_msg = f"Failed to access Google Sheet: Status {response.status}"
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get("error", {}).get("message", error_msg)
                        except:
                            pass
                        
                        return {"success": False, "message": error_msg}
        except Exception as e:
            logger.error(f"Error verifying Google Sheet access: {str(e)}")
            return {"success": False, "message": f"Error: {str(e)}"}

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
            # Check if sheet has data
            async with aiohttp.ClientSession() as session:
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:D1"
                
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        values = data.get("values", [])
                        
                        # If no data or headers, add them
                        if not values:
                            # Set up headers
                            headers_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:D1"
                            headers_data = {
                                "values": [["Дата и время", "Пользователь", "Ассистент", "Результат функции"]]
                            }
                            params = {"valueInputOption": "RAW"}
                            
                            async with session.put(headers_url, params=params, json=headers_data) as headers_response:
                                if headers_response.status == 200:
                                    logger.info(f"Successfully set up headers in Google Sheet: {sheet_id}")
                                    return True
                                else:
                                    logger.error(f"Failed to set up headers: Status {headers_response.status}")
                                    return False
                        
                        return True
                    else:
                        logger.error(f"Failed to check sheet data: Status {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error setting up Google Sheet: {str(e)}")
            return False

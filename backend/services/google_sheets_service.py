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
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import google.auth.transport.aiohttp
import google.auth.transport.requests
import io

from backend.core.logging import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

# JSON содержимое сервисного аккаунта
SERVICE_ACCOUNT_INFO = {
  "type": "service_account",
  "project_id": "voiceai-459203",
  "private_key_id": "07959c3b94944dae0e4c55b1061ed23c25beba54",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDU0jZFLYu/bKj5\nG9F5xjdxm9oxR80Zmdzr0+8I9aAwbC+wBFnBgqojp4PbfhGB/ZYiyHcw1UdtfI0u\nyS2S/J6GX5IBtuJ0r1nQCpLP+u5vzD9nTrHdgx5b0fLtkzbeh9H+WdRwTNMZlPB2\nGOnpHZU8mhu1cK526lYFXt7yZTcm6qCVyrDKJCAlxsk8gcGfxKey971J4+5Izbsg\nniX/d044ct2z6uo8lgR5LA2D/B3BhGDevjNxxWO6wWAIr6ff6Srwwaoj8JXc5PeH\nY71A+fILZ5LUgO9cDgT/FK+cE4EOIPgBvIOzzwnkijxH3/nyCQ7CmoUtd9AzWk83\npQNdG8zfAgMBAAECggEABR1kjW+JQOW+ax5CMQhF6IuMNHOdn4W8riC/DkI4/TXc\na9nu6pxMtPfkdiX/WgeC0Di7oiTRx0PacMtDIvxMNr3sCaLRbxlpALaxkm/m/jDc\nAsdLjm5n/LAGvu5ahMah9HW+sVCOvpKmuIOVFDOo43a+P25ljN4X/trk2gyssWzb\nPbP8FufReBEn3Bosx5FdVoIs3VSiIv9Ll3/QAiDrgmidyvHidQEYiFNeKwZIr9Ta\na7lKpDClbon2nhRZFPQIVwRr5CZJJgOFM+zCTQUsToYS7qZinGbr6iZePYXYJWSW\n8Q8g7roECyUlRjHTca6Dr4HTu3AOAcR1oVrgOTzkQQKBgQDpw4+BRhdKbY8IZIy8\n0Wv/I8PqC5nPoH+8PDNnoRScZV7LkoVeE7ShtrwWN8NeR45D1M2c8kASbN2t+HNC\niEI/cY4XnIWU+d8CeXloEv4cAsdp75IAXrmoN1EhB8IfT8hKa/pcjGr32A4PWZ+u\nF/gS2oTR/NPG6lXTNem3a7ydJwKBgQDpEKtQ8+MQ2Yw7UCZil1ZPkAgeVpnSZw8p\npYBgvCcqtQ1WNw2nC6W5cgmw2GAnDYo582HTXoe0WyPrkVRJbOzSy+SIyMbpFV/a\nI6abmrDBepxsI8gSMYpr6L/XwunKVoGuhGspjYggnOuHdJ+mDKhxAD5hqyY6GUHk\n7rIWnSyViQKBgB6UO2iAv7k3vbcuWA63InZ8ujsai2NSroL0KRFMTALta8obf6C/\n2SgyXEZXwxHJMH4FD2SRd/oxDYqdbo5sfqYH97t0+TB0w0xykYQgv+bwIh/ke+fa\nfFTZ753vguBPsnaxy01h/Pgw5h3x7mZ6sjPdK/TAKv/hVZrMeadJy6GPAoGAEA9Z\n/sYPi4WyKBQp0PlktS7ToGOPTfRUEyaYZhIRENxRAvPgOPaQgOreyBTg60//ima/\nAvWsnDz7iKwHBtg+qXfrU5GiQ0V5yWpTfL14GJz+UmVU0Awh4bW0IoYH3i1/2iq9\nx6s9CiJGCJt8tNCCeubtZYWJqM88vy3Dj9Nc0yECgYARtflxSPhwHnMreWXvkFWt\nPEd+HjXiiP+LQ3vvWbvGaTsip28clEWLQICxUez1dIAgU/fdMVh6DMyL6+Kwaqja\nOnjJ0lNsXEX/pxJuejxP11gWa6aZYYpCRdiwHcEFDaONmq2LqgeSN2MTwli+8yiq\nS/pDQHZCnzu8JpC/ofrh3g==\n-----END PRIVATE KEY-----\n",
  "client_email": "voiceai@voiceai-459203.iam.gserviceaccount.com",
  "client_id": "113806588169949164285",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/voiceai%40voiceai-459203.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

class GoogleSheetsService:
    """Service for working with Google Sheets"""
    
    @staticmethod
    async def _get_auth_headers():
        """
        Получить заголовки авторизации для использования с сервисным аккаунтом
        
        Returns:
            Dict с заголовками авторизации
        """
        try:
            # Загружаем учетные данные напрямую из JSON-строки вместо файла
            credentials = service_account.Credentials.from_service_account_info(
                SERVICE_ACCOUNT_INFO,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Создаем транспорт для обновления токена
            request = google.auth.transport.requests.Request()
            
            # Убедимся, что токен действителен
            credentials.refresh(request)
            
            # Получаем токен
            token = credentials.token
            
            # Возвращаем заголовки авторизации
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Error generating auth headers: {str(e)}")
            raise Exception(f"Auth error: {str(e)}")
    
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
            
            # Получаем заголовки авторизации
            headers = await GoogleSheetsService._get_auth_headers()
            
            # Используем Google Sheets API с аутентификацией сервисного аккаунта
            async with aiohttp.ClientSession() as session:
                params = {
                    "valueInputOption": "RAW",
                    "insertDataOption": "INSERT_ROWS",
                }
                data = {
                    "values": [values]
                }
                
                async with session.post(url, params=params, json=data, headers=headers) as response:
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
            # Получаем заголовки авторизации
            headers = await GoogleSheetsService._get_auth_headers()
            
            # Try to get sheet metadata to verify access
            async with aiohttp.ClientSession() as session:
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
                params = {
                    "fields": "properties/title"
                }
                
                async with session.get(url, params=params, headers=headers) as response:
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
            # Получаем заголовки авторизации
            headers = await GoogleSheetsService._get_auth_headers()
            
            # Check if sheet has data
            async with aiohttp.ClientSession() as session:
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:D1"
                
                async with session.get(url, headers=headers) as response:
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
                            
                            async with session.put(headers_url, params=params, json=headers_data, headers=headers) as headers_response:
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

import openai
from app.config import settings
from app.schemas import ChatRequest, ChatResponse, ChatMessage
from typing import List
import json

class ChatService:
    def __init__(self):
        if settings.openai_api_key:
            openai.api_key = settings.openai_api_key
    
    def process_message(self, request: ChatRequest) -> ChatResponse:
        # Simple rule-based responses for demo purposes
        # In production, you'd use OpenAI API or another LLM
        
        user_message = request.message.lower()
        
        if any(keyword in user_message for keyword in ["po", "purchase order"]):
            reply = "Purchase orders are tracked with cap, utilization, vendor, and expiry metadata. You can review PO balances on the dashboard or open the document detail page for more context."
        elif "invoice" in user_message:
            reply = "Invoices are matched against their linked PO. Validation ensures amounts stay within the PO cap and alerts trigger if mismatches appear."
        elif any(keyword in user_message for keyword in ["agreement", "contract"]):
            reply = "Service agreements store vendor relationships, expiry dates, and linked PO versions. The system raises alerts 30 days before expiration."
        elif any(keyword in user_message for keyword in ["alert", "notification"]):
            reply = "Alerts fire when PO utilization crosses thresholds, invoices fail validation, or agreements near expiration. Manage rules in the Alerts view."
        elif any(keyword in user_message for keyword in ["chatbot", "assistant"]):
            reply = "I'm the DMS assistant. Ask about PO balances, upcoming expiries, or document summaries and I'll point you to the right dashboard modules."
        else:
            reply = "I can help you with purchase orders, invoices, service agreements, and alerts. What would you like to know about?"
        
        return ChatResponse(reply=reply)
    
    def process_message_with_openai(self, request: ChatRequest) -> ChatResponse:
        """Process message using OpenAI API (requires API key)"""
        if not settings.openai_api_key:
            return self.process_message(request)
        
        try:
            # Prepare messages for OpenAI
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are the DMS Assistant — an expert on this Document Management System. "
                        "Answer only from the facts below. Be concise.\n\n"
                        "ALERTS: Alerts are auto-generated when a document is uploaded and processed. "
                        "Rules: (1) Invoice not linked to any PO → warning. "
                        "(2) Invoice amount exceeds PO remaining balance → critical. "
                        "(3) Vendor/client/currency mismatch between invoice and PO → critical. "
                        "(4) PO utilization ≥ 80% of total value → warning; ≥ 95% → critical. "
                        "(5) Service Agreement expiring within 30 days → warning; already expired → critical. "
                        "(6) PO or invoice date falls outside the linked contract validity period → warning. "
                        "Alerts are ordered: unacknowledged first, then critical → warning → info, newest first.\n\n"
                        "PURCHASE ORDERS: Two types — Client PO (revenue, billable to client) and Vendor PO (cost, paid to vendor). "
                        "PO utilization = total invoiced / PO amount. Remaining balance = PO amount − total invoiced. "
                        "Each Vendor PO maps to a Client PO via a POAllocation (margin tracking).\n\n"
                        "INVOICES: Vendor Invoices link to Vendor POs; Client Invoices link to Client POs. "
                        "Matching checks: amount within PO balance, vendor name, currency, date within contract period. "
                        "Overbilling detected when sum of invoices exceeds PO allocated value.\n\n"
                        "SERVICE AGREEMENTS: Govern one or more POs. Store start/end dates. "
                        "System alerts 30 days before expiry and flags linked POs/invoices that fall outside the contract period.\n\n"
                        "DOCUMENT PROCESSING: PDFs are uploaded → AWS Textract extracts fields → classified into category → "
                        "financial records created → alerts generated automatically. "
                        "A background scheduler re-links documents every 60 seconds to catch out-of-order uploads.\n\n"
                        "CLIENT MANAGEMENT: Client Overview shows Client POs, invoices, and linked Vendor POs per client. "
                        "Documents can be manually assigned to clients. Client names can be renamed across all records."
                    )
                }
            ]
            
            # Add context if provided
            if request.context:
                for msg in request.context:
                    messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
            
            # Add current message
            messages.append({
                "role": "user",
                "content": request.message
            })
            
            # Call OpenAI API
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            reply = response.choices[0].message.content
            return ChatResponse(reply=reply)
            
        except Exception as e:
            # Fallback to rule-based response
            return self.process_message(request)

"""
api/chatbot.py
LLM-powered City Manager that answers questions about live traffic state.
"""
from __future__ import annotations

import os
import json
from loguru import logger

class CityManagerChatbot:
    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.enabled = False
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                self.enabled = True
                logger.info("City Manager Chatbot initialized with Gemini API.")
            except ImportError:
                logger.warning("google-genai not installed. Chatbot will use Mock responses.")
        else:
            logger.info("GEMINI_API_KEY not found. Chatbot will use Mock responses.")

    def chat(self, user_message: str, network_state: dict) -> str:
        state_str = json.dumps(network_state, indent=2)
        
        prompt = f"""
You are the AI City Manager for a smart traffic intelligence system.
Answer the user's query based ONLY on the current live network state provided below.
Keep your response concise, professional, and helpful (max 3-4 sentences).

Live Network State:
{state_str}

User Query: {user_message}
"""
        
        if self.enabled:
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                logger.error(f"Gemini API error: {e}")
                return "I'm currently experiencing communication issues with my cloud backend, but I am still actively monitoring the intersections locally."
        
        # Mock Fallback responses if no API key is provided
        msg = user_message.lower()
        num_ints = len(network_state.get('intersections', []))
        accidents = network_state.get('accidents', [])
        
        if "accident" in msg:
            if accidents:
                return f"Yes, there are {len(accidents)} active accidents. The emergency agents have already overridden the signals to ALL_RED."
            else:
                return "There are currently no active accidents in the network."
        elif "congestion" in msg or "traffic" in msg:
            return f"I am monitoring {num_ints} intersections. The adaptive controllers are currently running dynamic Webster's splits to manage queue lengths."
        else:
            return f"I am the City Manager AI. The network is active with {num_ints} intersections connected. How can I help you optimize flow today?"

# Singleton
chatbot = CityManagerChatbot()

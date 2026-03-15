"""
Gradio Web Interface for Boston School Chatbot

This script creates a web interface for your chatbot using Gradio.
You only need to implement the chat function.

Key Features:
- Creates a web UI for your chatbot
- Handles conversation history
- Provides example questions
- Can be deployed to Hugging Face Spaces

Example Usage:
    # Run locally:
    python app.py
    
    # Access in browser:
    # http://localhost:7860
"""

import gradio as gr
from src.chat import Chatbot

def create_chatbot():
    """
    Creates and configures the chatbot interface.
    """
    chatbot = Chatbot()
    
    def chat(message, history, mode):
        """
        TODO:Generate a response for the current message in a Gradio chat interface.
        
        This function is called by Gradio's ChatInterface every time a user sends a message.
        You only need to generate and return the assistant's response - Gradio handles the
        chat display and history management automatically.

        Args:
            message (str): The current message from the user
            history (list): List of previous message pairs, where each pair is
                           [user_message, assistant_message]
                           Example:
                           [
                               ["What schools offer Spanish?", "The Hernandez School..."],
                               ["Where is it located?", "The Hernandez School is in Roxbury..."]
                           ]

        Returns:
            str: The assistant's response to the current message.


        Note:
            - Gradio automatically:
                - Displays the user's message
                - Displays your returned response
                - Updates the chat history
                - Maintains the chat interface
            - You only need to:
                - Generate an appropriate response to the current message
                - Return that response as a string
        """
        return chatbot.get_response(user_input=message, history=history, mode=mode)

    
    # Define the radio buttons for the UI
    mode_selector = gr.Radio(
        choices=["Find School", "Registration Guide", "Contact Info"],
        value="Find School", # Default value
        label="What do you need help with today?"
    )
    # Create Gradio interface
    demo = gr.ChatInterface(
        chat,
        title="🏫 Boston School Finder 🔎",
        additional_inputs=[mode_selector],
        additional_inputs_accordion=gr.Accordion(label="Chatbot Mode", open=True),
        description=(
            "Hi! I can help you navigate Boston school registration, find the "
            "right school for your child, or connect you with the right people! "
            "Select one of the modes below! (If you see a 503 error, please try again in a "
            "few seconds.)"
        ),
        examples=[
            ["How can I find the right school for my child?", "Find School"],
            ["How do I register my child for school in Boston?", "Registration Guide"],
            ["How can I find more information about who to contact?", "Contact Info"],
        ],
    )
 
    return demo

if __name__ == "__main__":
    demo = create_chatbot()
    demo.launch()

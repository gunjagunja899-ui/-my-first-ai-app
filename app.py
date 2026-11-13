
import streamlit as st
from google import genai

st.title("My First AI Chatbot 🤖")
st.write("Ask me anything!")

# Connect to Gemini
client = genai.Client(
    api_key=st.secrets["GEMINI_API_KEY"]
)

# Take user's question
question = st.text_input("Enter your question")

# Generate AI response
if st.button("Ask AI"):
    if question:
        with st.spinner("AI is thinking..."):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=question
                )
                st.write(response.text)
            except Exception as e:
                st.error(f"Error: {e}")
    else:
        st.warning("Please enter a question.")

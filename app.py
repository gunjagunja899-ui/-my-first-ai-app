import streamlit as st

st.title("My First AI App")

st.write("Welcome to my first application!")

name = st.text_input("Enter your name")

if st.button("Submit"):
    st.success("Welcome " + name)

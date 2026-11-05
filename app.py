import streamlit as st

st.title("My First AI App")

st.write("Welcome to my first application!")

name = st.text_input("Enter your name")
age = st.number_input("Enter your age", min_value=1, max_value=100, step=1)

if st.button("Submit"):
    st.success("Welcome " + name)

    if age >= 18:
        st.write("You are an Adult.")
    else:
        st.write("You are a Minor.")

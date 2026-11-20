
import streamlit as st
import bcrypt
from sqlalchemy import create_engine, text
from transformers import pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

st.set_page_config(
    page_title="MoodMentor",
    page_icon="🌿",
    layout="centered"
)

st.title("🌿 MoodMentor")
st.subheader("AI-Based Employee Wellness Management Platform")
st.write("Understand your emotions and explore wellness suggestions.")

# Database connection
@st.cache_resource
def get_engine():
    return create_engine(
        st.secrets["DATABASE_URL"],
        pool_pre_ping=True
    )

engine = get_engine()

# Load emotion model
@st.cache_resource
def load_model():
    return pipeline(
        "text-classification",
        model="bhadresh-savani/distilbert-base-uncased-emotion"
    )

# Create database tables if needed
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS app_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES app_users(id),
            journal TEXT,
            sentiment VARCHAR(30),
            emotion VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS app_recommendations (
            id SERIAL PRIMARY KEY,
            log_id INTEGER REFERENCES app_logs(id),
            suggestion TEXT,
            feedback VARCHAR(20)
        )
    """))

# Session state
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# Login and registration
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login"):
            with engine.connect() as conn:
                user = conn.execute(
                    text("SELECT id, password_hash FROM app_users WHERE username=:u"),
                    {"u": username}
                ).fetchone()

            if user and bcrypt.checkpw(
                password.encode(), user.password_hash.encode()
            ):
                st.session_state.user_id = user.id
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        new_user = st.text_input("Create username", key="new_user")
        new_pass = st.text_input("Create password", type="password", key="new_pass")

        if st.button("Create account"):
            if not new_user or len(new_pass) < 8:
                st.warning("Enter a username and password of at least 8 characters.")
            else:
                hashed = bcrypt.hashpw(
                    new_pass.encode(), bcrypt.gensalt()
                ).decode()
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO app_users(username,password_hash)
                                VALUES (:u,:p)
                            """),
                            {"u": new_user, "p": hashed}
                        )
                    st.success("Account created! Please login.")
                except Exception:
                    st.error("Username already exists.")

    st.stop()

# Logged-in dashboard
st.success("You are logged in!")
if st.button("Logout"):
    st.session_state.user_id = None
    st.rerun()

st.header("How are you feeling today?")
journal = st.text_area(
    "Write about your thoughts and feelings",
    height=150
)

recommendations = {
    "joy": [
        "Write down three things you are grateful for.",
        "Share your positive feelings with someone you trust.",
        "Take a short walk and enjoy your day."
    ],
    "sadness": [
        "Talk to someone you trust.",
        "Try a gentle walk or relaxing activity.",
        "Write your thoughts in a journal."
    ],
    "anger": [
        "Take slow, deep breaths.",
        "Pause and step away from stressful situations.",
        "Try a short relaxation exercise."
    ],
    "fear": [
        "Try slow breathing.",
        "Break a difficult task into smaller steps.",
        "Talk with someone you trust."
    ],
    "love": [
        "Express appreciation to someone important.",
        "Spend quality time with loved ones.",
        "Write down a positive memory."
    ],
    "surprise": [
        "Reflect on what surprised you today.",
        "Take a moment to process the experience.",
        "Share your experience with someone."
    ]
}

if st.button("Analyze My Mood"):
    if not journal.strip():
        st.warning("Please write something first.")
    else:
        with st.spinner("Analyzing your emotions..."):
            model = load_model()
            predictions = model(journal)[0]
            top = max(predictions, key=lambda x: x["score"])
            emotion = top["label"].lower()

            vader = SentimentIntensityAnalyzer()
            score = vader.polarity_scores(journal)["compound"]
            sentiment = (
                "Positive" if score >= 0.05
                else "Negative" if score <= -0.05
                else "Neutral"
            )

            with engine.begin() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO app_logs
                        (user_id,journal,sentiment,emotion)
                        VALUES (:uid,:j,:s,:e)
                        RETURNING id
                    """),
                    {
                        "uid": st.session_state.user_id,
                        "j": journal,
                        "s": sentiment,
                        "e": emotion
                    }
                )
                log_id = result.scalar_one()

                suggestions = recommendations.get(
                    emotion, recommendations["joy"]
                )

                for suggestion in suggestions:
                    conn.execute(
                        text("""
                            INSERT INTO app_recommendations
                            (log_id,suggestion)
                            VALUES (:lid,:s)
                        """),
                        {"lid": log_id, "s": suggestion}
                    )

            st.session_state.last_log_id = log_id
            st.session_state.last_emotion = emotion

        st.subheader("Your Emotion Analysis")
        st.write("Sentiment:", sentiment)
        st.write("Primary emotion:", emotion.title())
        st.write("Model confidence:", f"{top['score']:.2%}")

# Recommendations and feedback
if "last_log_id" in st.session_state:
    st.subheader("Your Wellness Recommendations")

    with engine.connect() as conn:
        items = conn.execute(
            text("""
                SELECT id, suggestion, feedback
                FROM app_recommendations
                WHERE log_id=:lid
                ORDER BY id
            """),
            {"lid": st.session_state.last_log_id}
        ).fetchall()

    for item in items:
        st.write("🌱", item.suggestion)
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Accept", key=f"accept_{item.id}"):
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE app_recommendations
                            SET feedback='accept'
                            WHERE id=:rid
                        """),
                        {"rid": item.id}
                    )
                st.success("Feedback saved!")

        with col2:
            if st.button("Reject", key=f"reject_{item.id}"):
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE app_recommendations
                            SET feedback='reject'
                            WHERE id=:rid
                        """),
                        {"rid": item.id}
                    )
                st.info("Feedback saved!")

# Personal history
st.header("My Emotion History")

with engine.connect() as conn:
    history = conn.execute(
        text("""
            SELECT journal, sentiment, emotion, created_at
            FROM app_logs
            WHERE user_id=:uid
            ORDER BY created_at DESC
        """),
        {"uid": st.session_state.user_id}
    ).fetchall()

if history:
    for record in history:
        with st.expander(
            f"{record.emotion.title()} — {record.created_at}"
        ):
            st.write(record.journal)
            st.write("Sentiment:", record.sentiment)
else:
    st.info("Your personal history will appear here.")

st.caption(
    "MoodMentor is a wellness support prototype, not a medical diagnosis tool."
)

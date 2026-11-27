
import streamlit as st
import bcrypt
from sqlalchemy import create_engine, text
from transformers import pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

st.set_page_config(page_title="MoodMentor", page_icon="🌿", layout="centered")

st.title("🌿 MoodMentor")
st.subheader("AI-Based Employee Wellness Management Platform")
st.write("Understand your emotions and explore wellness suggestions.")

@st.cache_resource
def get_engine():
    return create_engine(st.secrets["DATABASE_URL"], pool_pre_ping=True)

engine = get_engine()

@st.cache_resource
def load_model():
    return pipeline(
        "text-classification",
        model="bhadresh-savani/distilbert-base-uncased-emotion"
    )

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

if "user_id" not in st.session_state:
    st.session_state.user_id = None

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

            if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                st.session_state.user_id = user.id
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        new_user = st.text_input("Create username", key="new_user")
        new_pass = st.text_input("Create password", type="password", key="new_pass")

        if st.button("Create account"):
            if not new_user.strip() or len(new_pass) < 8:
                st.warning("Enter a username and password of at least 8 characters.")
            else:
                hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("INSERT INTO app_users(username,password_hash) VALUES (:u,:p)"),
                            {"u": new_user.strip(), "p": hashed}
                        )
                    st.success("Account created! Please login.")
                except Exception:
                    st.error("Username already exists.")

    st.stop()

st.success("You are logged in!")

if st.button("Logout"):
    st.session_state.user_id = None
    st.rerun()

st.header("How are you feeling today?")
journal = st.text_area("Write about your thoughts and feelings", height=150)

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
        try:
            with st.spinner("Analyzing your emotions..."):
                model = load_model()
                predictions = model(journal, top_k=None)

                if isinstance(predictions, list) and predictions and isinstance(predictions[0], list):
                    predictions = predictions[0]

                top = max(predictions, key=lambda x: float(x["score"]))
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
                            INSERT INTO app_logs (user_id,journal,sentiment,emotion)
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

                    for suggestion in recommendations.get(emotion, recommendations["joy"]):
                        conn.execute(
                            text("""
                                INSERT INTO app_recommendations (log_id,suggestion)
                                VALUES (:lid,:s)
                            """),
                            {"lid": log_id, "s": suggestion}
                        )

                st.session_state.last_log_id = log_id
                st.session_state.last_emotion = emotion
                st.session_state.last_score = float(top["score"])

            st.subheader("Your Emotion Analysis")
            st.write("Sentiment:", sentiment)
            st.write("Primary emotion:", emotion.title())
            st.write("Model confidence:", f"{top['score']:.2%}")

        except Exception as e:
            st.error(f"Analysis failed: {e}")

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
                        text("UPDATE app_recommendations SET feedback='accept' WHERE id=:rid"),
                        {"rid": item.id}
                    )
                st.success("Feedback saved!")

        with col2:
            if st.button("Reject", key=f"reject_{item.id}"):
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE app_recommendations SET feedback='reject' WHERE id=:rid"),
                        {"rid": item.id}
                    )
                st.info("Feedback saved!")

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
        with st.expander(f"{record.emotion.title()} — {record.created_at}"):
            st.write(record.journal)
            st.write("Sentiment:", record.sentiment)
else:
    st.info("Your personal history will appear here.")
# ==============================
# EMOTION TREND DASHBOARD
# ==============================

import pandas as pd

st.divider()
st.header("📊 Emotion Trend Dashboard")
st.write("Track your emotional patterns over the last 30 days.")

with engine.connect() as conn:
    trend_data = conn.execute(
        text("""
            SELECT
                created_at::date AS day,
                emotion,
                COUNT(*) AS total
            FROM app_logs
            WHERE user_id = :uid
              AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY created_at::date, emotion
            ORDER BY day
        """),
        {"uid": st.session_state.user_id}
    ).fetchall()

if trend_data:
    df = pd.DataFrame([dict(row._mapping) for row in trend_data])

    df["day"] = pd.to_datetime(df["day"])

    st.subheader("Your Mood Over Time")

    chart_data = df.pivot(
        index="day",
        columns="emotion",
        values="total"
    ).fillna(0)

    st.line_chart(chart_data)

    st.subheader("Emotion Summary")

    emotion_summary = (
        df.groupby("emotion")["total"]
        .sum()
        .sort_values(ascending=False)
    )

    st.bar_chart(emotion_summary)

else:
    st.info("No emotion data available yet. Analyze your mood to see trends.")
st.caption("MoodMentor is a wellness support prototype, not a medical diagnosis tool.")

# ==============================
# PERSONAL WELLNESS INSIGHTS
# ==============================

st.divider()
st.header("🌟 Your Personal Wellness Insights")

with engine.connect() as conn:
    insight_rows = conn.execute(
        text("""
            SELECT emotion, sentiment, created_at
            FROM app_logs
            WHERE user_id = :uid
            ORDER BY created_at DESC
        """),
        {"uid": st.session_state.user_id}
    ).fetchall()

if insight_rows:
    insight_df = pd.DataFrame(
        [dict(row._mapping) for row in insight_rows]
    )

    total_entries = len(insight_df)
    top_emotion = insight_df["emotion"].mode().iloc[0].title()
    active_days = insight_df["created_at"].dt.date.nunique()
    latest_emotion = insight_df.iloc[0]["emotion"].title()

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    col1.metric("Total Mood Entries", total_entries)
    col2.metric("Most Frequent Emotion", top_emotion)
    col3.metric("Active Days", active_days)
    col4.metric("Latest Emotion", latest_emotion)

    st.subheader("📊 Sentiment Breakdown")

    sentiment_counts = (
        insight_df["sentiment"]
        .value_counts()
    )

    st.bar_chart(sentiment_counts)

    st.subheader("🧠 Emotion Distribution")

    emotion_counts = (
        insight_df["emotion"]
        .value_counts()
    )

    st.bar_chart(emotion_counts)

    st.subheader("💡 Personal Insight")

    st.info(
        f"You have recorded {total_entries} mood entries. "
        f"Your most frequently detected emotion is {top_emotion}. "
        f"You have tracked your emotions across {active_days} days."
    )

else:
    st.info("Start analysing your mood to unlock personal insights!")

# ==============================
# WEEKLY MOOD REPORT
# ==============================

st.divider()
st.header("📅 Your Weekly Mood Report")
st.caption("A summary of your emotional activity over the last 7 days.")

with engine.connect() as conn:
    weekly_rows = conn.execute(
        text("""
            SELECT emotion, sentiment, created_at
            FROM app_logs
            WHERE user_id = :uid
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            ORDER BY created_at DESC
        """),
        {"uid": st.session_state.user_id}
    ).fetchall()

if weekly_rows:
    weekly_df = pd.DataFrame(
        [dict(row._mapping) for row in weekly_rows]
    )

    weekly_df["created_at"] = pd.to_datetime(
        weekly_df["created_at"]
    )

    total = len(weekly_df)
    common = weekly_df["emotion"].mode().iloc[0].title()
    days = weekly_df["created_at"].dt.date.nunique()

    positive = (
        weekly_df["sentiment"].astype(str).str.lower()
        == "positive"
    ).sum()

    negative = (
        weekly_df["sentiment"].astype(str).str.lower()
        == "negative"
    ).sum()

    neutral = total - positive - negative

    c1, c2, c3 = st.columns(3)
    c1.metric("Weekly Entries", total)
    c2.metric("Active Days", days)
    c3.metric("Most Common Emotion", common)

    st.subheader("Weekly Sentiment Summary")

    sentiment_data = pd.Series({
        "Positive": positive,
        "Neutral": neutral,
        "Negative": negative
    })

    st.bar_chart(sentiment_data)

    st.subheader("Emotion Frequency")
    st.bar_chart(weekly_df["emotion"].value_counts())

    st.subheader("📝 Your Weekly Reflection")

    st.info(
        f"You recorded {total} mood entries across {days} days. "
        f"Your most frequently detected emotion was {common}. "
        f"Positive entries: {positive}, "
        f"Neutral entries: {neutral}, "
        f"Negative entries: {negative}."
    )

else:
    st.info("No mood entries found for the last 7 days. Start tracking your emotions!")

# ==============================

# ==============================
# DAILY WELLNESS PLAN - DATABASE
# ==============================

st.divider()
st.header("🌱 My Daily Wellness Action Plan")
st.write("Choose activities and track your daily wellness progress.")

wellness_tasks = [
    "Practice 5 minutes of mindfulness",
    "Take a 10-minute walk",
    "Drink enough water",
    "Take a short screen break",
    "Write down three things you are grateful for",
    "Connect with a friend or colleague"
]

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS app_wellness_tasks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            task_date DATE NOT NULL DEFAULT CURRENT_DATE,
            task_name TEXT NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE(user_id, task_date, task_name)
        )
    """))

uid = st.session_state.user_id

with engine.connect() as conn:
    saved_rows = conn.execute(
        text("""
            SELECT task_name, completed
            FROM app_wellness_tasks
            WHERE user_id = :uid
            AND task_date = CURRENT_DATE
        """),
        {"uid": uid}
    ).fetchall()

saved_tasks = {
    row.task_name: row.completed
    for row in saved_rows
}

st.subheader("Today's Wellness Goals")

completed_count = 0

for i, task in enumerate(wellness_tasks):
    checked = st.checkbox(
        task,
        value=bool(saved_tasks.get(task, False)),
        key=f"daily_wellness_{uid}_{i}"
    )

    if checked != bool(saved_tasks.get(task, False)):
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app_wellness_tasks
                    (user_id, task_date, task_name, completed)
                    VALUES (:uid, CURRENT_DATE, :task, :completed)
                    ON CONFLICT (user_id, task_date, task_name)
                    DO UPDATE SET completed = EXCLUDED.completed
                """),
                {
                    "uid": uid,
                    "task": task,
                    "completed": checked
                }
            )

    if checked:
        completed_count += 1

total_tasks = len(wellness_tasks)
progress = completed_count / total_tasks

st.subheader("📈 Daily Progress")
st.progress(progress)

st.write(
    f"You completed {completed_count} out of "
    f"{total_tasks} wellness goals."
)

if completed_count == total_tasks:
    st.success("Amazing! All daily wellness goals completed! 🎉")
elif completed_count > 0:
    st.success("Great progress! Keep going! 🌿")
else:
    st.info("Start with one small wellness activity today.")

# ==============================
# EMOTION-BASED PERSONALIZED RECOMMENDATIONS
# ==============================

st.divider()
st.header("💚 Personalized Wellness Recommendations")
st.write("Wellness suggestions based on your latest detected emotion.")

emotion_tips = {
    "joy": [
        "Write down three things you are grateful for.",
        "Share your happiness with someone you trust.",
        "Celebrate a small achievement today."
    ],
    "sadness": [
        "Talk to a trusted friend or colleague.",
        "Take a gentle walk in fresh air.",
        "Try writing down how you feel."
    ],
    "anger": [
        "Take a short break before responding to stressful situations.",
        "Try slow and steady breathing.",
        "Step away briefly and return when you feel ready."
    ],
    "fear": [
        "Try a grounding exercise: notice five things around you.",
        "Break a difficult task into smaller steps.",
        "Talk with someone you trust about your concerns."
    ],
    "love": [
        "Express appreciation to someone important to you.",
        "Spend quality time with people you care about.",
        "Write a positive message to someone."
    ],
    "surprise": [
        "Take a moment to reflect on what happened.",
        "Write down your thoughts and feelings.",
        "Give yourself time to adjust to unexpected changes."
    ]
}

with engine.connect() as conn:
    latest_emotion = conn.execute(
        text("""
            SELECT emotion
            FROM app_logs
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"uid": st.session_state.user_id}
    ).fetchone()

if latest_emotion:
    emotion = str(latest_emotion[0]).lower()

    st.subheader(f"Your latest emotion: {emotion.title()}")

    tips = emotion_tips.get(
        emotion,
        [
            "Take a short mindful break.",
            "Write down your thoughts.",
            "Connect with someone you trust."
        ]
    )

    for i, tip in enumerate(tips, 1):
        st.success(f"🌱 {tip}")

else:
    st.info("Analyze your mood first to receive personalized suggestions.")

st.caption(
    "These suggestions support personal reflection and are not medical advice."
)

# ==============================

# ==============================
# EMPLOYEE STRESS LEVEL TRACKER
# ==============================

st.divider()
st.header("🧠 Daily Stress Level Tracker")

st.write("Record how stressed you feel today.")

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS app_stress_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            stress_level INTEGER NOT NULL,
            notes TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

uid = st.session_state.user_id

with engine.connect() as conn:
    today_stress = conn.execute(
        text("""
            SELECT stress_level, notes, recorded_at
            FROM app_stress_logs
            WHERE user_id = :uid
              AND recorded_at::date = CURRENT_DATE
            ORDER BY recorded_at DESC
            LIMIT 1
        """),
        {"uid": uid}
    ).fetchone()

if today_stress:
    st.info(
        f"Today's latest stress level: "
        f"{today_stress.stress_level}/10"
    )
else:
    st.write("You have not recorded your stress level today.")

with st.form("stress_tracker_form"):
    stress_level = st.slider(
        "How stressed do you feel today?",
        min_value=1,
        max_value=10,
        value=5
    )

    stress_notes = st.text_area(
        "What may be causing your stress? (Optional)"
    )

    save_stress = st.form_submit_button("Save Stress Level")

if save_stress:
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO app_stress_logs
                (user_id, stress_level, notes)
                VALUES (:uid, :level, :notes)
            """),
            {
                "uid": uid,
                "level": stress_level,
                "notes": stress_notes
            }
        )

    st.success("Your stress level has been saved successfully! 🌿")
    st.rerun()

st.caption(
    "This is a self-reported wellness tracker, not a medical diagnosis."
)

# ==============================
# STRESS HISTORY DASHBOARD
# ==============================

st.divider()
st.header("📊 Stress History Dashboard")

uid = st.session_state.user_id

with engine.connect() as conn:
    stress_history = conn.execute(
        text("""
            SELECT stress_level, notes, recorded_at
            FROM app_stress_logs
            WHERE user_id = :uid
            ORDER BY recorded_at DESC
            LIMIT 30
        """),
        {"uid": uid}
    ).fetchall()

if stress_history:
    levels = [row.stress_level for row in reversed(stress_history)]

    average_stress = sum(levels) / len(levels)
    highest_stress = max(levels)

    col1, col2 = st.columns(2)

    col1.metric("Average Stress", f"{average_stress:.1f}/10")
    col2.metric("Highest Stress", f"{highest_stress}/10")

    st.subheader("Stress Level Trend")
    st.line_chart({"Stress Level": levels})

    st.subheader("Previous Stress Records")

    st.dataframe([
        {
            "Date": str(row.recorded_at),
            "Stress Level": f"{row.stress_level}/10",
            "Notes": row.notes or "No notes"
        }
        for row in stress_history
    ], use_container_width=True)

else:
    st.info("No stress history available yet.")


import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="TMDB SQL & Analytics Explorer", page_icon="🎬", layout="wide")

DB_PATH = "tmdb_movies.db"

@st.cache_data
def run_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# Load filter options
try:
    all_genres = run_query("SELECT DISTINCT genre_name FROM genres ORDER BY genre_name")['genre_name'].tolist()
    year_bounds = run_query("""
        SELECT MIN(CAST(substr(release_date, 1, 4) AS INT)) AS min_y,
               MAX(CAST(substr(release_date, 1, 4) AS INT)) AS max_y
        FROM movies WHERE release_date IS NOT NULL
    """)
    min_year = int(year_bounds['min_y'].iloc[0])
    max_year = int(year_bounds['max_y'].iloc[0])
except Exception as e:
    st.error(f"Database error: {e}. Please run `01_data_cleaning.ipynb` first to generate `tmdb_movies.db`.")
    st.stop()

# SHARED SIDEBAR NAVIGATION & GLOBAL FILTERS
st.sidebar.title("🎬 TMDB Analytics Hub")
page = st.sidebar.radio("Navigate Pages", ["1️⃣ Filters & Catalog", "2️⃣ Executive Dashboard", "3️⃣ SQL Query Explorer"])

st.sidebar.divider()
st.sidebar.subheader("Global Filters")
selected_genres = st.sidebar.multiselect("Filter by Genre", all_genres, default=[])
year_range = st.sidebar.slider("Release Year Range", min_year, max_year, (2000, max_year))
min_rating = st.sidebar.slider("Minimum Rating (vote_average)", 0.0, 10.0, 5.0, 0.5)
exclude_zero_fin = st.sidebar.checkbox("Exclude $0 Budget/Revenue", value=True)

# Build dynamic SQL WHERE clause
where_clauses = [
    f"CAST(substr(m.release_date, 1, 4) AS INT) BETWEEN {year_range[0]} AND {year_range[1]}",
    f"m.vote_average >= {min_rating}"
]
if exclude_zero_fin:
    where_clauses.append("m.budget > 0 AND m.revenue > 0")
if selected_genres:
    genre_list_sql = "', '".join(selected_genres)
    where_clauses.append(f"g.genre_name IN ('{genre_list_sql}')")

where_sql = " AND ".join(where_clauses)

base_query = f"""
    SELECT DISTINCT m.movie_id, m.title, m.release_date,
           CAST(substr(m.release_date, 1, 4) AS INT) AS release_year,
           m.runtime, m.budget, m.revenue, (m.revenue - m.budget) AS profit,
           m.popularity, m.vote_average, m.vote_count, m.original_language
    FROM movies m
    LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
    LEFT JOIN genres g ON mg.genre_id = g.genre_id
    WHERE {where_sql}
"""
filtered_df = run_query(base_query)

# PAGE 1: FILTERS & CATALOG EXPLORER
if page == "1️⃣ Filters & Catalog":
    st.title("1️⃣ Interactive Movie Catalog & Filters")
    st.markdown("Use the sidebar filters to slice the SQLite database in real time.")

    search_title = st.text_input("🔍 Search by Movie Title:", "")
    display_df = filtered_df.copy()
    if search_title:
        display_df = display_df[display_df['title'].str.contains(search_title, case=False, na=False)]

    c1, c2, c3 = st.columns(3)
    c1.metric("Matching Movies", f"{len(display_df):,}")
    c2.metric("Average Rating", f"⭐ {display_df['vote_average'].mean():.2f}" if len(display_df) else "N/A")
    c3.metric("Total Box Office", f"${display_df['revenue'].sum()/1e9:.2f}B" if len(display_df) else "$0")

    st.dataframe(
        display_df[['title', 'release_date', 'runtime', 'budget', 'revenue', 'profit', 'vote_average', 'popularity']],
        use_container_width=True,
        hide_index=True
    )

# PAGE 2: EXECUTIVE DASHBOARD

elif page == "2️⃣ Executive Dashboard":
    st.title("2️⃣ Box Office & Audience Dashboard")

    if filtered_df.empty:
        st.warning("No movies match your current sidebar filter selection.")
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Filtered Movies", f"{len(filtered_df):,}")
        k2.metric("Avg Budget", f"${filtered_df['budget'].mean()/1e6:.1f}M")
        k3.metric("Avg Revenue", f"${filtered_df['revenue'].mean()/1e6:.1f}M")
        k4.metric("Avg Rating", f"{filtered_df['vote_average'].mean():.2f} / 10")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Budget vs. Revenue")
            fig1 = px.scatter(
                filtered_df, x="budget", y="revenue", hover_name="title",
                color="vote_average", size="vote_count", color_continuous_scale="Viridis"
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            st.subheader("Releases per Year")
            yearly = filtered_df.groupby('release_year').size().reset_index(name='count')
            fig2 = px.bar(yearly, x="release_year", y="count", color_discrete_sequence=["#2E86AB"])
            st.plotly_chart(fig2, use_container_width=True)



# PAGE 3: SQL QUERY EXPLORER
elif page == "3️⃣ SQL Query Explorer":
    st.title("3️⃣ Live SQL Query Explorer")
    st.markdown("Run preset analytical SQL queries or write your own custom `SELECT` query against `tmdb_movies.db`.")

    preset_queries = {
        "Custom Query": "SELECT title, release_date, budget, revenue, vote_average FROM movies ORDER BY revenue DESC LIMIT 15;",
        "Top 10 Highest-Grossing Movies + Genres": """SELECT m.title, m.revenue, GROUP_CONCAT(g.genre_name, ', ') AS genres
FROM movies m
LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
LEFT JOIN genres g ON mg.genre_id = g.genre_id
GROUP BY m.movie_id, m.title, m.revenue
ORDER BY m.revenue DESC LIMIT 10;""",
        "Top 10 Prolific Actors": """SELECT actor_name, COUNT(DISTINCT movie_id) AS movie_count
FROM cast GROUP BY person_id, actor_name ORDER BY movie_count DESC LIMIT 10;""",
        "Directors with > 3 Movies": """SELECT person_name AS director, COUNT(DISTINCT movie_id) AS movie_count
FROM crew WHERE job = 'Director' GROUP BY person_id, person_name HAVING COUNT(DISTINCT movie_id) > 3 ORDER BY movie_count DESC;""",
        "Highest Rated Genres (Min 20 Movies)": """SELECT g.genre_name, COUNT(m.movie_id) AS movies, ROUND(AVG(m.vote_average), 2) AS avg_rating
FROM genres g JOIN movie_genres mg ON g.genre_id = mg.genre_id JOIN movies m ON mg.movie_id = m.movie_id
GROUP BY g.genre_id, g.genre_name HAVING COUNT(m.movie_id) >= 20 ORDER BY avg_rating DESC;"""
    }

    choice = st.selectbox("Choose a preset SQL query:", list(preset_queries.keys()))
    sql_input = st.text_area("SQL Editor (Read-only SELECT queries):", value=preset_queries[choice], height=160)

    if st.button("Execute SQL Query ▶️", type="primary"):
        if not sql_input.strip().lower().startswith("select"):
            st.error("Only read-only SELECT queries are permitted in the explorer.")
        else:
            try:
                res = run_query(sql_input)
                st.success(f"Returned {len(res)} rows.")
                st.dataframe(res, use_container_width=True, hide_index=True)
            except Exception as err:
                st.error(f"SQL Syntax Error: {err}")

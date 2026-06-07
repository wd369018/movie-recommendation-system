import os
import pickle
import streamlit as st
import pandas as pd
import numpy as np


TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
df_path = os.path.join(BASE_DIR, 'df.pkl')
indices_path = os.path.join(BASE_DIR, 'indices.pkl')
matrix_path = os.path.join(BASE_DIR, 'tfidf_matrix.pkl')


@st.cache_resource
def load_data():
    with open(df_path, 'rb') as f:
        df_data = pickle.load(f)

    with open(indices_path, 'rb') as f:
        indices_map = pickle.load(f)

    with open(matrix_path, 'rb') as f:
        tfidf = pickle.load(f)

    return df_data, indices_map, tfidf


try:
    df, indices, tfidf_matrix = load_data()

except Exception as e:
    st.error(f"Error loading system assets: {e}")
    st.stop()


def get_recommendations(title, indices=indices, tfidf_matrix=tfidf_matrix):
    try:
        title_lower = title.lower().strip()

        if title_lower not in indices:
            return ["Movie not found in database. Try another search!"]

        idx = indices[title_lower]

        from sklearn.metrics.pairwise import cosine_similarity

        sim_scores = cosine_similarity(tfidf_matrix, tfidf_matrix[idx]).flatten()

        sim_indices = np.argsort(sim_scores)[::-1][1:6]

        movie_column = 'title' if 'title' in df.columns else df.columns[0]

        return df[movie_column].iloc[sim_indices].tolist()

    except Exception as e:
        return [f"An evaluation error occurred: {e}"]


st.set_page_config(page_title="Movie Recommender System", layout="centered", page_icon="🎬")
st.title("🎬 Content-Based Movie Recommendation System")
st.write("Enter a movie name below to instantly discover top content suggestions based on textual features.")


movie_list = sorted(list(indices.keys()))
selected_movie = st.selectbox("Type or select a movie you like:", movie_list)


if st.button("Recommend"):
    with st.spinner("Analyzing structural features..."):
        recommendations = get_recommendations(selected_movie)

        st.subheader("Top Suggestions for You:")

        for i, movie in enumerate(recommendations, 1):
            st.success(f"{i}. {movie.title()}")
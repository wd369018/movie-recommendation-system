# 🎬 Movie Recommendation System

A Content-Based Movie Recommendation System built with Python, Scikit-Learn, and Streamlit. This application processes metadata from movies, vectorizes contextual textual features using TF-IDF vectorization, and recommends top similar titles based on Cosine Similarity matrices.

## 🚀 Project Features
- **Dynamic Content Analysis:** Leverages natural language processing concepts to match contextual features.
- **Optimized Caching:** Implements Streamlit's `@st.cache_resource` for swift internal performance without memory bottlenecks.
- **Robust UI:** Offers clean cross-platform operational styling using interactive native inputs.

## 📂 File Architecture
```text
├── app.py                  # Main Streamlit application entrypoint
├── requirements.txt        # System application dependency parameters
├── df.pkl                  # Serialized primary movie DataFrame
├── indices.pkl             # Mapping lookup structure (Movie titles -> Index positions)
├── tfidf_matrix.pkl        # Compressed sparse structural token vectors
└── README.md               # Documentation file

# 🎬 DramaDx AI – End-to-End ML Recommendation System

DramaDx AI is an end-to-end machine learning–based drama and movie discovery platform that delivers intelligent recommendations using real-world data pipelines, similarity learning, and API-driven enrichment.

---

## 🚀 Overview

This project goes beyond basic recommendation systems by integrating:

* Dynamic dataset generation using TMDB API
* Feature engineering and similarity-based ML
* Model training and artifact storage
* Full-stack Streamlit application for real-time interaction

---

## 🧠 Machine Learning Approach

### Model Type

* Unsupervised Learning
* Content-Based Recommendation System

### Core Technique

* Feature extraction from:

  * Genres
  * Overview (text)
  * Themes
  * Metadata (country, language)
* Vectorization using TF-IDF / embeddings
* Similarity computation using cosine similarity

---

## ⚙️ End-to-End Pipeline

```
TMDB API → Data Collection → Feature Engineering → Model Training → Saved Artifacts → Streamlit UI
```

---

## 📂 Project Structure

```
DramaDx-AI/
│
├── app.py                      # Streamlit frontend
├── requirements.txt            # Dependencies
├── README.md                   # Documentation
│
├── src/                        # Core logic
│   ├── recommender.py         # ML model (similarity-based)
│   ├── data.py                # Data loading & preprocessing
│   ├── tmdb.py                # TMDB API integration
│   ├── youtube.py             # Trailer fetching
│   ├── config.py              # Config paths
│
├── scripts/                    # Pipelines
│   ├── train_model.py         # Train & save ML model
│
├── data/                       # Generated datasets
│   ├── dramas_seed.csv
│   ├── movies_seed.csv
│   ├── cast_seed.csv
│   ├── movies_cast_seed.csv
│   ├── seasons_seed.csv
│   ├── show_aliases.csv
│   ├── populate_from_tmdb.py
│   ├── populate_movies_fast.py
│
├── artifacts/                  # Trained models
│   ├── drama_recommender.joblib
│   ├── movie_recommender.joblib
```

---

## ⚡ Key Features

* Intelligent drama & movie recommendations
* Actor exploration with metadata
* Trailer integration using YouTube
* Real-time data enrichment via TMDB
* Handles missing/dirty data robustly
* Parallel data processing for faster dataset generation

---

## 🆚 How It Differs from Basic Projects

| Basic Projects          | DramaDx AI                          |
| ----------------------- | ----------------------------------- |
| Static dataset (Kaggle) | Dynamic API-based dataset           |
| No real ML pipeline     | Full training + inference pipeline  |
| Minimal preprocessing   | Advanced data cleaning & validation |
| Simple UI               | Interactive full-stack application  |
| No scalability          | Modular & extensible architecture   |

---

## 🛠 Tech Stack

* Python
* Streamlit
* Pandas / NumPy
* Scikit-learn
* TMDB API
* YouTube API
* Joblib (model persistence)

---

## ▶️ Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 🔄 Train Model

```bash
python scripts/train_model.py
```

---

## 📌 Future Enhancements

* Hybrid recommendation system (content + collaborative filtering)
* User personalization
* Deployment (Docker / AWS / Streamlit Cloud)
* API caching & async optimization

---

## 👨‍💻 Author

Shubham
Machine Learning & AI Enthusiast

---

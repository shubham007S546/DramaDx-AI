from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import argparse

from src.config import ARTIFACT_PATH, DATA_PATH
from src.data import load_movies
from src.recommender import MovieRecommender


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the local movie recommendation model.")
    parser.add_argument("--dataset", default=str(DATA_PATH), help="Path to the movie CSV file.")
    parser.add_argument("--artifact", default=str(ARTIFACT_PATH), help="Path to save the model artifact.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    artifact_path = Path(args.artifact)

    movies = load_movies(dataset_path)
    recommender = MovieRecommender().fit(movies)
    recommender.save(artifact_path)

    print(f"Trained recommender on {len(movies)} movies.")
    print(f"Saved artifact to: {artifact_path.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()

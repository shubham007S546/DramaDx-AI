from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import argparse

from src.config import ARTIFACT_PATH, DATA_PATH
from src.data import load_catalog
from src.recommender import DramaRecommender


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the local drama recommendation model.")
    parser.add_argument("--dataset", default=str(DATA_PATH), help="Path to the drama CSV file.")
    parser.add_argument("--artifact", default=str(ARTIFACT_PATH), help="Path to save the model artifact.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    artifact_path = Path(args.artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    dramas = load_catalog(dataset_path)
    recommender = DramaRecommender().fit(dramas)
    recommender.save(artifact_path)

    print(f"Trained recommender on {len(dramas)} dramas.")
    print(f"Saved artifact to: {artifact_path.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()

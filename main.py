"""gloss — AI-augmented lecture note-taking app."""

import sys
from src.app import create_app


def main():
    app = create_app()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

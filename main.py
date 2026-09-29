"""
EcoNova Root Launcher
---------------------
Allows running the AI detection module directly from project root:
    python main.py
Or from the ai/ directory:
    cd ai
    python main.py
"""

import sys
import os

# Add ai/ to system path
AI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai")
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

from ai.main import main

if __name__ == "__main__":
    main()

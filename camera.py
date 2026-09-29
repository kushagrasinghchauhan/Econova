"""
Root wrapper for ai/camera.py
"""
import sys
import os

AI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai")
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

from ai.camera import Camera, get_camera

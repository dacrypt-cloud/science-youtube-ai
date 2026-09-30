"""First end-to-end test (spec §41):
"How does a mosquito transmit malaria, and what actually happens to Plasmodium inside the mosquito?"
Target 12-15 min. Runs the REAL pipeline (network + TTS + FFmpeg).
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from science_studio import storage
from science_studio.pipeline import run_project

IDEA = "How does a mosquito transmit malaria, and what actually happens to Plasmodium inside the mosquito?"

if __name__ == "__main__":
    pid, root = storage.create_project(IDEA, duration="12-15", mode="autonomous")
    print("PROJECT:", pid)
    res = run_project(pid)
    print(json.dumps(res, indent=2))

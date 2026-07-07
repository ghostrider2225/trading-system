#!/bin/zsh
# Open the trading dashboard in the browser
cd "$(dirname "$0")"
.venv/bin/streamlit run dashboard/app.py --server.port 8501 --server.headless true &
sleep 2
open http://localhost:8501
wait

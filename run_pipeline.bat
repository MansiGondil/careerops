@echo off
REM Scheduled entry point. Task Scheduler cannot activate a venv,
REM so call the venv's python directly.

cd /d D:\careerops
call .venv\Scripts\activate.bat
python -m src.run_pipeline

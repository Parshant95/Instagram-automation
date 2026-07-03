@echo off
REM Non-interactive runner for Windows Task Scheduler (no pause).
cd /d "%~dp0"
python youtube_poster.py >> "%~dp0youtube_poster.log" 2>&1

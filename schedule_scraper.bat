@echo off
echo Registering daily scraper task (runs every day at 8:00 AM)...

schtasks /create /tn "DesktopHutScraper" ^
  /tr "python \"C:\Users\parsh\Documents\ProjectX\Automation\desktophut_scraper.py\"" ^
  /sc daily /st 08:00 ^
  /sd 06/13/2026 ^
  /f

echo.
echo Done! Scraper will run every day at 8:00 AM automatically.
echo Videos saved to: C:\Users\parsh\Documents\ProjectX\Automation\downloads\
pause

@echo off
echo Starting Alter on Raspberry Pi. Enter the Pi account password if requested.
ssh -t -o ConnectTimeout=15 pi@127.0.0.1 "/home/pi/hw-agent/start.sh --no-browser"
set "alter_result=%errorlevel%"
if not "%alter_result%"=="0" if not "%alter_result%"=="2" goto done
start "" "http://127.0.0.1:11977/"
:done
pause

@echo off
chcp 65001 >NUL
set PYTHONUTF8=1
echo Starting AutoBet Bot in Demo mode (Dry-run)...
python -m src.autobet.run_bot --event-source demo --dry-run 1
pause
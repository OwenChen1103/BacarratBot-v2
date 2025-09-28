@echo off
chcp 65001 >NUL
set PYTHONUTF8=1
echo Starting AutoBet Bot with NDJSON replay (Dry-run)...
python -m src.autobet.run_bot --event-source ndjson --ndjson-file data\sessions\events.sample.ndjson --dry-run 1
pause
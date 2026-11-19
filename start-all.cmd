@echo off
setlocal
set "DESKTOP=%USERPROFILE%\Desktop"
set "RUNTIME=%DESKTOP%\llama.cpp\llama-b12532-bin-win-cuda-12.4-x64"
set "CUDA=%DESKTOP%\llama.cpp\cudart-llama-bin-win-cuda-12.4-x64"
set "MODEL_DIR=%DESKTOP%\Ai\Qwen35_Vision"
set "MODEL=%MODEL_DIR%\Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
set "MMPROJ=%MODEL_DIR%\mmproj-Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive-f16.gguf"

curl.exe -s --max-time 2 "http://127.0.0.1:8080/health" >nul 2>nul
if not errorlevel 1 goto :studio

if not exist "%RUNTIME%\llama-server.exe" (
 echo ERROR: llama-server.exe not found: %RUNTIME%
 pause
 exit /b 1
)
if not exist "%MODEL%" (
 echo ERROR: Qwen model not found: %MODEL%
 pause
 exit /b 1
)
if not exist "%MMPROJ%" (
 echo ERROR: mmproj not found: %MMPROJ%
 pause
 exit /b 1
)
set "PATH=%CUDA%;%PATH%"
start "Qwen3.5 - local server" /D "%RUNTIME%" "%RUNTIME%\llama-server.exe" -m "%MODEL%" --mmproj "%MMPROJ%" -ngl 4 -c 16384 --port 8080
:studio
call "%~dp0start-studio.cmd"

@echo off
setlocal
REM Link Prompt Extractor Studio v0.2 to the user's GitHub update channel.
REM Does not download or execute remote code; does not touch models or results.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ErrorActionPreference='Stop'; $url='https://raw.githubusercontent.com/nakumaakuma-web/GORK/main/update-manifest.json'; $roots=@((Join-Path $env:USERPROFILE 'Desktop'),(Join-Path $env:USERPROFILE 'Downloads'),(Join-Path $env:USERPROFILE 'Documents'),(Join-Path $env:USERPROFILE 'OneDrive\Desktop')); $found=@(); foreach($r in $roots){if(!(Test-Path -LiteralPath $r)){continue}; if((Test-Path -LiteralPath (Join-Path $r 'updater.py')) -and (Test-Path -LiteralPath (Join-Path $r 'ui\index.html'))){$found+=@($r)}; foreach($p in @(Get-ChildItem -Path $r -Filter '*Prompt*' -Directory -Recurse -Depth 5 -ErrorAction SilentlyContinue)){ if((Test-Path -LiteralPath (Join-Path $p.FullName 'updater.py')) -and (Test-Path -LiteralPath (Join-Path $p.FullName 'ui\index.html'))){$found+=@($p.FullName)}} }; $found=@($found | Select-Object -Unique); if($found.Count -eq 0){throw 'Prompt Extractor Studio not found on Desktop, Downloads, or Documents. Open its folder and run this file from there.'}; if($found.Count -gt 1){Write-Host 'Found multiple installations:'; for($i=0;$i -lt $found.Count;$i++){Write-Host ($i+1) $found[$i]}; $n=[int](Read-Host 'Enter installation number'); if($n -lt 1 -or $n -gt $found.Count){throw 'Wrong number'}; $folder=$found[$n-1]}else{$folder=$found[0]}; $conf=Join-Path $folder 'update_config.json'; $obj=@{}; if(Test-Path -LiteralPath $conf){$old=Get-Content -LiteralPath $conf -Raw -Encoding UTF8|ConvertFrom-Json; $old.PSObject.Properties|ForEach-Object{$obj[$_.Name]=$_.Value}; Copy-Item -LiteralPath $conf -Destination ($conf+'.before-github.bak') -Force}; $obj['manifest_url']=$url; $obj|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $conf -Encoding UTF8; Write-Host 'CONNECTED:' $folder -ForegroundColor Green; Write-Host 'Now open http://127.0.0.1:8765 and click Check updates -> Install update.'; Start-Process 'http://127.0.0.1:8765'"
if errorlevel 1 (
 echo Failed. No app code was changed.
 pause
 exit /b 1
)
exit /b 0

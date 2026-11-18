$taskPidFile=Join-Path $PSScriptRoot 'data/server.pid'
if(-not(Test-Path -LiteralPath $taskPidFile)){Write-Host '이 폴더가 시작한 서버 기록이 없습니다.';exit}
$taskServerPid=[int](Get-Content -LiteralPath $taskPidFile)
$taskProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$taskServerPid"
$taskScript=Join-Path $PSScriptRoot 'server.py'
if($taskProcess -and $taskProcess.CommandLine.Contains($taskScript)){Stop-Process -Id $taskServerPid;Write-Host '온터 지식 지도 서버를 종료했습니다.'}
elseif($taskProcess){throw '프로세스가 이 폴더의 서버인지 확인되지 않아 종료하지 않았습니다.'}
else{Write-Host '서버가 이미 종료되었습니다.'}

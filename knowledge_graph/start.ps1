param([int]$Port=8767,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
$taskURL="http://127.0.0.1:$Port"
$pythonCommand=Get-Command python -ErrorAction SilentlyContinue
$taskPython=if($pythonCommand){$pythonCommand.Source}else{Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'}
if(-not(Test-Path -LiteralPath $taskPython)){throw 'Python이 필요합니다.'}
if(-not(Test-Path -LiteralPath (Join-Path $taskRoot 'data/knowledge.sqlite'))){Push-Location $taskRoot;try{& $taskPython build_graph.py;if($LASTEXITCODE -ne 0){throw '그래프 생성 실패'}}finally{Pop-Location}}
$existing=$null
try{$existing=Invoke-RestMethod "$taskURL/api/stats" -TimeoutSec 2}catch{}
if($existing -and $existing.service -ne 'onter-knowledge-graph'){throw '다른 서비스가 이 포트를 사용 중입니다. -Port로 다른 번호를 지정하세요.'}
if(-not $existing){
 $taskScript=Join-Path $taskRoot 'server.py'
 $taskProcess=Start-Process -FilePath $taskPython -ArgumentList @('-u',('"'+$taskScript+'"'),'--port',"$Port") -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRoot 'data/server.log') -RedirectStandardError (Join-Path $taskRoot 'data/server.error.log')
 Set-Content -LiteralPath (Join-Path $taskRoot 'data/server.pid') -Value $taskProcess.Id
 $ready=$false
 for($attempt=0;$attempt -lt 20;$attempt++){try{$probe=Invoke-RestMethod "$taskURL/api/stats" -TimeoutSec 1;if($probe.service -eq 'onter-knowledge-graph'){$ready=$true;break}}catch{};Start-Sleep -Milliseconds 250}
 if(-not $ready){throw '서버가 시작되지 않았습니다. data/server.error.log를 확인하세요.'}
}
Write-Host "온터 지식 지도: $taskURL"
if(-not $NoBrowser){Start-Process $taskURL}

$ErrorActionPreference = 'Stop'
$account = Read-Host 'Pi account / Pi 계정'
$piHost = Read-Host 'Pi hostname or IP / Pi 호스트 또는 IP'
if ($account -notmatch '^[a-z_][a-z0-9_-]*$' -or $piHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') {
    throw 'Invalid account or hostname / 계정 또는 호스트 형식을 확인하세요.'
}
& ssh -t -o ConnectTimeout=15 "$account@$piHost" '~/hw-agent/start.sh --no-browser'
if ($LASTEXITCODE -ne 0) { throw 'Remote startup needs attention / 원격 시작 상태를 확인하세요.' }
Start-Process "http://${piHost}:11977"

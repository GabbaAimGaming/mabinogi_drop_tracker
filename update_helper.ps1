param([Parameter(Mandatory=$true)][string]$PlanFile)
$ErrorActionPreference = 'Stop'
$plan = $null
$changed = @()
$backup = $null
$lock = $null
$resultFile = Join-Path (Split-Path -Parent $PlanFile) 'result.json'

function Hash([string]$file) {
    $stream = [IO.File]::OpenRead($file)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function CheckedPath([string]$root, [string]$relative) {
    if ($relative -match '\\|:|(^|/)\.\.?(/|$)' -or $relative.StartsWith('/') -or $relative -match '(^|/)[^/]*[ .](/|$)') { throw 'Invalid update path.' }
    if ($relative -notmatch '^(_internal|assets|references|models|licenses|dictionary-docs)/' -and
        $relative -notin @('KarenDrop.exe','item-master.json','requirements.txt','README_EXE.txt','更新内容.txt','更新方法.txt','現在の問題点と対処方法.txt','検証記録.txt','update_helper.ps1','release-manifest.json')) { throw 'Protected file in update.' }
    foreach ($part in $relative.Split('/')) { if ($part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$') { throw 'Invalid file name.' } }
    $fullRoot = [IO.Path]::GetFullPath($root).TrimEnd('\')
    $full = [IO.Path]::GetFullPath((Join-Path $fullRoot $relative))
    if (-not $full.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path outside update folder.' }
    $cursor = $full
    while ($cursor -and $cursor.Length -ge $fullRoot.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked folders are not supported.' }
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}
function WriteResult([bool]$ok, [string]$message) {
    @{ok=$ok;message=$message;backup=$backup} | ConvertTo-Json | Set-Content -LiteralPath $resultFile -Encoding UTF8
}

try {
    $plan = Get-Content -LiteralPath $PlanFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $target = [IO.Path]::GetFullPath($plan.target)
    $payload = [IO.Path]::GetFullPath($plan.payload)
    if (-not (Test-Path -LiteralPath (Join-Path $target 'KarenDrop.exe'))) { throw 'KarenDrop.exe was not found.' }
    if ($target -eq $payload) { throw 'Source and destination must differ.' }
    if ($plan.parent_pid -gt 0) {
        $parent = Get-Process -Id $plan.parent_pid -ErrorAction SilentlyContinue
        if ($parent) { Wait-Process -InputObject $parent -Timeout 120 -ErrorAction Stop }
    }
    foreach ($running in @(Get-Process -Name KarenDrop -ErrorAction SilentlyContinue)) {
        if ($running.Path -eq (Join-Path $target 'KarenDrop.exe')) { throw 'Close every KarenDrop window before updating.' }
    }
    $lockPath = Join-Path $target '.update.lock'
    if ((Test-Path -LiteralPath $lockPath) -and ((Get-Item -LiteralPath $lockPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid lock file.' }
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if ($plan.base_exe_sha256 -and (Hash (Join-Path $target 'KarenDrop.exe')) -ne $plan.base_exe_sha256) { throw 'This patch is only for the original v0.18 Windows release.' }
    $seen = @{}
    $needed = 0L
    foreach ($item in $plan.files) {
        if ($seen.ContainsKey($item.path)) { throw 'Duplicate update entry.' }; $seen[$item.path] = $true
        $source = CheckedPath $payload $item.path
        $destination = CheckedPath $target $item.path
        if ($item.sha256 -notmatch '^[a-f0-9]{64}$' -or (Hash $source) -ne $item.sha256) { throw ('File verification failed: ' + $item.path) }
        if (-not (Test-Path -LiteralPath $destination) -or (Hash $destination) -ne $item.sha256) {
            $needed += (Get-Item -LiteralPath $source).Length
            $exists = Test-Path -LiteralPath $destination
            if ($exists) { $needed += (Get-Item -LiteralPath $destination).Length }
            $changed += @{path=$item.path;existed=$exists;sha256=$item.sha256}
        }
    }
    if (-not $seen.ContainsKey('KarenDrop.exe')) { throw 'Missing application file.' }
    $drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($target))
    if ($drive.AvailableFreeSpace -lt ($needed + 50MB)) { throw 'Not enough free disk space.' }
    $backupRoot = Join-Path $target '.update-backups'
    if ((Test-Path -LiteralPath $backupRoot) -and ((Get-Item -LiteralPath $backupRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid backup folder.' }
    $backup = Join-Path $backupRoot ([guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach ($item in $changed) {
        if ($item.existed) {
            $saved = CheckedPath $backup $item.path
            New-Item -ItemType Directory -Path (Split-Path -Parent $saved) -Force | Out-Null
            Copy-Item -LiteralPath (CheckedPath $target $item.path) -Destination $saved
        }
    }
    @{target=$target;version=$plan.version;files=$changed} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backup 'restore.json') -Encoding UTF8
    $applied = @()
    try {
        foreach ($item in $changed) {
            $dest = CheckedPath $target $item.path
            New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
            $applied += $item
            Copy-Item -LiteralPath (CheckedPath $payload $item.path) -Destination $dest -Force
            if ((Hash $dest) -ne $item.sha256) { throw 'Installed file verification failed.' }
        }
        $report = Join-Path $backup 'startup-check.json'
        $process = Start-Process -FilePath (Join-Path $target 'KarenDrop.exe') -ArgumentList @('--self-test', ('"' + $report + '"')) -WorkingDirectory $target -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(120000)) { $process.Kill(); $process.WaitForExit(); throw 'New version startup check timed out.' }
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) { throw 'New version startup check failed.' }
        $health = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $health.ok -or $health.title -notlike ('*v' + $plan.version)) { throw 'New version startup check failed.' }
    } catch {
        $problem = $_.Exception.Message
        $restoreFailures = @()
        [array]::Reverse($applied)
        foreach ($item in $applied) {
            try {
                $dest = CheckedPath $target $item.path
                if ($item.existed) { Copy-Item -LiteralPath (CheckedPath $backup $item.path) -Destination $dest -Force }
                elseif (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Force }
            } catch { $restoreFailures += $item.path }
        }
        if ($restoreFailures.Count) { throw ($problem + ' Rollback incomplete: ' + ($restoreFailures -join ', ') + '. Backup: ' + $backup) }
        throw ($problem + ' Previous files restored. Backup: ' + $backup)
    }
    WriteResult $true 'Update completed.'
    # 更新成功後に、このツールが作成した一時ファイルだけを削除する。
    $work = [IO.Path]::GetFullPath((Split-Path -Parent $PlanFile))
    $expectedWork = Join-Path $target '.updates'
    if ($work.StartsWith($expectedWork + '\', [StringComparison]::OrdinalIgnoreCase) -and $payload -eq (Join-Path $work 'payload')) {
        foreach ($item in $plan.files) { Remove-Item -LiteralPath (CheckedPath $payload $item.path) -Force -ErrorAction SilentlyContinue }
        Remove-Item -LiteralPath (Join-Path $work 'download.zip') -Force -ErrorAction SilentlyContinue
    }
    # 旧バックアップは記録されたファイルだけ整理し、直前の1版を保持する。
    foreach ($old in @(Get-ChildItem -LiteralPath $backupRoot -Directory)) {
        if ($old.FullName -eq $backup -or $old.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        $journal = Join-Path $old.FullName 'restore.json'
        try {
            $prior = Get-Content -LiteralPath $journal -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($prior.target -ne $target) { continue }
            foreach ($item in $prior.files) {
                $file = CheckedPath $old.FullName $item.path
                if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
            }
            Remove-Item -LiteralPath $journal -Force
        } catch { } # 整理失敗は更新成功を取り消さない。
    }
    $lock.Dispose(); $lock = $null
    if (-not $plan.no_restart) { Start-Process -FilePath (Join-Path $target 'KarenDrop.exe') -WorkingDirectory $target -WindowStyle Hidden }
    exit 0
} catch {
    $message = $_.Exception.Message
    WriteResult $false $message
    if (-not $plan.quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(('更新できませんでした。現在の状態と復旧先は次のログを確認してください。' + [Environment]::NewLine + $resultFile + [Environment]::NewLine + $message), 'KarenDrop 更新') | Out-Null
    }
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}

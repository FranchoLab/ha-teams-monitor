<#
.SYNOPSIS
Disposable, sanitized, read-only probe for New Teams log structure and call-state marker candidates.

.DESCRIPTION
Inventories the current user's New Teams log directory and, in capture mode, compares
marker candidates appended to the logs while you move Teams through labelled states
(idle, prejoin, ringing, joined, muted, left, ...).

The probe never prints or saves raw log lines. It reports only file-name shapes,
sizes, encodings, line shapes (letters -> 'a', digits -> '9'), and identifier-like
tokens or key/value pairs whose key mentions call/meeting/state vocabulary. Values of
keys that look like names, titles, identifiers, URLs, or message text are dropped.
Review the report before sharing it anyway.

It opens files read-only with sharing enabled, needs no elevation, and does not
change Teams settings.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows_teams_log_discovery.ps1
#>
[CmdletBinding()]
param(
    [string]$LogDirectory = '',
    [string]$OutputPath = '',
    [switch]$InventoryOnly,
    [string[]]$Labels = @(),
    [ValidateRange(1, 256)]
    [int]$MaxMegabytesPerRead = 16,
    [ValidateRange(1, 500)]
    [int]$TopCount = 40
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$PackageRelativeLogPath = 'Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs'
$MarkerKeywords = 'call|meeting|join|leave|left|hang|end|disconnect|connect|ring|incoming|mute|state|status|presence|activity|busy|conversation|media|audio|video|room|lobby'
$SensitiveKeyPattern = 'name|title|subject|user|display|mail|upn|tenant|id$|ids$|uri|url|link|message|text|body|topic|organi[sz]er|participant|thread|phone|number|token|key|secret|path|file|host|address|caller|callee|sender|recipient|attendee|member|person|contact|alias|account|identity|owner|creator|from'
$TokenPattern = [regex]'[A-Za-z_][A-Za-z0-9_.\-]{2,63}'
# Bare tokens must look like code identifiers so plain words such as personal names are dropped.
$CompoundTokenRegex = [regex]'[a-z][A-Z]|[_.]'
$KeyValuePattern = [regex]'(?<key>[A-Za-z_][A-Za-z0-9_.\-]{1,48})"?\s*[:=]\s*"?(?<value>[A-Za-z_][A-Za-z0-9_.\-]{0,31})\b'
$MarkerRegex = [regex]::new($MarkerKeywords, 'IgnoreCase')
$SensitiveKeyRegex = [regex]::new($SensitiveKeyPattern, 'IgnoreCase')
$UnsafeTokenRegex = [regex]'@|[0-9A-Fa-f]{8,}|[0-9]{5,}|https?|www\.|\\|/'

$Report = New-Object System.Collections.Generic.List[string]

function Write-Report {
    param([string]$Line = '')
    $Report.Add($Line)
    Write-Host $Line
}

function Get-Shape {
    param([string]$Text, [int]$MaxLength = 160)
    $shape = [regex]::Replace($Text, '[A-Za-z]', 'a')
    $shape = [regex]::Replace($shape, '[0-9]', '9')
    $shape = [regex]::Replace($shape, 'a{4,}', 'aaa+')
    $shape = [regex]::Replace($shape, '9{4,}', '999+')
    if ($shape.Length -gt $MaxLength) { $shape = $shape.Substring(0, $MaxLength) + '...' }
    return $shape
}

function Get-EncodingName {
    param([byte[]]$Bytes)
    if ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF) { return 'utf-8-bom' }
    if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0xFF -and $Bytes[1] -eq 0xFE) { return 'utf-16le-bom' }
    if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0xFE -and $Bytes[1] -eq 0xFF) { return 'utf-16be-bom' }
    $sample = [Math]::Min($Bytes.Length, 4096)
    if ($sample -eq 0) { return 'empty' }
    $oddNulls = 0
    $evenNulls = 0
    for ($i = 0; $i -lt $sample; $i++) {
        if ($Bytes[$i] -eq 0) {
            if ($i % 2 -eq 1) { $oddNulls++ } else { $evenNulls++ }
        }
    }
    if ($oddNulls -gt ($sample / 4)) { return 'utf-16le' }
    if ($evenNulls -gt ($sample / 4)) { return 'utf-16be' }
    if (($oddNulls + $evenNulls) -gt 0) { return 'binary' }
    return 'utf-8-or-ascii'
}

function ConvertFrom-LogBytes {
    param([byte[]]$Bytes, [string]$EncodingName)
    switch -Wildcard ($EncodingName) {
        'utf-16le*' { return [System.Text.Encoding]::Unicode.GetString($Bytes) }
        'utf-16be*' { return [System.Text.Encoding]::BigEndianUnicode.GetString($Bytes) }
        'binary' { return '' }
        default { return [System.Text.Encoding]::UTF8.GetString($Bytes) }
    }
}

function Read-LogBytes {
    param([string]$Path, [long]$Offset, [long]$MaxBytes, [switch]$FromStart)
    $stream = New-Object System.IO.FileStream(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
    )
    try {
        $length = $stream.Length
        $start = $Offset
        $end = $length
        $skipped = [long]0
        if (($length - $start) -gt $MaxBytes) {
            $skipped = ($length - $start) - $MaxBytes
            if ($FromStart) { $end = $start + $MaxBytes } else { $start = $length - $MaxBytes }
        }
        $count = [int]($end - $start)
        $buffer = New-Object byte[] $count
        [void]$stream.Seek($start, [System.IO.SeekOrigin]::Begin)
        $read = 0
        while ($read -lt $count) {
            $n = $stream.Read($buffer, $read, $count - $read)
            if ($n -le 0) { break }
            $read += $n
        }
        if ($read -lt $count) { $buffer = $buffer[0..([Math]::Max(0, $read - 1))] }
        return [pscustomobject]@{ Bytes = $buffer; Length = $length; Skipped = $skipped }
    }
    finally {
        $stream.Dispose()
    }
}

function Get-LogFiles {
    param([string]$Root)
    return @(Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction Stop)
}

function Get-RelativeShape {
    param([string]$Root, [string]$FullName)
    $relative = $FullName.Substring($Root.Length).TrimStart('\', '/')
    $relative = [regex]::Replace($relative, '[0-9]', '9')
    return [regex]::Replace($relative, '[0-9A-Fa-f]{8}-([0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}', '<guid>')
}

function Get-MarkerCandidates {
    param([string]$Text)
    $counts = @{}
    foreach ($match in $TokenPattern.Matches($Text)) {
        $token = $match.Value
        if (-not $MarkerRegex.IsMatch($token)) { continue }
        if (-not $CompoundTokenRegex.IsMatch($token)) { continue }
        if ($UnsafeTokenRegex.IsMatch($token)) { continue }
        $token = [regex]::Replace($token, '[0-9]+', '#')
        $counts[$token] = 1 + [int]$counts[$token]
    }
    foreach ($match in $KeyValuePattern.Matches($Text)) {
        $key = $match.Groups['key'].Value
        $value = $match.Groups['value'].Value
        if (-not $MarkerRegex.IsMatch($key)) { continue }
        if ($SensitiveKeyRegex.IsMatch($key)) { continue }
        if ($UnsafeTokenRegex.IsMatch($key) -or $UnsafeTokenRegex.IsMatch($value)) { continue }
        $pair = ([regex]::Replace($key, '[0-9]+', '#')) + '=' + ([regex]::Replace($value, '[0-9]+', '#'))
        $counts[$pair] = 1 + [int]$counts[$pair]
    }
    return $counts
}

function Get-LineStats {
    param([string]$Text)
    $crlf = ([regex]::Matches($Text, "`r`n")).Count
    $lf = ([regex]::Matches($Text, "`n")).Count - $crlf
    $lines = @($Text -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
    return [pscustomobject]@{ Crlf = $crlf; Lf = $lf; Lines = $lines }
}

function Write-Inventory {
    param([string]$Root)
    Write-Report '== Environment'
    Write-Report ("Windows build: {0}" -f [Environment]::OSVersion.Version)
    Write-Report ("PowerShell: {0}" -f $PSVersionTable.PSVersion)
    try {
        $package = Get-AppxPackage -Name 'MSTeams' -ErrorAction Stop | Select-Object -First 1
        if ($null -ne $package) { Write-Report ("New Teams package: {0}" -f $package.Version) }
        else { Write-Report 'New Teams package: not found for this user' }
    }
    catch {
        Write-Report 'New Teams package: unavailable'
    }
    Write-Report ''
    Write-Report '== Inventory'
    $files = Get-LogFiles -Root $Root
    Write-Report ("Files: {0}" -f $files.Count)
    foreach ($group in ($files | Group-Object { $_.Extension.ToLowerInvariant() } | Sort-Object Name)) {
        Write-Report ("  extension '{0}': {1}" -f $group.Name, $group.Count)
    }
    foreach ($file in ($files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First $TopCount)) {
        try {
            $head = Read-LogBytes -Path $file.FullName -Offset 0 -MaxBytes 65536 -FromStart
        }
        catch {
            Write-Report ''
            Write-Report ("File: {0} (unreadable: {1})" -f (Get-RelativeShape -Root $Root -FullName $file.FullName), $_.Exception.GetType().Name)
            continue
        }
        $encoding = Get-EncodingName -Bytes $head.Bytes
        Write-Report ''
        Write-Report ("File: {0}" -f (Get-RelativeShape -Root $Root -FullName $file.FullName))
        Write-Report ("  size={0} bytes, lastWriteUtc={1:o}, createdUtc={2:o}, encoding={3}" -f $file.Length, $file.LastWriteTimeUtc, $file.CreationTimeUtc, $encoding)
        if ($encoding -eq 'binary' -or $encoding -eq 'empty') { continue }
        $stats = Get-LineStats -Text (ConvertFrom-LogBytes -Bytes $head.Bytes -EncodingName $encoding)
        Write-Report ("  line endings in first 64 KiB: crlf={0}, lf={1}" -f $stats.Crlf, $stats.Lf)
        foreach ($line in ($stats.Lines | Select-Object -First 3)) {
            Write-Report ("  line shape: {0}" -f (Get-Shape -Text $line))
        }
    }
}

function Get-Snapshot {
    param([string]$Root)
    $snapshot = @{}
    foreach ($file in (Get-LogFiles -Root $Root)) {
        $snapshot[$file.FullName] = [pscustomobject]@{
            Length = $file.Length
            CreatedUtc = $file.CreationTimeUtc
        }
    }
    return $snapshot
}

function Read-Segment {
    param([string]$Root, [hashtable]$Offsets, [hashtable]$Encodings)
    $maxBytes = [long]$MaxMegabytesPerRead * 1MB
    $events = New-Object System.Collections.Generic.List[string]
    $combined = @{}
    $totalBytes = [long]0
    $totalLines = 0
    $current = Get-Snapshot -Root $Root
    $vanished = New-Object System.Collections.Generic.List[object]
    foreach ($path in @($Offsets.Keys)) {
        if (-not $current.ContainsKey($path)) {
            $vanished.Add([pscustomobject]@{ Path = $path; Info = $Offsets[$path] })
            $Offsets.Remove($path)
        }
    }
    # A file that reappears under a new name with the same creation time was renamed, not rewritten.
    foreach ($path in @($current.Keys)) {
        if ($Offsets.ContainsKey($path)) { continue }
        $match = $vanished | Where-Object {
            $_.Info.CreatedUtc -eq $current[$path].CreatedUtc -and $_.Info.Length -le $current[$path].Length
        } | Select-Object -First 1
        if ($null -ne $match) {
            $events.Add(("renamed: {0} -> {1}" -f (Get-RelativeShape -Root $Root -FullName $match.Path), (Get-RelativeShape -Root $Root -FullName $path)))
            $Offsets[$path] = $match.Info
            if ($Encodings.ContainsKey($match.Path)) { $Encodings[$path] = $Encodings[$match.Path] }
            [void]$vanished.Remove($match)
        }
    }
    foreach ($entry in $vanished) {
        $events.Add(("removed: {0}" -f (Get-RelativeShape -Root $Root -FullName $entry.Path)))
    }
    foreach ($path in $current.Keys) {
        $info = $current[$path]
        $shape = Get-RelativeShape -Root $Root -FullName $path
        $offset = [long]0
        if ($Offsets.ContainsKey($path)) {
            $previous = $Offsets[$path]
            if ($info.CreatedUtc -ne $previous.CreatedUtc) {
                $events.Add(("replaced (new creation time): {0}" -f $shape))
            }
            elseif ($info.Length -lt $previous.Length) {
                $events.Add(("truncated: {0}" -f $shape))
            }
            else {
                $offset = $previous.Length
            }
        }
        else {
            $events.Add(("new file: {0}" -f $shape))
        }
        if ($info.Length -le $offset) {
            $Offsets[$path] = $info
            continue
        }
        try {
            $chunk = Read-LogBytes -Path $path -Offset $offset -MaxBytes $maxBytes
        }
        catch {
            $events.Add(("unreadable ({0}): {1}" -f $_.Exception.GetType().Name, $shape))
            continue
        }
        if ($chunk.Skipped -gt 0) {
            $events.Add(("skipped {0} bytes beyond read cap: {1}" -f $chunk.Skipped, $shape))
        }
        $Offsets[$path] = [pscustomobject]@{ Length = $chunk.Length; CreatedUtc = $info.CreatedUtc }
        if (-not $Encodings.ContainsKey($path) -or $offset -eq 0) {
            $Encodings[$path] = Get-EncodingName -Bytes (Read-LogBytes -Path $path -Offset 0 -MaxBytes 4096 -FromStart).Bytes
        }
        $encoding = $Encodings[$path]
        $bytes = $chunk.Bytes
        if ($encoding -like 'utf-16*' -and ($offset % 2) -ne 0 -and $bytes.Length -gt 1) {
            $bytes = $bytes[1..($bytes.Length - 1)]
        }
        $text = ConvertFrom-LogBytes -Bytes $bytes -EncodingName $encoding
        $totalBytes += $bytes.Length
        $totalLines += (Get-LineStats -Text $text).Lines.Count
        $candidates = Get-MarkerCandidates -Text $text
        foreach ($key in $candidates.Keys) {
            $combined[$key] = [int]$combined[$key] + $candidates[$key]
        }
    }
    return [pscustomobject]@{
        Events = $events
        Candidates = $combined
        Bytes = $totalBytes
        Lines = $totalLines
    }
}

function Invoke-Capture {
    param([string]$Root)
    Write-Report ''
    Write-Report '== Capture'
    Write-Report 'Put Teams in a state, wait about 30 seconds, then type a label for the state you are now in.'
    Write-Report 'Suggested order: idle, prejoin, joined, muted, unmuted, left, ringing, declined, joined2, left2.'
    Write-Report 'Each segment covers log data appended since the previous label. Type q to finish.'

    $offsets = Get-Snapshot -Root $Root
    $encodings = @{}
    $segments = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    $queue = New-Object System.Collections.Generic.Queue[string]
    foreach ($label in ($Labels | ForEach-Object { $_ -split ',' })) {
        if ($label.Trim() -ne '') { $queue.Enqueue($label.Trim()) }
    }
    $lastMark = Get-Date

    while ($true) {
        if ($queue.Count -gt 0) {
            $label = $queue.Dequeue()
            Read-Host ("Press Enter when Teams is in state '{0}'" -f $label) | Out-Null
        }
        else {
            $label = Read-Host 'State label (q to finish)'
        }
        if ($null -eq $label) { break }
        $label = $label.Trim()
        if ($label -eq 'q') { break }
        if ($label -eq '') { continue }
        $label = [regex]::Replace($label, '[^A-Za-z0-9_\-]', '_')

        $now = Get-Date
        $segment = Read-Segment -Root $Root -Offsets $offsets -Encodings $encodings
        $elapsed = [Math]::Round(($now - $lastMark).TotalSeconds, 1)
        $lastMark = $now
        $segments.Add([pscustomobject]@{ Label = $label; Candidates = $segment.Candidates })

        Write-Report ''
        Write-Report ("-- Segment '{0}': {1}s, {2} bytes, {3} non-empty lines appended" -f $label, $elapsed, $segment.Bytes, $segment.Lines)
        foreach ($event in $segment.Events) { Write-Report ("  file event: {0}" -f $event) }
        $ranked = $segment.Candidates.GetEnumerator() | Sort-Object -Property @{ Expression = 'Value'; Descending = $true }, @{ Expression = 'Name'; Descending = $false }
        $newOnes = @($ranked | Where-Object { -not $seen.ContainsKey($_.Name) } | Select-Object -First $TopCount)
        Write-Report ("  first-seen candidates ({0}):" -f $newOnes.Count)
        foreach ($entry in $newOnes) { Write-Report ("    {0,6}  {1}" -f $entry.Value, $entry.Name) }
        Write-Report '  most frequent candidates:'
        foreach ($entry in ($ranked | Select-Object -First $TopCount)) { Write-Report ("    {0,6}  {1}" -f $entry.Value, $entry.Name) }
        foreach ($key in $segment.Candidates.Keys) { $seen[$key] = $true }
    }

    if ($segments.Count -lt 2) { return }

    Write-Report ''
    Write-Report '== Discriminating candidates (absent from at least one segment)'
    $labels = @($segments | ForEach-Object { $_.Label })
    Write-Report ("  segments: {0}" -f ($labels -join ', '))
    $rows = foreach ($key in $seen.Keys) {
        $counts = @($segments | ForEach-Object { [int]$_.Candidates[$key] })
        $present = @($counts | Where-Object { $_ -gt 0 }).Count
        if ($present -lt $segments.Count) {
            [pscustomobject]@{ Name = $key; Present = $present; Counts = $counts }
        }
    }
    $rows = @($rows | Sort-Object -Property Present, Name | Select-Object -First ($TopCount * 3))
    foreach ($row in $rows) {
        Write-Report ("  {0}  {1}" -f (($row.Counts | ForEach-Object { '{0,5}' -f $_ }) -join ' '), $row.Name)
    }
}

if ($LogDirectory -eq '') {
    if (-not $env:LOCALAPPDATA) {
        [Console]::Error.WriteLine('LOCALAPPDATA is not set; run this on Windows as the user who runs Teams.')
        exit 2
    }
    $LogDirectory = Join-Path $env:LOCALAPPDATA $PackageRelativeLogPath
}
if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
    [Console]::Error.WriteLine('Teams log directory not found or not accessible for this user.')
    exit 2
}
$LogDirectory = (Resolve-Path -LiteralPath $LogDirectory).ProviderPath.TrimEnd('\', '/')
if ($OutputPath -eq '') {
    $tempRoot = [System.IO.Path]::GetTempPath()
    $OutputPath = Join-Path $tempRoot ('teams-log-discovery-{0:yyyyMMdd-HHmmss}.txt' -f (Get-Date))
}

Write-Report 'Sanitized Teams log discovery. Raw log lines are never printed or saved.'
Write-Report ("Started: {0:o}" -f (Get-Date).ToUniversalTime())
Write-Report ''
Write-Inventory -Root $LogDirectory
if (-not $InventoryOnly) { Invoke-Capture -Root $LogDirectory }

[System.IO.File]::WriteAllLines($OutputPath, $Report.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
Write-Host ''
Write-Host ("Report saved to {0}. Review it before sharing; delete it when no longer needed." -f $OutputPath)

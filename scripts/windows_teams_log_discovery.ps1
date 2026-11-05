<#
.SYNOPSIS
Disposable, sanitized, read-only probe for New Teams log structure and call-state marker candidates.

.DESCRIPTION
Inventories the current user's New Teams log directory and, in capture mode, compares
marker candidates appended to the logs while you move Teams through labelled states
(idle, prejoin, ringing, joined, muted, left, ...).

The probe never prints or saves raw log lines. It reports only file-name shapes,
sizes, encodings, line shapes (letters -> 'a', digits -> '9'), safe field names and
types, allow-listed state values, and counts of call/state word pairs. Values that
are not known state words and fields that could contain personal or meeting details
are dropped. Review the report before sharing it anyway.

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
$SensitiveKeyPattern = 'name|title|subject|user|display|mail|upn|tenant|id$|ids$|uri|url|link|message|text|body|topic|organi[sz]er|participant|thread|phone|number|token|key|secret|path|file|folder|directory|location|host|address|caller|callee|sender|recipient|attendee|member|person|contact|alias|account|identity|owner|creator|from'
$KeyValuePattern = [regex]'(?<key>[A-Za-z_][A-Za-z0-9_.\-]{1,48})"?\s*[:=]\s*"?(?<value>[A-Za-z_][A-Za-z0-9_.\-]{0,31})\b'
$StateValueWords = @(
    'active', 'call', 'connected', 'connecting', 'connection',
    'conversation', 'ended', 'ending', 'false', 'hang', 'hangup', 'idle', 'in',
    'inactive', 'incoming', 'is', 'join', 'joined', 'joining', 'leave', 'leaving',
    'left', 'lobby', 'meeting', 'mute', 'muted', 'no', 'not', 'off', 'on', 'out',
    'ring', 'ringing', 'session', 'state', 'status', 'stopped', 'true', 'unmuted',
    'was', 'waiting', 'yes'
)
$SensitiveKeyRegex = [regex]::new($SensitiveKeyPattern, 'IgnoreCase')
$SafePropertyNameRegex = [regex]'^[A-Za-z_][A-Za-z0-9_.\-]{0,47}$'
$SafePropertyPathRegex = [regex]'^[A-Za-z_][A-Za-z0-9_.\-\[\]]{0,191}$'
$CallContextWords = @('call', 'meeting', 'conversation', 'conference')
$StateSignalWords = @('active', 'connected', 'connecting', 'disconnect', 'disconnected', 'end', 'ended', 'ending', 'hang', 'hangup', 'idle', 'inactive', 'incoming', 'join', 'joined', 'joining', 'leave', 'leaving', 'left', 'lobby', 'mute', 'muted', 'ring', 'ringing', 'state', 'status', 'unmuted')
$EventFieldWords = @('action', 'event', 'operation', 'outcome', 'phase', 'reason', 'result', 'transition', 'type')

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
    $parts = foreach ($part in ($relative -split '[\\/]')) {
        $extension = [System.IO.Path]::GetExtension($part).ToLowerInvariant()
        $stem = if ($extension) { $part.Substring(0, $part.Length - $extension.Length) } else { $part }
        (Get-Shape -Text $stem -MaxLength 48) + $extension
    }
    return $parts -join '/'
}

function Add-FieldCandidate {
    param([string]$Key, [object]$Value, [hashtable]$Counts)
    $leaf = ($Key -split '[.]')[-1] -replace '\[\]$', ''
    if ($SensitiveKeyRegex.IsMatch($Key)) { return }
    if (-not $SafePropertyPathRegex.IsMatch($Key)) { return }

    $safeValue = Get-SafeStateValue -Value $Value
    if (-not (Test-StateFieldKey -Key $Key -Value $Value -SafeValue $safeValue)) { return }

    $safeKey = [regex]::Replace($Key, '[0-9]+', '#')
    $type = if ($null -eq $Value) { 'null' } elseif ($Value -is [bool]) { 'boolean' } elseif ($Value -is [string]) { 'string' } elseif ($Value -is [ValueType]) { 'number' } else { 'other' }
    $typeCandidate = "field:$safeKey`:$type"
    $Counts[$typeCandidate] = 1 + [int]$Counts[$typeCandidate]

    if (-not $safeValue -and $type -eq 'number' -and $leaf -match '^(state|status|phase|result|outcome)$') {
        $number = 0
        if ([int]::TryParse([string]$Value, [ref]$number) -and $number -ge -1 -and $number -le 10) {
            $safeValue = "enum$number"
        }
    }
    if ($safeValue) {
        $valueCandidate = "field:$safeKey`:$safeValue"
        $Counts[$valueCandidate] = 1 + [int]$Counts[$valueCandidate]
    }
}

function Get-SemanticWords {
    param([string]$Text)
    $normalized = [regex]::Replace($Text, '([A-Z]+)([A-Z][a-z])', '$1 $2')
    $normalized = [regex]::Replace($normalized, '([a-z0-9])([A-Z])', '$1 $2')
    return @([regex]::Matches($normalized, '[A-Za-z]+') | ForEach-Object { $_.Value.ToLowerInvariant() })
}

function Test-StateFieldKey {
    param([string]$Key, [object]$Value, [string]$SafeValue)
    $keyWords = @(Get-SemanticWords -Text $Key)
    $valueWords = if ($Value -is [string]) { @(Get-SemanticWords -Text $Value) } else { @() }
    $hasCallContext = @($keyWords | Where-Object { $_ -in $CallContextWords }).Count -gt 0
    $hasStateSignal = @($keyWords | Where-Object { $_ -in $StateSignalWords }).Count -gt 0
    $hasEventField = @($keyWords | Where-Object { $_ -in $EventFieldWords }).Count -gt 0
    $valueHasContext = @($valueWords | Where-Object { $_ -in $CallContextWords }).Count -gt 0
    $valueHasSignal = @($valueWords | Where-Object { $_ -in $StateSignalWords }).Count -gt 0

    if ($hasCallContext -and ($hasStateSignal -or $Value -is [bool] -or $valueHasSignal)) { return $true }
    if ($hasEventField -and ($valueHasSignal -or $valueHasContext) -and $SafeValue) { return $true }
    return $false
}

function Get-SafeStateValue {
    param([object]$Value)
    if ($Value -is [bool]) { return $Value.ToString().ToLowerInvariant() }
    if ($Value -isnot [string]) { return '' }

    $text = $Value.Trim()
    if ($text.Length -gt 64) { return '' }
    $text = [regex]::Replace($text, '([a-z])([A-Z])', '$1 $2')
    if ($text -notmatch '^[A-Za-z]+(?:[\s_.:/-]+[A-Za-z]+)*$') { return '' }

    $words = @([regex]::Matches($text, '[A-Za-z]+') | ForEach-Object { $_.Value.ToLowerInvariant() })
    if ($words.Count -eq 0) { return '' }
    foreach ($word in $words) {
        if ($StateValueWords -notcontains $word) { return '' }
    }
    return $words -join ''
}

function Add-JsonFieldCandidates {
    param([object]$Value, [string]$Path, [hashtable]$Counts, [int]$Depth = 0)
    if ($Depth -gt 8 -or $null -eq $Value) { return }

    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) {
            $name = [string]$key
            if (-not $SafePropertyNameRegex.IsMatch($name) -or $SensitiveKeyRegex.IsMatch($name)) { continue }
            $childPath = if ($Path) { "$Path.$name" } else { $name }
            Add-JsonFieldCandidates -Value $Value[$key] -Path $childPath -Counts $Counts -Depth ($Depth + 1)
        }
        return
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        foreach ($property in $Value.PSObject.Properties) {
            if ($property.MemberType -notin @('NoteProperty', 'Property')) { continue }
            if (-not $SafePropertyNameRegex.IsMatch($property.Name) -or $SensitiveKeyRegex.IsMatch($property.Name)) { continue }
            $childPath = if ($Path) { "$Path.$($property.Name)" } else { $property.Name }
            Add-JsonFieldCandidates -Value $property.Value -Path $childPath -Counts $Counts -Depth ($Depth + 1)
        }
        return
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        foreach ($item in $Value) {
            Add-JsonFieldCandidates -Value $item -Path "$Path[]" -Counts $Counts -Depth ($Depth + 1)
        }
        return
    }
    Add-FieldCandidate -Key $Path -Value $Value -Counts $Counts
}

function Get-MarkerCandidates {
    param([string]$Text)
    $counts = @{}
    foreach ($line in ($Text -split "`r?`n")) {
        if (-not $line.Trim()) { continue }

        $start = $line.IndexOf('{')
        $end = $line.LastIndexOf('}')
        $jsonParsed = $false
        $record = $null
        if ($start -ge 0 -and $end -gt $start) {
            $jsonText = $line.Substring($start, $end - $start + 1)
            try {
                $record = ConvertFrom-Json -InputObject $jsonText -ErrorAction Stop
                $jsonParsed = $true
            }
            catch {
                # Non-JSON lines are handled by the key/value and safe word-pair scans.
            }
        }

        if ($jsonParsed) {
            Add-JsonFieldCandidates -Value $record -Path '' -Counts $counts
        }
        else {
            foreach ($match in $KeyValuePattern.Matches($line)) {
                $key = $match.Groups['key'].Value
                if ($SensitiveKeyRegex.IsMatch($key)) { continue }
                Add-FieldCandidate -Key $key -Value $match.Groups['value'].Value -Counts $counts
            }
        }

        $normalized = [regex]::Replace($line, '([a-z])([A-Z])', '$1 $2')
        $words = @([regex]::Matches($normalized, '[A-Za-z]+') | ForEach-Object { $_.Value.ToLowerInvariant() })
        $contexts = @($words | Where-Object { $_ -in @('call', 'meeting', 'conversation', 'conference') } | Select-Object -Unique)
        $states = @($words | Where-Object { $_ -in @('join', 'joined', 'joining', 'leave', 'leaving', 'left', 'end', 'ended', 'ending', 'connect', 'connected', 'connecting', 'disconnect', 'disconnected', 'ring', 'ringing', 'incoming', 'active', 'inactive', 'idle') } | Select-Object -Unique)
        foreach ($context in $contexts) {
            foreach ($state in $states) {
                $pair = "text:$context+$state"
                $counts[$pair] = 1 + [int]$counts[$pair]
            }
        }
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
    $perFile = @{}
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
            $fileCandidate = "$shape :: $key"
            $perFile[$fileCandidate] = [int]$perFile[$fileCandidate] + $candidates[$key]
        }
    }
    return [pscustomobject]@{
        Events = $events
        Candidates = $combined
        PerFile = $perFile
        Bytes = $totalBytes
        Lines = $totalLines
    }
}

function Invoke-Capture {
    param([string]$Root)
    Write-Report ''
    Write-Report '== Capture'
    Write-Report 'Change Teams to a state, wait about 30 seconds, then type that state label.'
    Write-Report 'Each label summarizes log changes since the previous label; the first covers time since capture started.'
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
        Write-Report '  candidate signatures by sanitized file-name shape:'
        $fileRanked = $segment.PerFile.GetEnumerator() | Sort-Object -Property @{ Expression = 'Value'; Descending = $true }, @{ Expression = 'Name'; Descending = $false }
        foreach ($entry in ($fileRanked | Select-Object -First $TopCount)) {
            Write-Report ("    {0,6}  {1}" -f $entry.Value, $entry.Name)
        }
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

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Add-ValidationError([string] $Message) {
    $errors.Add($Message)
}

function Test-Image {
    param(
        [Parameter(Mandatory)] [string] $RelativePath,
        [Parameter(Mandatory)] [int] $ExpectedWidth,
        [Parameter(Mandatory)] [int] $ExpectedHeight,
        [Parameter(Mandatory)] [ValidateSet('rgb24', 'argb32', 'any')] [string] $ExpectedPixelFormat,
        [long] $MaximumBytes = [long]::MaxValue
    )

    $path = Join-Path $repoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-ValidationError "Missing image: $RelativePath"
        return
    }

    $item = Get-Item -LiteralPath $path
    if ($item.Length -gt $MaximumBytes) {
        Add-ValidationError "$RelativePath is $($item.Length) bytes; maximum is $MaximumBytes."
    }

    $image = [System.Drawing.Image]::FromFile($path)
    try {
        if ($image.Width -ne $ExpectedWidth -or $image.Height -ne $ExpectedHeight) {
            Add-ValidationError "$RelativePath is $($image.Width)x$($image.Height); expected ${ExpectedWidth}x${ExpectedHeight}."
        }

        $actualFormat = $image.PixelFormat.ToString()
        if ($ExpectedPixelFormat -eq 'rgb24' -and $actualFormat -ne 'Format24bppRgb') {
            Add-ValidationError "$RelativePath uses $actualFormat; expected opaque Format24bppRgb."
        }
        if ($ExpectedPixelFormat -eq 'argb32' -and $actualFormat -notin @('Format32bppArgb', 'Format32bppPArgb')) {
            Add-ValidationError "$RelativePath uses $actualFormat; expected 32-bit ARGB PNG."
        }
    }
    finally {
        $image.Dispose()
    }
}

$sourceRelative = 'release\brand\source\approved-artwork.png'
$sourcePath = Join-Path $repoRoot $sourceRelative
$expectedSourceHash = '767DEDCA3FDF794FAF09ED8B6D73C65B7C03EBD3E0391FEEDBF05C01085B785E'
$assetManifestPath = Join-Path $repoRoot 'release\google-play\asset-manifest.json'
$assetManifest = Get-Content -LiteralPath $assetManifestPath -Raw | ConvertFrom-Json
$sha256SumsPath = Join-Path $repoRoot 'release\google-play\evidence\sha256sums.txt'
$sha256SumsContent = Get-Content -LiteralPath $sha256SumsPath -Raw
$defaultLanguagePath = Join-Path $repoRoot 'release\google-play\metadata\default-language.txt'

if ((Get-Content -LiteralPath $defaultLanguagePath -Raw).Trim() -ne 'he-IL') {
    Add-ValidationError 'Default Google Play listing language must be he-IL.'
}

if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    Add-ValidationError "Missing approved source: $sourceRelative"
}
else {
    $actualSourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
    if ($actualSourceHash -ne $expectedSourceHash) {
        Add-ValidationError "Approved source hash changed: $actualSourceHash"
    }
    Test-Image -RelativePath $sourceRelative -ExpectedWidth 1254 -ExpectedHeight 1254 -ExpectedPixelFormat rgb24
}

Test-Image -RelativePath 'release\google-play\graphics\store-icon-512.png' -ExpectedWidth 512 -ExpectedHeight 512 -ExpectedPixelFormat argb32 -MaximumBytes 1048576
Test-Image -RelativePath 'release\google-play\graphics\feature-graphic-1024x500.png' -ExpectedWidth 1024 -ExpectedHeight 500 -ExpectedPixelFormat rgb24 -MaximumBytes 15728640

$launcherSizes = @{
    'mdpi' = 48
    'hdpi' = 72
    'xhdpi' = 96
    'xxhdpi' = 144
    'xxxhdpi' = 192
}

$foregroundSizes = @{
    'mdpi' = 108
    'hdpi' = 162
    'xhdpi' = 216
    'xxhdpi' = 324
    'xxxhdpi' = 432
}

foreach ($density in $launcherSizes.Keys) {
    $size = $launcherSizes[$density]
    $resourceDirectory = "frontend\android\app\src\main\res\mipmap-$density"
    Test-Image -RelativePath "$resourceDirectory\ic_launcher.png" -ExpectedWidth $size -ExpectedHeight $size -ExpectedPixelFormat argb32
    Test-Image -RelativePath "$resourceDirectory\ic_launcher_round.png" -ExpectedWidth $size -ExpectedHeight $size -ExpectedPixelFormat argb32
}

foreach ($density in $foregroundSizes.Keys) {
    $size = $foregroundSizes[$density]
    Test-Image -RelativePath "frontend\android\app\src\main\res\mipmap-$density\ic_launcher_foreground.png" -ExpectedWidth $size -ExpectedHeight $size -ExpectedPixelFormat argb32
}

$splashExports = @(
    @{ Path = 'frontend\android\app\src\main\res\drawable\splash.png'; Width = 480; Height = 320 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-land-mdpi\splash.png'; Width = 480; Height = 320 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-land-hdpi\splash.png'; Width = 800; Height = 480 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-land-xhdpi\splash.png'; Width = 1280; Height = 720 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-land-xxhdpi\splash.png'; Width = 1600; Height = 960 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-land-xxxhdpi\splash.png'; Width = 1920; Height = 1280 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-port-mdpi\splash.png'; Width = 320; Height = 480 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-port-hdpi\splash.png'; Width = 480; Height = 800 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-port-xhdpi\splash.png'; Width = 720; Height = 1280 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-port-xxhdpi\splash.png'; Width = 960; Height = 1600 },
    @{ Path = 'frontend\android\app\src\main\res\drawable-port-xxxhdpi\splash.png'; Width = 1280; Height = 1920 }
)

foreach ($export in $splashExports) {
    Test-Image -RelativePath $export.Path -ExpectedWidth $export.Width -ExpectedHeight $export.Height -ExpectedPixelFormat rgb24
}

foreach ($locale in @('he-IL', 'en-US')) {
    $metadataDirectory = Join-Path $repoRoot "release\google-play\metadata\$locale"
    $metadataLimits = @{
        'title.txt' = 30
        'short-description.txt' = 80
        'full-description.txt' = 4000
        'release-notes.txt' = 500
    }

    foreach ($entry in $metadataLimits.GetEnumerator()) {
        $metadataPath = Join-Path $metadataDirectory $entry.Key
        if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
            Add-ValidationError "Missing metadata: release/google-play/metadata/$locale/$($entry.Key)"
            continue
        }
        $content = (Get-Content -LiteralPath $metadataPath -Raw).Trim()
        if ($content.Length -eq 0) {
            Add-ValidationError "Metadata is empty: release/google-play/metadata/$locale/$($entry.Key)"
        }
        if ($content.Length -gt $entry.Value) {
            Add-ValidationError "Metadata exceeds $($entry.Value) characters: $locale/$($entry.Key) ($($content.Length))."
        }
    }

    $screenshotSet = $assetManifest.screenshotSets | Where-Object { $_.locale -eq $locale }
    $inheritsDefaultSet = $screenshotSet.status -like 'inherits-default-*'
    $screenshotDirectory = Join-Path $repoRoot "release\google-play\graphics\screenshots\phone\$locale"
    $screenshots = @()
    if (Test-Path -LiteralPath $screenshotDirectory -PathType Container) {
        $screenshots = @(
            Get-ChildItem -LiteralPath $screenshotDirectory -File |
                Where-Object { $_.Extension.ToLowerInvariant() -in @('.png', '.jpg', '.jpeg') } |
                Sort-Object Name
        )
    }

    if ($screenshots.Count -eq 0) {
        if ($inheritsDefaultSet) {
            continue
        }
        $warnings.Add("$locale screenshots are pending owner-supplied approved files.")
        continue
    }

    if ($screenshots.Count -lt 2 -or $screenshots.Count -gt 8) {
        Add-ValidationError "$locale has $($screenshots.Count) phone screenshots; Google Play requires 2-8."
    }

    if ($screenshotSet.status -ne 'owner-approved-compliant') {
        Add-ValidationError "$locale screenshot manifest status is '$($screenshotSet.status)'; expected owner-approved-compliant."
    }

    $displayOrder = @($screenshotSet.displayOrder)
    if ($displayOrder.Count -ne $screenshots.Count) {
        Add-ValidationError "$locale asset manifest must contain one displayOrder entry per screenshot."
    }

    $actualRelativePaths = @(
        $screenshots | ForEach-Object {
            $_.FullName.Substring($repoRoot.Length + 1).Replace('\', '/')
        }
    )
    $manifestRelativePaths = @($displayOrder | ForEach-Object { $_.path })
    if (($actualRelativePaths -join "`n") -ne ($manifestRelativePaths -join "`n")) {
        Add-ValidationError "$locale screenshot filenames/order do not match asset-manifest.json."
    }

    foreach ($screenshot in $screenshots) {
        if ($screenshot.Length -gt 8388608) {
            Add-ValidationError "$($screenshot.FullName) exceeds 8 MB."
        }

        $relativePath = $screenshot.FullName.Substring($repoRoot.Length + 1).Replace('\', '/')
        $manifestEntries = @($displayOrder | Where-Object { $_.path -eq $relativePath })
        if ($manifestEntries.Count -ne 1) {
            Add-ValidationError "$relativePath must have exactly one asset-manifest.json entry."
        }

        $image = [System.Drawing.Image]::FromFile($screenshot.FullName)
        try {
            $shortSide = [Math]::Min($image.Width, $image.Height)
            $longSide = [Math]::Max($image.Width, $image.Height)
            if ($shortSide -lt 320 -or $longSide -gt 3840) {
                Add-ValidationError "$($screenshot.Name) is $($image.Width)x$($image.Height); each side must be 320-3840 px."
            }
            if ($longSide -gt (2 * $shortSide)) {
                Add-ValidationError "$($screenshot.Name) exceeds the 2:1 maximum aspect ratio."
            }
            if ($image.PixelFormat.ToString() -ne 'Format24bppRgb') {
                Add-ValidationError "$($screenshot.Name) must use an opaque 24-bit RGB pixel format."
            }

            if ($manifestEntries.Count -eq 1) {
                $manifestEntry = $manifestEntries[0]
                if ($manifestEntry.width -ne $image.Width -or $manifestEntry.height -ne $image.Height) {
                    Add-ValidationError "$relativePath dimensions do not match asset-manifest.json."
                }
                if ($manifestEntry.bytes -ne $screenshot.Length) {
                    Add-ValidationError "$relativePath byte count does not match asset-manifest.json."
                }
            }
        }
        finally {
            $image.Dispose()
        }

        $actualHash = (Get-FileHash -LiteralPath $screenshot.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($manifestEntries.Count -eq 1 -and $manifestEntries[0].sha256.ToLowerInvariant() -ne $actualHash) {
            Add-ValidationError "$relativePath hash does not match asset-manifest.json."
        }
        if (-not $sha256SumsContent.Contains("$actualHash  $relativePath")) {
            Add-ValidationError "$relativePath hash is missing or stale in evidence/sha256sums.txt."
        }
    }

    $duplicateGroups = @(
        $screenshots |
            ForEach-Object {
                [pscustomobject]@{
                    Name = $_.Name
                    Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                }
            } |
            Group-Object Hash |
            Where-Object Count -gt 1
    )

    foreach ($group in $duplicateGroups) {
        $duplicateNames = $group.Group.Name -join ', '
        $warnings.Add("$locale contains byte-identical screenshots: $duplicateNames")
    }

    $altTextPath = Join-Path $metadataDirectory 'screenshot-alt-text.yml'
    $altTextContent = Get-Content -LiteralPath $altTextPath -Raw
    $filenameEntries = @([regex]::Matches($altTextContent, '(?m)^\s*-\s*filename:\s*.+$'))
    $altTextEntries = @([regex]::Matches($altTextContent, '(?m)^\s*alt_text:\s*\S.+$'))

    if ($filenameEntries.Count -ne $screenshots.Count -or $altTextEntries.Count -ne $screenshots.Count) {
        Add-ValidationError "$locale screenshot alt-text manifest must contain one non-empty filename and alt_text entry per screenshot."
    }

    foreach ($screenshot in $screenshots) {
        if (-not $altTextContent.Contains($screenshot.Name)) {
            Add-ValidationError "$locale alt-text manifest does not reference $($screenshot.Name)."
        }
    }

    $altTextFilenames = @(
        [regex]::Matches($altTextContent, '(?m)^\s*-\s*filename:\s*(.+?)\s*$') |
            ForEach-Object { $_.Groups[1].Value }
    )
    if (($altTextFilenames -join "`n") -ne (($screenshots.Name) -join "`n")) {
        Add-ValidationError "$locale screenshot alt-text filenames/order do not match the official screenshot set."
    }
}

if ($warnings.Count -gt 0) {
    Write-Host 'Warnings:' -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "- $_" -ForegroundColor Yellow }
}

if ($errors.Count -gt 0) {
    Write-Host 'Validation failed:' -ForegroundColor Red
    $errors | ForEach-Object { Write-Host "- $_" -ForegroundColor Red }
    exit 1
}

Write-Host 'Google Play and Android asset validation passed.' -ForegroundColor Green

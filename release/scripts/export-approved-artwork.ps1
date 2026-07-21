[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sourcePath = Join-Path $repoRoot 'release\brand\source\approved-artwork.png'

if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Approved source artwork is missing: $sourcePath"
}

function Export-CoverPng {
    param(
        [Parameter(Mandatory)]
        [System.Drawing.Image] $Source,

        [Parameter(Mandatory)]
        [string] $RelativePath,

        [Parameter(Mandatory)]
        [int] $Width,

        [Parameter(Mandatory)]
        [int] $Height,

        [System.Drawing.Imaging.PixelFormat] $PixelFormat = [System.Drawing.Imaging.PixelFormat]::Format24bppRgb,

        [switch] $RoundMask
    )

    $targetPath = Join-Path $repoRoot $RelativePath
    $targetDirectory = Split-Path -Parent $targetPath
    New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null

    $sourceAspect = $Source.Width / $Source.Height
    $targetAspect = $Width / $Height

    if ($sourceAspect -gt $targetAspect) {
        $cropHeight = [double]$Source.Height
        $cropWidth = $cropHeight * $targetAspect
        $cropX = ($Source.Width - $cropWidth) / 2
        $cropY = 0
    }
    else {
        $cropWidth = [double]$Source.Width
        $cropHeight = $cropWidth / $targetAspect
        $cropX = 0
        $cropY = ($Source.Height - $cropHeight) / 2
    }

    $bitmap = [System.Drawing.Bitmap]::new($Width, $Height, $PixelFormat)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $clipPath = $null

    try {
        $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality

        if ($RoundMask) {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $clipPath = [System.Drawing.Drawing2D.GraphicsPath]::new()
            $clipPath.AddEllipse(0, 0, $Width, $Height)
            $graphics.SetClip($clipPath)
        }

        $destination = [System.Drawing.Rectangle]::new(0, 0, $Width, $Height)
        $graphics.DrawImage(
            $Source,
            $destination,
            [single]$cropX,
            [single]$cropY,
            [single]$cropWidth,
            [single]$cropHeight,
            [System.Drawing.GraphicsUnit]::Pixel
        )

        $bitmap.SetResolution(72, 72)
        $bitmap.Save($targetPath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        if ($null -ne $clipPath) {
            $clipPath.Dispose()
        }
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

$source = [System.Drawing.Image]::FromFile($sourcePath)

try {
    if ($source.Width -ne 1254 -or $source.Height -ne 1254) {
        throw "Approved source dimensions changed. Expected 1254x1254, found $($source.Width)x$($source.Height)."
    }

    # Google Play graphics: deterministic center crop/resize only.
    Export-CoverPng -Source $source -RelativePath 'release\google-play\graphics\store-icon-512.png' -Width 512 -Height 512 -PixelFormat Format32bppArgb
    Export-CoverPng -Source $source -RelativePath 'release\google-play\graphics\feature-graphic-1024x500.png' -Width 1024 -Height 500 -PixelFormat Format24bppRgb

    # Android legacy and adaptive launcher resources.
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
        Export-CoverPng -Source $source -RelativePath "$resourceDirectory\ic_launcher.png" -Width $size -Height $size -PixelFormat Format32bppArgb
        Export-CoverPng -Source $source -RelativePath "$resourceDirectory\ic_launcher_round.png" -Width $size -Height $size -PixelFormat Format32bppArgb -RoundMask
    }

    foreach ($density in $foregroundSizes.Keys) {
        $size = $foregroundSizes[$density]
        $resourceDirectory = "frontend\android\app\src\main\res\mipmap-$density"
        Export-CoverPng -Source $source -RelativePath "$resourceDirectory\ic_launcher_foreground.png" -Width $size -Height $size -PixelFormat Format32bppArgb
    }

    # Existing Capacitor splash matrix. Each export is a full-bleed center crop.
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
        Export-CoverPng -Source $source -RelativePath $export.Path -Width $export.Width -Height $export.Height -PixelFormat Format24bppRgb
    }
}
finally {
    $source.Dispose()
}

Write-Host 'Approved artwork exports completed.'

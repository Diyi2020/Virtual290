# Virtual290 - minimal static file server.
# Last-resort launcher for Windows machines with no Python and no Node.
# PowerShell ships with every Windows install, so this always works.
# Binding http://localhost:<port>/ does NOT require administrator rights.

param([int]$Port = 8731)

$root = $PSScriptRoot
$url  = "http://localhost:$Port/m0-board-spike.html"

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
try { $listener.Start() }
catch {
  Write-Host ""
  Write-Host "  Could not open port $Port - something else may be using it."
  Write-Host "  You can still double-click m0-board-spike.html; only the microphone will be unavailable."
  Write-Host ""
  Read-Host "  Press Enter to close"
  exit 1
}

Write-Host ""
Write-Host "  Virtual290 - board spike"
Write-Host "  Serving at $url"
Write-Host "  Leave this window open. Press Ctrl-C when you're done."
Write-Host ""
Start-Process $url

$mime = @{
  ".html"="text/html; charset=utf-8"; ".htm"="text/html; charset=utf-8"
  ".js"="application/javascript";     ".css"="text/css"
  ".woff2"="font/woff2";              ".woff"="font/woff";  ".ttf"="font/ttf"
  ".svg"="image/svg+xml";             ".png"="image/png";   ".jpg"="image/jpeg"
  ".json"="application/json";         ".md"="text/plain; charset=utf-8"
}
$rootFull = [System.IO.Path]::GetFullPath($root)

while ($listener.IsListening) {
  try {
    $ctx = $listener.GetContext()
    $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
    if ([string]::IsNullOrWhiteSpace($rel)) { $rel = "m0-board-spike.html" }

    $full = [System.IO.Path]::GetFullPath((Join-Path $root $rel))
    if ($full.StartsWith($rootFull) -and (Test-Path -LiteralPath $full -PathType Leaf)) {
      $ext = [System.IO.Path]::GetExtension($full).ToLower()
      $ctx.Response.ContentType = $(if ($mime.ContainsKey($ext)) { $mime[$ext] } else { "application/octet-stream" })
      $bytes = [System.IO.File]::ReadAllBytes($full)
      $ctx.Response.ContentLength64 = $bytes.Length
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
      $ctx.Response.StatusCode = 404
    }
    $ctx.Response.Close()
  } catch { }
}

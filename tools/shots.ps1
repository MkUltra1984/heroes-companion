# Screenshots of the local site with headless Chrome, plus the page's console errors.
# usage: tools\shots.ps1 <output folder> name route width,height [name route width,height]...
# needs the local server: python -I -m http.server 8765 --bind 127.0.0.1 --directory site
param([string]$out)
$chrome = @("C:\Program Files\Google\Chrome\Application\chrome.exe", "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
for ($i = 0; $i + 2 -lt $args.Count + 1; $i += 3) {
  $name = $args[$i]; $route = $args[$i + 1]; $size = $args[$i + 2]
  $p = Start-Process $chrome -ArgumentList '--headless=new', '--disable-gpu', '--hide-scrollbars', "--user-data-dir=`"$out\chromeprof`"", "--window-size=$size", '--enable-logging=stderr', '--virtual-time-budget=8000', "--screenshot=`"$out\$name.png`"", "`"http://127.0.0.1:8765/index.html$route`"" -PassThru -WindowStyle Hidden -RedirectStandardError "$out\$name.err"
  $p.WaitForExit(45000) | Out-Null
  $errs = Select-String -Path "$out\$name.err" -Pattern 'CONSOLE' | ForEach-Object { $_.Line -replace '^.*CONSOLE:\d+\] ', '' }
  "$name" + $(if ($errs) { '  ERRORS: ' + ($errs -join ' | ') } else { '  ok' })
}

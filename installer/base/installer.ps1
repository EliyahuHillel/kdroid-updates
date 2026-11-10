# Kiydroid PC installer: installs the app on a phone over USB and turns on device management.
# Works with no internet at all: adb and the app (with the installer's details inside) come in this folder.
# After a successful install it erases itself from the computer. Runs on Windows PowerShell 5.1 (Windows 10/11).
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pkg  = 'com.kdroid.filter'
$Adb  = Join-Path $Here 'adb\adb.exe'
$Apk  = Join-Path $Here 'kiydroid.apk'
$Info = @{ fid = ''; version = ''; installer = '' }
try { $j = Get-Content -Raw -Encoding UTF8 (Join-Path $Here 'installer.json') | ConvertFrom-Json; $Info.fid = "$($j.fid)"; $Info.version = "$($j.version)"; $Info.installer = "$($j.installer)" } catch {}
# adb keeps its key in %USERPROFILE%\.android. If that folder was not there before, it goes away with the installer.
$AndroidDir = Join-Path $env:USERPROFILE '.android'
$HadAndroidDir = Test-Path $AndroidDir

# The same activation command the app runs in its own setup (Activator.ACTIVATE_ALL):
# account apps are paused for a moment so device management can be turned on, then restored.
$Activate = @'
A=$(cmd package query-services -a android.accounts.AccountAuthenticator | grep packageName | cut -d '=' -f 2 | tr -d '\r' | sort -u | grep -viE 'bluetooth|telecom|telephony|dialer|contacts|phonebook|calendar|carservice|car.')
echo "$A" | sed 's/^/pm disable-user --user 0 /' | sh
sleep 3
dpm set-device-owner com.kdroid.filter/.listener.AdminListener
appops set com.kdroid.filter ACTIVATE_VPN allow
pm grant com.kdroid.filter android.permission.POST_NOTIFICATIONS
appops set com.kdroid.filter SYSTEM_ALERT_WINDOW allow
appops set com.kdroid.filter GET_USAGE_STATS allow
echo "$A" | sed 's/^/pm enable /' | sh
pm enable com.google.android.gms
pm enable com.google.android.gsf
pm enable com.android.vending
'@

# ------------------------------------------------------------------ window
$Green = [System.Drawing.Color]::FromArgb(0, 108, 81)
$Muted = [System.Drawing.Color]::FromArgb(64, 73, 68)
$Bg    = [System.Drawing.Color]::FromArgb(251, 253, 249)

$form = New-Object System.Windows.Forms.Form
$form.Text = 'התקנת קיידרואיד'
$form.Size = New-Object System.Drawing.Size(620, 700)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.RightToLeft = 'Yes'
$form.RightToLeftLayout = $true
$form.BackColor = $Bg
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'התקנת קיידרואיד בטלפון'
$title.Font = New-Object System.Drawing.Font('Segoe UI', 17, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = $Green
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(24, 18)
$form.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$parts = @()
if ($Info.installer) { $parts += ('מתקין: ' + $Info.installer) }
if ($Info.fid) { $parts += ('קובץ ' + $Info.fid) }
if ($Info.version) { $parts += ('גרסה ' + $Info.version) }
$sub.Text = ($parts -join '  ·  ')
$sub.ForeColor = $Muted
$sub.AutoSize = $true
$sub.Location = New-Object System.Drawing.Point(26, 56)
$form.Controls.Add($sub)

$steps = New-Object System.Windows.Forms.Label
$steps.Text = "לפני שמתחילים, בטלפון:`r`n" +
  "1. הגדרות ← אודות הטלפון ← הקישו 7 פעמים על 'מספר גרסה', עד שמופיע 'אתה מפתח'.`r`n" +
  "2. הגדרות ← אפשרויות מפתח ← הפעילו 'ניפוי באגים ב-USB'.`r`n" +
  "3. חברו את הטלפון למחשב בכבל, ואשרו בטלפון את ההודעה 'לאפשר ניפוי באגים'.`r`n" +
  "אחר כך לחצו 'התקן'. אין צורך באינטרנט."
$steps.ForeColor = $Muted
$steps.Location = New-Object System.Drawing.Point(24, 84)
$steps.Size = New-Object System.Drawing.Size(560, 112)
$form.Controls.Add($steps)

$onlyInstall = New-Object System.Windows.Forms.CheckBox
$onlyInstall.Text = 'להתקין בלבד, בלי להפעיל ניהול מכשיר'
$onlyInstall.ForeColor = $Muted
$onlyInstall.AutoSize = $true
$onlyInstall.Location = New-Object System.Drawing.Point(24, 200)
$form.Controls.Add($onlyInstall)

$go = New-Object System.Windows.Forms.Button
$go.Text = 'התקן'
$go.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$go.BackColor = $Green
$go.ForeColor = [System.Drawing.Color]::White
$go.FlatStyle = 'Flat'
$go.FlatAppearance.BorderSize = 0
$go.Size = New-Object System.Drawing.Size(560, 46)
$go.Location = New-Object System.Drawing.Point(24, 232)
$form.Controls.Add($go)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'מוכן להתקנה.'
$status.Font = New-Object System.Drawing.Font('Segoe UI', 11, [System.Drawing.FontStyle]::Bold)
$status.Location = New-Object System.Drawing.Point(24, 292)
$status.Size = New-Object System.Drawing.Size(560, 26)
$form.Controls.Add($status)

$log = New-Object System.Windows.Forms.RichTextBox
$log.ReadOnly = $true
$log.RightToLeft = 'Yes'
$log.BackColor = [System.Drawing.Color]::White
$log.BorderStyle = 'FixedSingle'
$log.Location = New-Object System.Drawing.Point(24, 324)
$log.Size = New-Object System.Drawing.Size(560, 320)
$form.Controls.Add($log)

function Pump { [System.Windows.Forms.Application]::DoEvents() }
function Say([string]$text, [string]$color = 'black') {
  $log.SelectionStart = $log.TextLength
  $log.SelectionColor = [System.Drawing.Color]::FromName($color)
  $log.AppendText($text + "`r`n")
  $log.ScrollToCaret()
  Pump
}
function Step([string]$text) { $status.ForeColor = $Green; $status.Text = $text; Say ('• ' + $text) 'DarkGreen' }
function Fail([string]$text) { $status.ForeColor = [System.Drawing.Color]::Firebrick; $status.Text = 'ההתקנה לא הושלמה'; Say $text 'Firebrick'; throw 'stop' }

# ------------------------------------------------------------------ helpers
function Run([string]$exe, [string]$arguments, [int]$timeoutSec = 180) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $exe
  $psi.Arguments = $arguments
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($psi)
  $outTask = $p.StandardOutput.ReadToEndAsync()
  $errTask = $p.StandardError.ReadToEndAsync()
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  while (-not $p.HasExited) {
    Start-Sleep -Milliseconds 100; Pump
    if ($sw.Elapsed.TotalSeconds -gt $timeoutSec) { try { $p.Kill() } catch {}; return @{ Code = -1; Out = 'timeout' } }
  }
  return @{ Code = $p.ExitCode; Out = ($outTask.Result + $errTask.Result).Trim() }
}

function Check-Files {
  if (-not (Test-Path $Adb) -or -not (Test-Path $Apk)) {
    Fail ("חסרים קבצים בתיקייה. כנראה שהקובץ נפתח בלי לחלץ אותו.`r`n" +
          "סגרו את החלון, לחצו לחיצה ימנית על קובץ ה-ZIP ← 'חלץ הכל', ופתחו את 'Install-Kiydroid' מהתיקייה שנוצרה.")
  }
}

function Wait-Device {
  Step 'מחפש טלפון מחובר…'
  Run $Adb 'start-server' 60 | Out-Null
  $warned = $false
  for ($i = 0; $i -lt 120; $i++) {
    $r = Run $Adb 'devices' 20
    $lines = @($r.Out -split "`n" | Where-Object { $_ -match "`t" })
    $ready = @($lines | Where-Object { $_ -match "`tdevice\s*$" })
    if ($ready.Count -gt 1) { Fail 'מחוברים כמה מכשירים. השאירו מחובר רק את הטלפון שמתקינים בו ונסו שוב.' }
    if ($ready.Count -eq 1) { Say 'הטלפון מחובר.'; return }
    if (-not $warned -and ($lines -match 'unauthorized')) {
      Say 'בטלפון מופיעה הודעה "לאפשר ניפוי באגים?". סמנו "אפשר תמיד מהמחשב הזה" ולחצו "אישור".' 'DarkOrange'; $warned = $true
    }
    Start-Sleep -Milliseconds 500; Pump
  }
  Fail ("לא נמצא טלפון מחובר.`r`n" +
        "• בדקו שהכבל מעביר נתונים (לא רק טעינה) ושניפוי באגים ב-USB פעיל.`r`n" +
        "• בחלק מהטלפונים צריך להתקין במחשב את מנהל ההתקן (Driver) של היצרן.")
}

function Is-Owner {
  $r = Run $Adb 'shell dpm list-owners' 30
  if ($r.Out -match '(?im)^\s*(\d+ owners?:|no owners)') { return ($r.Out -match ('(?m)' + [regex]::Escape($Pkg) + '.*DeviceOwner')) }
  $r = Run $Adb 'shell dumpsys device_policy' 60
  return ($r.Out -match ('Device Owner:\s*\r?\n\s*admin=ComponentInfo\{' + [regex]::Escape($Pkg) + '/'))
}

# ------------------------------------------------------------------ erase after a successful install
$script:Done = $false
function Erase-Self {
  try { Run $Adb 'kill-server' 20 | Out-Null } catch {}
  if (-not $HadAndroidDir) { try { Remove-Item -Recurse -Force $AndroidDir -ErrorAction SilentlyContinue } catch {} }
  # leftovers of the older installer that downloaded into the user's profile
  try { Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA 'Kiydroid') -ErrorAction SilentlyContinue } catch {}
  # the zip this folder came from (downloads, desktop, documents)
  if ($Info.fid) {
    foreach ($d in @((Join-Path $env:USERPROFILE 'Downloads'), [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('MyDocuments'), (Split-Path -Parent $Here))) {
      try { Get-ChildItem -Path $d -Filter ('Kiydroid-Installer-' + $Info.fid + '*.zip') -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
  # this folder: removed by a small detached command once this window and its batch file have closed
  $cmd = 'ping -n 4 127.0.0.1 >nul & rd /s /q "' + $Here + '"'
  Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ' + $cmd) -WindowStyle Hidden -WorkingDirectory $env:TEMP
}

# ------------------------------------------------------------------ install
function Install-All {
  $log.Clear()
  $script:t0 = [DateTime]::Now
  Check-Files
  Wait-Device

  $model = (Run $Adb 'shell getprop ro.product.model' 20).Out
  $sdk = (Run $Adb 'shell getprop ro.build.version.sdk' 20).Out
  Say ("מכשיר: " + $model + " · אנדרואיד API " + $sdk)

  Step 'מתקין את קיידרואיד בטלפון…'
  $r = Run $Adb ('install -r -g "' + $Apk + '"') 300
  if ($r.Out -notmatch 'Success') {
    if ($r.Out -match 'UPDATE_INCOMPATIBLE|SIGNATURES') {
      Fail ("בטלפון מותקנת גרסה אחרת של קיידרואיד, שחתומה אחרת. צריך להסיר אותה קודם.`r`n" +
            "אם ההסרה חסומה (ניהול מכשיר פעיל), שחררו את המכשיר מהפאנל או בקוד חירום, ואז הסירו.`r`n" + $r.Out)
    }
    if ($r.Out -match 'VERSION_DOWNGRADE') { Fail ("בטלפון מותקנת כבר גרסה חדשה יותר. אין צורך להתקין.`r`n" + $r.Out) }
    if ($r.Out -match 'INSUFFICIENT_STORAGE') { Fail 'אין מספיק מקום פנוי בטלפון.' }
    Fail ("ההתקנה נכשלה:`r`n" + $r.Out)
  }
  Say 'האפליקציה הותקנה.'

  if (-not $onlyInstall.Checked) {
    if (Is-Owner) {
      Say 'ניהול המכשיר כבר פעיל. אין צורך להפעיל שוב.'
    } else {
      Step 'מפעיל ניהול מכשיר ונותן הרשאות…'
      $sh = Join-Path $env:TEMP ('kd-activate-' + [guid]::NewGuid().ToString('N') + '.sh')
      [IO.File]::WriteAllText($sh, ($Activate -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
      Run $Adb ('push "' + $sh + '" /data/local/tmp/kd-activate.sh') 60 | Out-Null
      Remove-Item -Force $sh -ErrorAction SilentlyContinue
      $r = Run $Adb 'shell sh /data/local/tmp/kd-activate.sh' 180
      Run $Adb 'shell rm -f /data/local/tmp/kd-activate.sh' 30 | Out-Null
      $dpmLine = @($r.Out -split "`n" | Where-Object { $_ -match 'Success|Error|Exception|Not allowed|already' }) -join "`r`n"
      if ($dpmLine) { Say ('תשובת המכשיר: ' + $dpmLine.Trim()) 'DimGray' }
      if (-not (Is-Owner)) {
        if ($r.Out -match 'already some accounts|accounts on the device') {
          Fail ("לא ניתן להפעיל ניהול מכשיר כי יש בטלפון חשבונות שלא ניתן להשהות.`r`n" +
                "הסירו את החשבונות (הגדרות ← חשבונות), לחצו שוב 'התקן', ואחר כך אפשר להוסיף אותם בחזרה.")
        }
        if ($r.Out -match 'several users|already provisioned|is already set|device owner is already') {
          Fail ("לא ניתן להפעיל ניהול מכשיר: בטלפון יש משתמש נוסף, פרופיל עבודה, או אפליקציית ניהול אחרת.`r`n" + $r.Out)
        }
        Fail ("הפעלת ניהול המכשיר נכשלה:`r`n" + $r.Out)
      }
      Say 'ניהול המכשיר הופעל.'
    }
  }

  Step 'פותח את קיידרואיד בטלפון…'
  Run $Adb ('shell am start -n ' + $Pkg + '/.MainActivity') 30 | Out-Null
  $status.ForeColor = $Green
  $status.Text = 'ההתקנה הושלמה ✓  (' + [int]([DateTime]::Now - $script:t0).TotalSeconds + ' שניות)'
  Say ''
  Say 'ההתקנה הושלמה. המשיכו בטלפון: פרטי המכשיר, הגדרות החסימה, ונעילה.' 'DarkGreen'
  Say 'מומלץ לכבות עכשיו את ניפוי הבאגים ב-USB. קיידרואיד גם יחסום אותו בעצמו לאחר הנעילה.' 'DimGray'
  Say 'תוכנת ההתקנה תימחק מהמחשב כשתסגרו את החלון.' 'DimGray'
  $script:Done = $true
}

$go.Add_Click({
  if ($script:Done) { $form.Close(); return }
  $go.Enabled = $false; $onlyInstall.Enabled = $false
  try { Install-All } catch { if ("$_" -ne 'stop') { $status.ForeColor = [System.Drawing.Color]::Firebrick; $status.Text = 'ההתקנה לא הושלמה'; Say ('שגיאה: ' + $_) 'Firebrick' } }
  if ($script:Done) { $go.Text = 'סיום'; $go.Enabled = $true }
  else { $go.Text = 'התקן שוב'; $go.Enabled = $true; $onlyInstall.Enabled = $true }
})
$form.Add_FormClosed({ if ($script:Done) { Erase-Self } else { try { Run $Adb 'kill-server' 20 | Out-Null } catch {} } })

[void]$form.ShowDialog()

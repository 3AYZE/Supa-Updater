"""Windows Update Agent: optional driver discovery and explicitly approved installation."""
import json, subprocess, sys

SEARCH = r'''
$ErrorActionPreference='Stop'
$s=New-Object -ComObject Microsoft.Update.Session
$q=$s.CreateUpdateSearcher()
$r=$q.Search("IsInstalled=0 and IsHidden=0 and Type='Driver'")
$a=@(for($i=0;$i -lt $r.Updates.Count;$i++){
 $u=$r.Updates.Item($i)
 [pscustomobject]@{id=$u.Identity.UpdateID; revision=$u.Identity.RevisionNumber; title=$u.Title; size=$u.MaxDownloadSize; reboot=$u.RebootRequired; eula=$u.EulaAccepted}
})
ConvertTo-Json -InputObject $a -Depth 4 -Compress
'''
INSTALL = r'''
param([string]$UpdateId,[int]$Revision)
$ErrorActionPreference='Stop'
$s=New-Object -ComObject Microsoft.Update.Session
$r=$s.CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0 and Type='Driver'")
$c=New-Object -ComObject Microsoft.Update.UpdateColl
for($i=0;$i -lt $r.Updates.Count;$i++){
 $u=$r.Updates.Item($i)
 if($u.Identity.UpdateID -eq $UpdateId -and $u.Identity.RevisionNumber -eq $Revision){
  if(-not $u.EulaAccepted){$u.AcceptEula()}
  [void]$c.Add($u);break
 }
}
if($c.Count -ne 1){throw 'Driver update is no longer offered; rescan first.'}
$d=$s.CreateUpdateDownloader();$d.Updates=$c;$dr=$d.Download()
if($dr.ResultCode -ne 2){throw ('Download failed: result '+$dr.ResultCode)}
$installer=$s.CreateUpdateInstaller();$installer.Updates=$c;$result=$installer.Install()
[pscustomobject]@{result=[int]$result.ResultCode;hresult=[string]$result.HResult;reboot=[bool]$result.RebootRequired} | ConvertTo-Json -Compress
if($result.ResultCode -notin @(2,3)){exit 2}
'''

def _run(script, args=(), timeout=180):
    if sys.platform!='win32':raise RuntimeError('Windows only')
    import base64
    encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded,*args],capture_output=True,text=True,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
    if p.returncode:raise RuntimeError((p.stderr or p.stdout or 'Windows Update operation failed')[-1200:])
    return p.stdout.strip()

def parse_updates(raw):
    rows=json.loads(raw) if raw else []
    if isinstance(rows,dict):rows=[rows]
    result=[]; seen=set()
    for row in rows:
        identity=(str(row['id']),int(row['revision']))
        if identity in seen:continue
        seen.add(identity)
        result.append({'id':identity[0],'revision':identity[1],'title':str(row['title']),'size':int(row.get('size') or 0),'reboot':bool(row.get('reboot')),'eula':bool(row.get('eula'))})
    return result

def find_driver_updates():return parse_updates(_run(SEARCH,timeout=180))

def install_driver_update(update):
    import re
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',update['id']):raise ValueError('Invalid Windows Update ID')
    revision=int(update['revision'])
    if revision<0:raise ValueError('Invalid revision')
    result=json.loads(_run(INSTALL,( '-UpdateId',update['id'],'-Revision',str(revision)),timeout=2400))
    return result
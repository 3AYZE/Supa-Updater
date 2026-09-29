"""Read-only Windows driver inventory. Never downloads or installs driver packages."""
import json, subprocess, sys

def classify(name):
    name=name.casefold()
    for label,words in [('Bluetooth',('bluetooth',)),('Network',('wi-fi','wireless','ethernet','network','802.11')),('Graphics',('display','graphics','geforce','radeon')),('Audio',('audio','sound','realtek high definition')),('Chipset',('chipset','smbus','serial io'))]:
        if any(word in name for word in words):return label
    return 'Other'

def parse_drivers(data):
    if not data:return []
    records=json.loads(data)
    if isinstance(records,dict):records=[records]
    result=[]; seen=set()
    for row in records:
        name=str(row.get('DeviceName') or '').strip()
        if not name:continue
        key=(str(row.get('DeviceID') or ''),str(row.get('DriverVersion') or ''))
        if key in seen:continue
        seen.add(key)
        result.append({'category':classify(name),'name':name,'version':str(row.get('DriverVersion') or 'Unknown'),'provider':str(row.get('DriverProviderName') or 'Unknown'),'date':str(row.get('DriverDate') or '')[:10]})
    return sorted(result,key=lambda x:(x['category'],x['name']))

def scan_drivers(timeout=90):
    if sys.platform!='win32':raise RuntimeError('Driver inventory requires Windows')
    command='Get-CimInstance Win32_PnPSignedDriver | Select-Object DeviceID,DeviceName,DriverVersion,DriverProviderName,DriverDate | ConvertTo-Json -Depth 3 -Compress'
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise RuntimeError((p.stderr or 'PowerShell driver scan failed')[:500])
    return parse_drivers(p.stdout)
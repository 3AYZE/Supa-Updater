"""Read-only Windows driver inventory. Never downloads or installs driver packages."""
import json, subprocess, sys, re

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
        result.append({'category':classify(name),'name':name,'version':str(row.get('DriverVersion') or 'Unknown'),'provider':str(row.get('DriverProviderName') or 'Unknown'),'date':str(row.get('DriverDate') or '')[:10], 'device_id':str(row.get('DeviceID') or ''), 'inf':str(row.get('InfName') or ''), 'manufacturer':str(row.get('Manufacturer') or '')})
    return sorted(result,key=lambda x:(x['category'],x['name']))

def scan_drivers(timeout=90):
    if sys.platform!='win32':raise RuntimeError('Driver inventory requires Windows')
    command='Get-CimInstance Win32_PnPSignedDriver | Select-Object DeviceID,DeviceName,DriverVersion,DriverProviderName,DriverDate,InfName,Manufacturer | ConvertTo-Json -Depth 3 -Compress'
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise RuntimeError((p.stderr or 'PowerShell driver scan failed')[:500])
    return parse_drivers(p.stdout)

def vendor_support(driver):
    """Conservative official support links; never infer an update exists."""
    s=' '.join(str(driver.get(k,'')).casefold() for k in ('provider','manufacturer','name','device_id'))
    vendors=[
      (('nvidia','ven_10de'),'NVIDIA','https://www.nvidia.com/en-us/software/nvidia-app/'),
      (('advanced micro devices','amd','ven_1002'),'AMD','https://www.amd.com/en/support/download/drivers.html'),
      (('intel','ven_8086'),'Intel','https://www.intel.com/content/www/us/en/support/detect.html'),
      (('realtek','ven_10ec'),'Realtek','https://www.realtek.com/Download'),
      (('broadcom','ven_14e4'),'Broadcom','https://www.broadcom.com/support'),
      (('qualcomm','ven_168c','ven_17cb'),'Qualcomm','https://www.qualcomm.com/support'),
      (('dell','alienware'),'Dell','https://www.dell.com/support/home/en-us?app=drivers'),
      (('lenovo',),'Lenovo','https://pcsupport.lenovo.com/'),
      (('asus','asustek'),'ASUS','https://www.asus.com/support/download-center/'),
      (('hp inc','hewlett-packard','hewlett packard'),'HP','https://support.hp.com/us-en/drivers'),
    ]
    for keys,name,url in vendors:
        if any(re.search(r'(?<![a-z])'+re.escape(k)+r'(?![a-z])',s) for k in keys):
            return {'vendor':name,'url':url,'status':'Official vendor check available; update not verified'}
    return {'vendor':'Unknown','url':'','status':'No verified vendor source identified'}

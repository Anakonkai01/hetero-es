"""Fixed, bounded native Windows observations. No driver installs or process arguments."""
import json
import math
import subprocess
import time

SCRIPT=r'''
$ErrorActionPreference='Stop'
function Q($class,$properties) {try { @(Get-CimInstance -ClassName $class -Property $properties -OperationTimeoutSec 1 | Select-Object -Property $properties) } catch { @() }}
$os=Q 'Win32_OperatingSystem' @('TotalVisibleMemorySize','FreePhysicalMemory','LastBootUpTime')
$cpu=Q 'Win32_Processor' @('Name')
$cores=Q 'Win32_PerfFormattedData_PerfOS_Processor' @('Name','PercentProcessorTime')
$network=try { @(Get-NetAdapterStatistics | Select-Object -First 32 -Property Name,ReceivedBytes,SentBytes) } catch { @() }
$disk=Q 'Win32_PerfRawData_PerfDisk_PhysicalDisk' @('Name','DiskReadBytesPerSec','DiskWriteBytesPerSec','CurrentDiskQueueLength')
$process=Q 'Win32_PerfFormattedData_PerfProc_Process' @('Name','IDProcess','PercentProcessorTime','WorkingSet','ThreadCount')
$process=@($process | Where-Object {$_.IDProcess -gt 0 -and $_.Name -ne '_Total'} | Sort-Object -Property PercentProcessorTime -Descending | Select-Object -First 20)
$memory=Q 'Win32_PerfFormattedData_PerfOS_Memory' @('CacheBytes')
$page=Q 'Win32_PageFileUsage' @('AllocatedBaseSize','CurrentUsage')
$thermal=try { @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -Property InstanceName,CurrentTemperature -OperationTimeoutSec 1 | Select-Object -First 32 -Property InstanceName,CurrentTemperature) } catch { @() }
$uptime=if($os.Count -gt 0){([datetime]::UtcNow-$os[0].LastBootUpTime.ToUniversalTime()).TotalSeconds}else{$null}
@{os=$os;cpu=$cpu;cores=@($cores|Select-Object -First 513);network=$network;disk=@($disk|Select-Object -First 33);process=$process;memory=$memory;page=$page;thermal=$thermal;uptime=$uptime}|ConvertTo-Json -Depth 4 -Compress
'''


def number(value):
    try:
        result=float(value)
        return result if math.isfinite(result) and result>=0 else None
    except (TypeError,ValueError):return None


def rows(value):
    return value if isinstance(value,list) else [value] if isinstance(value,dict) else []


class WindowsDetail:
    def __init__(self,runner=subprocess.run,clock=time.monotonic):
        self.runner=runner;self.clock=clock;self.previous={};self.tick=None

    def sample(self):
        response=self.runner(['powershell.exe','-NoProfile','-NonInteractive','-Command',SCRIPT],capture_output=True,text=True,timeout=8,check=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if len(response.stdout)>500_000:raise ValueError('Windows observation exceeds its bound')
        return self.normalize(json.loads(response.stdout))

    def normalize(self,raw):
        now=self.clock();dt=now-self.tick if self.tick is not None else None
        result={'cores':[],'networkInterfaces':[],'blockDevices':[],'processes':[],'sensors':[]}
        os_rows=rows(raw.get('os'))
        if os_rows:
            total=number(os_rows[0].get('TotalVisibleMemorySize'));free=number(os_rows[0].get('FreePhysicalMemory'))
            if total is not None and free is not None and total>=free:
                result.update(ramTotalBytes=int(total*1024),ramUsedBytes=int((total-free)*1024),ramAvailableBytes=int(free*1024))
        cpus=rows(raw.get('cpu'))
        if cpus:result['cpuModel']=str(cpus[0].get('Name','Unknown'))[:200]
        uptime=number(raw.get('uptime'))
        if uptime is not None:result['uptimeSeconds']=uptime
        for row in rows(raw.get('cores'))[:513]:
            name=str(row.get('Name',''));percent=number(row.get('PercentProcessorTime'))
            if name=='_Total':
                if percent is not None:result['cpuPercent']=min(percent,100)
            elif name.isdigit():result['cores'].append({'id':'cpu'+name,'utilizationPercent':None if percent is None else min(percent,100)})
        result['cores']=result['cores'][:512]
        current={}
        for group,read_key,write_key,target,prefix in [('network','ReceivedBytes','SentBytes','networkInterfaces','net'),('disk','DiskReadBytesPerSec','DiskWriteBytesPerSec','blockDevices','disk')]:
            for row in rows(raw.get(group))[:33]:
                name=str(row.get('Name',''))[:100]
                read=number(row.get(read_key));write=number(row.get(write_key))
                if not name or name=='_Total' or read is None or write is None:continue
                key=(prefix,name);prior=self.previous.get(key)
                item={'name':name,('rxBytes' if prefix=='net' else 'readBytes'):int(read),('txBytes' if prefix=='net' else 'writtenBytes'):int(write)}
                if prefix=='disk':item['inFlight']=int(number(row.get('CurrentDiskQueueLength')) or 0)
                if prior and dt and dt>0 and read>=prior[0] and write>=prior[1]:
                    item['rxBytesPerSecond' if prefix=='net' else 'readBytesPerSecond']=(read-prior[0])/dt
                    item['txBytesPerSecond' if prefix=='net' else 'writeBytesPerSecond']=(write-prior[1])/dt
                result[target].append(item);current[key]=(read,write)
            result[target]=result[target][:32]
        for row in rows(raw.get('process'))[:20]:
            pid=number(row.get('IDProcess'));ram=number(row.get('WorkingSet'));threads=number(row.get('ThreadCount'))
            if pid and ram is not None and threads is not None:
                result['processes'].append({'pid':int(pid),'name':str(row.get('Name','Unknown'))[:100],'state':'RUNNING',
                    'cpuPercent':number(row.get('PercentProcessorTime')),'ramBytes':int(ram),'threads':int(threads)})
        for row in rows(raw.get('thermal'))[:32]:
            reading=number(row.get('CurrentTemperature'))
            if reading is not None and -50<=reading/10-273.15<=150:
                name=str(row.get('InstanceName','ACPI thermal zone'))[:100]
                result['sensors'].append({'id':name,'group':'ACPI thermal zone','label':name,'kind':'temperature','value':reading/10-273.15,'unit':'°C'})
        memory=rows(raw.get('memory'))
        if memory and number(memory[0].get('CacheBytes')) is not None:result['ramCachedBytes']=int(number(memory[0]['CacheBytes']))
        page=rows(raw.get('page'))
        if page:
            result['swapTotalBytes']=int(sum(number(r.get('AllocatedBaseSize')) or 0 for r in page)*1024**2)
            result['swapUsedBytes']=int(sum(number(r.get('CurrentUsage')) or 0 for r in page)*1024**2)
        self.previous=current;self.tick=now
        return result

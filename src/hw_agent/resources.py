"""System metrics; unavailable GPU counters are never reported as zero load."""
from pathlib import Path
import threading

_previous = None
_lock = threading.Lock()


def temperatures():
    cpu, ram = None, None
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            name = (zone/'type').read_text().strip().lower()
            if any(word in name for word in ('cpu','soc','bcm')):
                cpu = round(int((zone/'temp').read_text())/1000,1)
        except (OSError, ValueError): pass
    for sensor in Path('/sys/class/hwmon').glob('hwmon*/temp*_label'):
        try:
            if any(word in sensor.read_text().lower() for word in ('dimm','dram','ram temperature')):
                ram = round(int(sensor.with_name(sensor.name.replace('_label','_input')).read_text())/1000,1)
        except (OSError, ValueError): pass
    return {'cpu_temperature':cpu,'ram_temperature':ram,
            'ram_temperature_note':'RAM 온도 센서가 노출되지 않습니다.' if ram is None else ''}


def snapshot():
    global _previous
    values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    total, idle = sum(values), values[3] + values[4]
    with _lock:
        prior, _previous = _previous, (total, idle)
    cpu = None
    if prior and total > prior[0]:
        cpu = round(100 * (1-(idle-prior[1])/(total-prior[0])), 1)
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in {'MemTotal', 'MemAvailable'}: mem[key] = int(value.split()[0])*1024
    gpu = None
    for path in Path('/sys/class/drm').glob('card*/device/gpu_busy_percent'):
        try: gpu = float(path.read_text()); break
        except (OSError, ValueError): pass
    return {**temperatures(), 'cpu_percent': cpu, 'ram_percent': round(100*(1-mem['MemAvailable']/mem['MemTotal']),1),
            'gpu_percent': gpu, 'gpu_note': 'Pi 드라이버가 사용률 계측을 제공하지 않습니다.' if gpu is None else '',
            'inference_device': 'CPU'}

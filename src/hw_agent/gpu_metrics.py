"""Bridge the Linux V3D driver's existing per-engine activity counters to the UI.

Counter source and units: raspberrypi/linux, drivers/gpu/drm/v3d/v3d_sysfs.c.
No performance-monitor configuration or privileged register access is required.
"""
from pathlib import Path
import threading
import time


ENGINES = {"bin", "render", "tfu", "csd"}


def read_counters(path):
    counters = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) != 4 or fields[0] not in ENGINES:
            continue
        stamp, jobs, runtime = map(int, fields[1:])
        if min(stamp, jobs, runtime) < 0:
            raise ValueError("Negative GPU counter")
        counters[fields[0]] = (stamp, runtime)
    if not counters:
        raise ValueError("No supported GPU engines")
    return counters


class V3dMetrics:
    def __init__(self, drm_root=Path("/sys/class/drm")):
        self.drm_root = drm_root
        self.previous = {}
        self.device = None
        self.cached = None
        self.sampled_at = 0.
        self.lock = threading.Lock()

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            if self.cached is not None and now - self.sampled_at < 1:
                return self.cached.copy()
            result = {"gpu_percent": None, "gpu_engines": {}, "gpu_source": None,
                      "gpu_note": "GPU 활동 통계를 읽을 수 없습니다."}
            try:
                path = next(self.drm_root.glob("card*/device/gpu_stats"))
                device = str(path.resolve())
                current = read_counters(path)
                prior = self.previous if device == self.device else {}
                rates = {}
                for engine, (stamp, runtime) in current.items():
                    if engine not in prior:
                        continue
                    old_stamp, old_runtime = prior[engine]
                    if stamp > old_stamp and runtime >= old_runtime:
                        rates[engine] = round(min(100., 100 * (runtime-old_runtime)/(stamp-old_stamp)), 1)
                self.previous, self.device = current, device
                result.update(gpu_source="Linux V3D gpu_stats", gpu_engines=rates,
                              gpu_note="GPU 활동을 측정하는 중입니다.")
                if rates:
                    # 엔진은 동시에 일할 수 있으므로 합계를 전체 사용률로 표시하지 않는다.
                    result.update(gpu_percent=max(rates.values()), gpu_note="가장 바쁜 GPU 엔진의 사용률")
            except (OSError, ValueError, StopIteration):
                self.previous, self.device = {}, None
            self.cached, self.sampled_at = result, now
            return result.copy()


_sampler = V3dMetrics()


def snapshot():
    return _sampler.snapshot()

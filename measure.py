import os 
import sys
import time
import math
import subprocess
from ipcqueue import posixmq
from ipcqueue.serializers import RawSerializer


def std_dev(times_list, mean):
    square_sum = 0.0
    for time in times_list:
        square_sum += (time - mean) ** 2
    return math.sqrt(square_sum / (len(times_list) - 1))


def calc_results(filters):
    log_capture = open("/tmp/log-capture", "r")
    log_filter = open("/tmp/log-filter", "r")
    log_playback = open("/tmp/log-playback", "r")

    capture_times = {}
    filter_times = {}
    playback_times = {}

    for line in log_capture.readlines():
        values = line.split(" ")
        capture_times[values[0]] = float(values[1])

    for line in log_filter.readlines():
        values = line.split(" ")
        filter_times[values[0]] = float(values[1])

    for line in log_playback.readlines():
        values = line.split(" ")
        playback_times[values[0]] = float(values[1])

    time_to_filter = 0.0
    time_to_playback = 0.0
    time_total = 0.0

    times_to_filter = []
    times_to_playback = []
    times_total = []

    for key in capture_times.keys():
        time = filter_times[key] - capture_times[key]
        time_to_filter += time
        times_to_filter.append(time)
        times_total.append(time)

    for key in filter_times.keys():
        time = playback_times[key] - filter_times[key]
        time_to_playback += time
        times_to_playback.append(time)
        times_total[-1] += time

    time_to_filter /= len(capture_times.keys())
    time_to_playback /= len(filter_times.keys())
    time_total = time_to_filter + time_to_playback

    std_dev_to_filter = std_dev(times_to_filter, time_to_filter)
    std_dev_to_playback = std_dev(times_to_playback, time_to_playback)
    std_dev_total = std_dev(times_total, time_total)

    results.write(f"{filters},{time_to_filter},{std_dev_to_filter},{time_to_playback},{std_dev_to_playback},{time_total},{std_dev_total}\n")
    
    log_capture.close()
    log_filter.close()
    log_playback.close()


def try_rm(path):
    try: 
        os.remove(path)
    except OSError:
        ...


def run(filters, periods):
    try_rm("/tmp/log-capture")
    try_rm("/tmp/log-filter")
    try_rm("/tmp/log-playback")

    mq_settings = posixmq.Queue("/settings", maxsize = 10, maxmsgsize = 8, serializer = RawSerializer)
    proc_capture = subprocess.Popen(["build/capture", str(periods)], stdout = subprocess.PIPE, stderr = sys.stderr)
    proc_filter = subprocess.Popen(["build/filter", str(periods)], stdout = subprocess.PIPE, stderr = sys.stderr)
    proc_playback = subprocess.Popen(["build/playback", str(periods)], stdout = subprocess.PIPE, stderr = sys.stderr)

    for id in range(filters):
        mq_settings.put(id.to_bytes(4, 'little', signed=True) + (10).to_bytes(4, 'little', signed=True))

    sys.stdout.write("Measuring: filters = %i, periods = %i ... " % (filters, periods))
    sys.stdout.flush()

    proc_capture.wait()
    proc_filter.wait()
    proc_playback.wait()

    try_rm("/dev/mqueue/input")
    try_rm("/dev/mqueue/output")
    try_rm("/dev/mqueue/settings")

    calc_results(filters)
    print("done")
    return 0


if __name__ == "__main__":
    results = open("results.csv", "w")
    results.write("filters,time to filter, std dev, time to playback, std dev, total, std dev\n")

    for filters in range(32):
        run(filters, 1000)

    results.close()

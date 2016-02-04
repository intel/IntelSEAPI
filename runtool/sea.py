import os
import sys
import time
import platform
from ctypes import cdll, c_char_p, c_void_p, c_ulonglong, c_int, c_double

class Task:
    def __init__(self, itt, name, id, parent):
        self.itt = itt
        self.name = name
        self.id = id
        self.parent = parent
    def __enter__(self):
        self.itt.lib.itt_task_begin(self.itt.domain, self.id, self.parent, self.itt.get_string_id(self.name), 0)
        return self
    def __exit__(self, type, value, traceback):
        self.itt.lib.itt_task_end(self.itt.domain, 0)
        return False

class Track:
    def __init__(self, itt, track):
        self.itt = itt
        self.track = track
    def __enter__(self):
        self.itt.lib.itt_set_track(self.track)
        return self
    def __exit__(self, type, value, traceback):
        self.itt.lib.itt_set_track(None)
        return False

class ITT:
    scope_global = 1
    scope_process = 2
    scope_thread = 3
    scope_task = 4

    def __init__(self, domain):
        bitness = 32 if '32' in platform.architecture()[0] else 64
        env_name = 'INTEL_LIBITTNOTIFY' + str(bitness)
        self.lib = None
        self.strings = {}
        self.tracks = {}
        self.counters = {}
        if os.environ.has_key(env_name):
            self.lib = cdll.LoadLibrary(os.environ[env_name])

            #void* itt_create_domain(const char* str)
            self.lib.itt_create_domain.argtypes = [c_char_p]
            self.lib.itt_create_domain.restype = c_void_p

            #void* itt_create_string(const char* str)
            self.lib.itt_create_string.argtypes = [c_char_p]
            self.lib.itt_create_string.restype = c_void_p

            #void itt_marker(void* domain, uint64_t id, void* name, int scope)
            self.lib.itt_marker.argtypes = [c_void_p, c_ulonglong, c_void_p, c_int, c_ulonglong]

            #void itt_task_begin(void* domain, uint64_t id, uint64_t parent, void* name)
            self.lib.itt_task_begin.argtypes = [c_void_p, c_ulonglong, c_ulonglong, c_void_p, c_ulonglong]
            
            #void itt_task_end(void* domain)
            self.lib.itt_task_end.argtypes = [c_void_p, c_ulonglong]

            #void* itt_counter_create(void* domain, void* name)
            self.lib.itt_counter_create.argtypes = [c_void_p, c_void_p]
            self.lib.itt_counter_create.restype = c_void_p

            #void itt_set_counter(void* id, double value, uint64_t timestamp)
            self.lib.itt_set_counter.argtypes = [c_void_p, c_double, c_ulonglong]

            #void* itt_create_track(const char* group, const char* track)
            self.lib.itt_create_track.argtypes = [c_char_p, c_char_p]
            self.lib.itt_create_track.restype = c_void_p

            #void itt_set_track(void* track)
            self.lib.itt_set_track.argtypes = [c_void_p]

            #uint64_t itt_get_timestamp()
            self.lib.itt_get_timestamp.restype = c_ulonglong

            self.domain = self.lib.itt_create_domain(domain)

    def get_string_id(self, text):
        try:
            return self.strings[text]
        except:
            id = self.strings[text] = self.lib.itt_create_string(text)
            return id

    def marker(self, text, scope = scope_process, timestamp = 0, id = 0):
        if not self.lib:
            return
        self.lib.itt_marker(self.domain, id, self.get_string_id(text), scope, timestamp)

    def task(self, name, id = 0, parent = 0):
        if not self.lib:
            return
        return Task(self, name, id, parent)

    def task_submit(self, name, timestamp, dur, id = 0, parent = 0):
        self.lib.itt_task_begin(self.domain, id, parent, self.get_string_id(name), timestamp)
        self.lib.itt_task_end(self.domain, timestamp + dur)

    def counter(self, name, value, timestamp = 0):
        if not self.lib:
            return
        try:
            counter = counters[name]
        except:
            counter = counters[name] = self.lib.itt_counter_create(self.domain, self.get_string_id(name))
        self.lib.itt_set_counter(counter, value, timestamp)

    def track(self, group, name):
        if not self.lib:
            return
        key = group+ "/" + name
        try:
            track = self.tracks[key]
        except:
            track = self.tracks[key] = self.lib.itt_create_track(group, name);
        return Track(self, track)

    def get_timestamp(self):
        if not self.lib:
            return 0
        return self.lib.itt_get_timestamp()

def stack_task(itt):
    import random
    with itt.task("python_task"):
        time.sleep(0.01)
        if random.randrange(0,2):
            stack_task(itt)
        time.sleep(0.01)

def test_itt():
    itt = ITT("python")
    itt.marker("Begin")
    ts1 = itt.get_timestamp()
    with itt.task("Main"):
        for i in range(0, 100):
            stack_task(itt)
            itt.counter("python_counter", i)
    ts2 = itt.get_timestamp()
    itt.marker("End")

    with itt.track("group", "track"):
        dur = (ts2-ts1) / 100
        for ts in range(ts1, ts2, dur):
            itt.task_submit("submitted", ts, dur / 2)

if __name__ == "__main__":
    test_itt()

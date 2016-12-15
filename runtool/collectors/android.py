import os
from sea_runtool import Collector, subst_env_vars

"""
to workaround broken atrace on non rooted devices of some vendors:

https://android.googlesource.com/platform/frameworks/native/+/9f476fd08079701d1ad0f7c591667b6e673ed38e%5E1%5E2..9f476fd08079701d1ad0f7c591667b6e673ed38e%5E1/

#define ATRACE_TAG_GRAPHICS         (1<<1)
#define ATRACE_TAG_INPUT            (1<<2)
#define ATRACE_TAG_VIEW             (1<<3)
#define ATRACE_TAG_WEBVIEW          (1<<4)
#define ATRACE_TAG_WINDOW_MANAGER   (1<<5)
#define ATRACE_TAG_ACTIVITY_MANAGER (1<<6)
#define ATRACE_TAG_SYNC_MANAGER     (1<<7)
#define ATRACE_TAG_AUDIO            (1<<8)
#define ATRACE_TAG_VIDEO            (1<<9)
#define ATRACE_TAG_CAMERA           (1<<10)
#define ATRACE_TAG_HAL              (1<<11)
#define ATRACE_TAG_APP              (1<<12)
#define ATRACE_TAG_RESOURCES        (1<<13)
#define ATRACE_TAG_DALVIK           (1<<14)
#define ATRACE_TAG_RS               (1<<15)
#define ATRACE_TAG_BIONIC           (1<<16)
#define ATRACE_TAG_POWER            (1<<17)

+    { "gfx",        "Graphics",         ATRACE_TAG_GRAPHICS, { } },
+    { "input",      "Input",            ATRACE_TAG_INPUT, { } },
+    { "view",       "View System",      ATRACE_TAG_VIEW, { } },
+    { "webview",    "WebView",          ATRACE_TAG_WEBVIEW, { } },
+    { "wm",         "Window Manager",   ATRACE_TAG_WINDOW_MANAGER, { } },
+    { "am",         "Activity Manager", ATRACE_TAG_ACTIVITY_MANAGER, { } },
+    { "audio",      "Audio",            ATRACE_TAG_AUDIO, { } },
+    { "video",      "Video",            ATRACE_TAG_VIDEO, { } },
+    { "camera",     "Camera",           ATRACE_TAG_CAMERA, { } },
+    { "hal",        "Hardware Modules", ATRACE_TAG_HAL, { } },
+    { "res",        "Resource Loading", ATRACE_TAG_RESOURCES, { } },
+    { "dalvik",     "Dalvik VM",        ATRACE_TAG_DALVIK, { } },

setprop debug.atrace.tags.enableflags to_hex(tags)
"""

class Android(Collector):
    def __init__(self, args):
        Collector.__init__(self, args)
        self.adb = self.detect()
        self.file = None
        if self.adb:
            self.start()

    def is_root(self, statics={}):
        if statics:
            return statics['root']
        out, err = self.execute(self.adb + ' shell id')
        if err:
            return False

        statics['root'] = 'root' in out
        return statics['root']

    @classmethod
    def detect(cls):
        adbs = cls.detect_instances('adb')
        systraces = []
        for adb in adbs:
            out, err = cls.execute('"%s" version' % adb)
            if err:
                continue
            parts = out.split()
            version = parts[parts.index('version') + 1]
            systraces.append((version, adb))
        if systraces:
            sorted_by_version = sorted(systraces, key=lambda(ver, _): [int(item) for item in ver.split('.')], reverse=True)
            return '"%s"' % sorted_by_version[0][1]
        else:
            return None

    def echo(self, what, where):
        out, err = self.execute(self.adb + ' shell "echo %s > %s"' % (what, where))
        if err:
            return out, err
        if 'no such file or directory' in str(out).lower():
            return out, out
        return out, err

    def start(self):
        self.file = os.path.join(subst_env_vars(self.args.input), 'atrace-%s.ftrace' % (self.args.cuts[0] if self.args.cuts else '0'))
        self.echo('0', '/sys/kernel/debug/tracing/tracing_on')
        self.echo('', '/sys/kernel/debug/tracing/trace')
        if self.is_root():
            out, err = self.execute(self.adb + ' shell atrace --list_categories')
            if err:
                return False
            features = []
            for line in out.split('\n'):
                parts = line.split()
                if not parts:
                    continue
                features.append(parts[0])

            cmd = self.adb + ' shell atrace'
            if self.args.ring:
                cmd += ' -b %d -c' % (self.args.ring * 1000)
            cmd += ' --async_start %s' % ' '.join(features)
            self.execute_detached(cmd)
        else:  # non roots sometimes have broken atrace, so we won't use it
            out, err = self.execute(self.adb + ' shell setprop debug.atrace.tags.enableflags 0xFFFFFFFF')
            if err:
                return None
            for event in self.enum_switchable_events():
                self.echo('1', event)
            if self.args.ring:
                self.echo("%d" % (self.args.ring * 1024), '/sys/kernel/debug/tracing/buffer_size_kb')
            out, err = self.echo('1', '/sys/kernel/debug/tracing/tracing_on')
            if err:
                return None
        return self

    def enum_switchable_events(self):
        out, err = self.execute(self.adb + ' shell ls -l -R /sys/kernel/debug/tracing/events')
        if err:
            return
        root_dir = None
        for line in out.split('\n'):
            line = line.strip()
            if not line:
                root_dir = None
            else:
                if root_dir:
                    if 'shell' in line and line.endswith('enable'):
                        yield root_dir + '/enable'
                else:
                    root_dir = line.strip(':')

    def stop(self, wait=True):
        out, err = self.echo('0', '/sys/kernel/debug/tracing/tracing_on')
        if err:
            return []
        self.execute(self.adb + ' shell setprop debug.atrace.tags.enableflags 0')
        out, err = self.execute('%s pull /sys/kernel/debug/tracing/trace %s' % (self.adb, self.file))
        if err or 'error' in out:
            with open(self.file, 'w') as file:
                self.execute(self.adb + ' shell cat /sys/kernel/debug/tracing/trace', stdout=file)
        return [self.file]

COLLECTOR_DESCRIPTORS = [{
    'format': 'android',
    'available': True,
    'collector': Android
}]

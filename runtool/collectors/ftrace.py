import glob
import shutil

supported_events = [
    "binder_locked",
    "binder_unlock",
    "binder_lock",
    "binder_transaction",
    "binder_transaction_received",
    "memory_bus_usage",
    "clock_set_rate",
    "cpufreq_interactive_up",
    "cpufreq_interactive_down",
    "cpufreq_interactive_already",
    "cpufreq_interactive_notyet",
    "cpufreq_interactive_setspeed",
    "cpufreq_interactive_target",
    "cpufreq_interactive_boost",
    "cpufreq_interactive_unboost",
    "f2fs_write_begin",
    "f2fs_write_end",
    "f2fs_sync_file_enter",
    "f2fs_sync_file_exit",
    "ext4_sync_file_enter",
    "ext4_sync_file_exit",
    "ext4_da_write_begin",
    "ext4_da_write_end",
    "block_rq_issue",
    "block_rq_complete",
    "drm_vblank_event",
    "exynos_busfreq_target_int",
    "exynos_busfreq_target_mif",
    "exynos_page_flip_state",
    "i915_gem_object_create",
    "i915_gem_object_bind",
    "i915_gem_object_unbind",
    "i915_gem_object_change_domain",
    "i915_gem_object_pread",
    "i915_gem_object_pwrite",
    "i915_gem_object_fault",
    "i915_gem_object_clflush",
    "i915_gem_object_destroy",
    "i915_gem_ring_dispatch",
    "i915_gem_ring_flush",
    "i915_gem_request",
    "i915_gem_request_add",
    "i915_gem_request_complete",
    "i915_gem_request_retire",
    "i915_gem_request_wait_begin",
    "i915_gem_request_wait_end",
    "i915_gem_ring_wait_begin",
    "i915_gem_ring_wait_end",
    "i915_reg_rw",
    "i915_flip_request",
    "i915_flip_complete",
    "intel_gpu_freq_change",
    "irq_handler_entry",
    "irq_handler_exit",
    "softirq_raise",
    "softirq_entry",
    "softirq_exit",
    "ipi_entry",
    "ipi_exit",
    "graph_ent",
    "graph_ret",
    "mali_dvfs_event",
    "mali_dvfs_set_clock",
    "mali_dvfs_set_voltage",
    "tracing_mark_write:mali_driver",
    "mm_vmscan_kswapd_wake",
    "mm_vmscan_kswapd_sleep",
    "mm_vmscan_direct_reclaim_begin",
    "mm_vmscan_direct_reclaim_end",
    "workqueue_execute_start",
    "workqueue_execute_end",
    "power_start",
    "power_frequency",
    "cpu_frequency",
    "cpu_idle",
    "regulator_enable",
    "regulator_enable_delay",
    "regulator_enable_complete",
    "regulator_disable",
    "regulator_disable_complete",
    "regulator_set_voltage",
    "regulator_set_voltage_complete",
    "sched_switch",
    "sched_wakeup",
    "workqueue_execute_start",
    "workqueue_execute_end",
    "workqueue_queue_work",
    "workqueue_activate_work",
]

class FTrace:
    def __init__(self, args, remote):
        self.args = args
        self.file = args.output + ".ftrace"
        self.remote = remote
        self.event_list = []
        self.proc = None

        for event in supported_events:
            for path in glob.glob('/sys/kernel/debug/tracing/events/*/%s/enable' % event):
                self.event_list.append(path)

    def echo(self, what, where):
        try:
            if self.remote:
                self.remote.execute('echo %s > %s' % (what, where))
            else:
                with open(where, "w") as file:
                    file.write(what)
        except:
            return False
        return True

    def start(self):
        self.echo("0", "/sys/kernel/debug/tracing/tracing_on")
        self.echo("nop", "/sys/kernel/debug/tracing/current_tracer")  # google chrome understands this format
        self.echo("", "/sys/kernel/debug/tracing/set_event")  # disabling all events
        self.echo("", "/sys/kernel/debug/tracing/trace")  # cleansing ring buffer (we need it's header only)

        # best is to write sync markers here
        """
        echo(FTRACE("tracing_on"), "1"); //activate tracing
        SEA::FTraceSync(); //writing synchronization markers
        echo(FTRACE("tracing_on"), "0"); //deactivate tracing
        //saving first part of synchronization as it will be wiped out in ring
        int res = std::system(("cat /sys/kernel/debug/tracing/trace > " + m_folder + "/nop.ftrace").c_str());
        if (-1 == res) return false;
        echo(FTRACE("trace"));// cleansing ring buffer again
        """

        for event in self.event_list:  # enabling only supported
            self.echo("1", event)
        self.echo("1", "/sys/kernel/debug/tracing/tracing_on")

    def stop(self):
        self.echo("0", "/sys/kernel/debug/tracing/tracing_on")
        if self.remote:
            self.remote.copy('%s:%s' % (self.args.ssh, "/sys/kernel/debug/tracing/trace"), self.file)
        else:
            shutil.copy("/sys/kernel/debug/tracing/trace", self.file)
        return self.file


def start_ftrace(args, remote=None):
    ftrace = FTrace(args, remote)
    if not ftrace.echo("nop", "/sys/kernel/debug/tracing/current_tracer"):
        print "Warning: failed to access ftrace subsystem"
        return None
    ftrace.start()
    return ftrace


COLLECTOR_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'collector': start_ftrace
}]

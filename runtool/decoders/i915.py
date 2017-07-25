import os
import sys
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'importers')))

from etw import GPUQueue


class I915(GPUQueue):

    # I915_GEM_DOMAIN_...
    CPU = 0x00000001  # CPU cache
    RENDER = 0x00000002  # Render cache, used by 2D and 3D drawing
    SAMPLER = 0x00000004  # Sampler cache, used by texture engine
    COMMAND = 0x00000008  # Command queue, used to load batch buffers
    INSTRUCTION = 0x00000010  # Instruction cache, used by shader programs
    VERTEX = 0x00000020  # Vertex address cache
    GTT = 0x00000040  # GTT domain - aperture and scanout

    def __init__(self, args, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.counters = {}
        self.cpu_packets = {}
        self.state = {}
        self.relations = {}
        self.wait_relations = {}
        self.gpu_relations = {}
        self.relations_add = {}
        self.has_gpu_events = False
        self.objects = {}

    @staticmethod
    def parse_args(args):
        parts = args.strip().split()
        args = {}
        for part in parts:
            if '=' in part:
                key, val = tuple(part.split('=', 1))
                args[key] = val.strip(',')
        return args

    def start_task(self, args, lcls):
        args = self.parse_args(args)
        self.state[self.get_id(args)] = lcls

    def add_relation(self, frm, to, static={'count': 0}):
        relation = (frm.copy(), to.copy(), frm)
        if 'realtime' in relation[1]:
            relation[1]['time'] = relation[1]['realtime']
        relation[0]['parent'] = static['count']
        static['count'] += 1
        if self.callbacks.check_time_in_limits(relation[0]['time']):
            for callback in self.callbacks.callbacks:
                callback.relation(*relation)

    def get_id(self, args):
        if not isinstance(args, dict):
            args = self.parse_args(args)
        return args['uniq'] if 'uniq' in args else args['seqno']

    def join_task(self, pid, tid, timestamp, name, args):
        args = self.parse_args(args)
        id = self.get_id(args)
        if id not in self.state:
            return None
        prev = self.state[id]
        if prev['pid'] != pid or prev['tid'] != tid:
            return None
        call_data = {'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'i915', 'time': prev['timestamp'], 'str': name, 'type': 0, 'args': args, 'id': id}
        end_data = call_data.copy()
        end_data['time'] = timestamp
        end_data['type'] = 1
        self.callbacks.complete_task('task', call_data, end_data)
        del self.state[id]
        return call_data

    def handle_record(self, proc, pid, tid, cpu, flags, timestamp, name, args):
        if name.startswith('i915_gem_request_wait'):
            args = self.parse_args(args)
            id = args['uniq'] if 'uniq' in args else args['seqno']
            if name.endswith('_end'):
                if id not in self.cpu_packets:
                    return
                self.callbacks.on_event("task_end", {'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'i915', 'time': timestamp, 'type': 1, 'args': args, 'id': id})
            elif name.endswith('_begin'):
                self.cpu_packets[id] = {'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'i915', 'time': timestamp, 'str': 'wait_request', 'type': 0, 'args': args, 'id': id}
                self.callbacks.on_event("task_begin", self.cpu_packets[id])
                if id in self.wait_relations:
                    self.add_relation(self.cpu_packets[id], self.wait_relations[id])
                    del self.wait_relations[id]
            else:
                assert(not "Unhandled")
        elif name.startswith('libdrm'):
            args = self.parse_args(args)
            fn = args['name']
            counter.setdefault(fn, 0)
            if name.endswith('_end'):
                if counter[fn] <= 0:
                    return
                counter[fn] -= 1
                self.callbacks.on_event("task_end", {'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'ftrace', 'time': timestamp, 'type': 1, 'args': args})
            elif name.endswith('_begin'):
                counter[fn] += 1
                self.callbacks.on_event("task_begin", {'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'ftrace', 'time': timestamp, 'str': fn, 'type': 0, 'args': args})
        elif 'i915_mvp_read_req' == name:
            self.has_gpu_events = True
            args = self.parse_args(args)
            ring = int(args['ring'])
            start = int(args['start'], 16)
            end = int(args['end'], 16)
            gputime = int(args['gpu_time'], 16)
            cputime = int(args['cpu_time'], 16)

            gputime |= start & 0xFFFFFFFF00000000

            start = cputime + (start - gputime) * 80
            end = cputime + (end - gputime) * 80
            id = args['uniq'] if 'uniq' in args else args['seqno']
            call_data = {'tid': ring, 'pid': -1, 'domain': 'i915', 'time': start, 'str': id, 'type': 2, 'args': args, 'id': id}

            self.auto_break_gui_packets(call_data, 2 ** 64 + call_data['tid'], True)
            self.callbacks.on_event("task_begin_overlapped", call_data)

            end_data = call_data.copy()
            end_data.update({'time': end, 'type': 3})
            self.auto_break_gui_packets(end_data, 2 ** 64 + end_data['tid'], False)
            self.callbacks.on_event("task_end_overlapped", end_data)

            if id in self.gpu_relations:
                self.add_relation(call_data, self.gpu_relations[id])
                del self.gpu_relations[id]
            else:
                self.gpu_relations[id] = call_data

            if id in self.cpu_packets:
                self.add_relation(call_data, self.cpu_packets[id])
                del self.cpu_packets[id]

            if id in self.relations_add:
                self.add_relation(call_data, self.relations_add[id])
                del self.relations_add[id]

        elif 'i915_gem_object_change_domain' in name:
            args = self.parse_args(args)

            def decode_bits(bits):
                res = set()
                if bits & I915.CPU:
                    res.add('CPU')
                if bits & I915.RENDER:
                    res.add('RENDER')
                if bits & I915.SAMPLER:
                    res.add('SAMPLER')
                if bits & I915.COMMAND:
                    res.add('COMMAND')
                if bits & I915.INSTRUCTION:
                    res.add('INSTRUCTION')
                if bits & I915.VERTEX:
                    res.add('VERTEX')
                if bits & I915.GTT:
                    res.add('GTT')
                return res

            def domain_change(arg):
                (frm, to) = arg.split('=>')
                if frm == to:
                    return [], set()
                bits_frm = decode_bits(int(frm, 16))
                bits_to = decode_bits(int(to, 16))
                added_bits = bits_to - bits_frm
                removed_bits = bits_frm - bits_to
                return ['-' + bit for bit in removed_bits] + ['+' + bit for bit in added_bits], bits_to
            read_domain_change, read_domain = domain_change(args['read'])
            write_domain_change, write_domain = domain_change(args['write'])
            if read_domain_change or write_domain_change:
                args['read'] = '%s = %s' % (' '.join(read_domain_change), ' '.join(read_domain))
                args['write'] = '%s = %s' % (' '.join(write_domain_change), ' '.join(write_domain))
                self.callbacks.on_event("marker", {'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'i915', 'time': timestamp, 'str': name, 'type': 5, 'data': 'track', 'args': args})
                """
                self.callbacks.on_event("object_snapshot", {
                    'tid': tid, 'pid': (pid if pid is not None else tid), 'domain': 'i915', 'time': timestamp, 'str': args['obj'], 'type': 10, 'args': {'snapshot': args}, 'id': int(args['obj'], 16)
                })
                """
        elif 'i915_reg_rw' == name:  # write reg=0x120a8, len=4, val=(0xfffffeff, 0x0)
            pass
        elif 'i915_gem_ring_queue' == name:  # ring=1, uniq=246509, seqno=0
            self.start_task(args, locals())
        elif 'i915_scheduler_queue' == name:  # ring=1, uniq=246509, seqno=0
            call_data = self.join_task(pid, tid, timestamp, 'gem_ring_queue->scheduler_queue', args)  # first event in 'uniq' life time
            if not call_data:
                return
            id = call_data['id']
            self.relations[id] = call_data
            self.wait_relations[id] = call_data
        elif 'i915_scheduler_node_state_change' == name:  # ring=1, uniq=246509, seqno=0, status=1
            pass
        elif 'i915_scheduler_pop_from_queue' == name:  # ring=1, uniq=0, seqno=0
            self.start_task(args, locals())
        elif 'i915_scheduler_fly' == name:  # ring=0, uniq=246537, seqno=0
            call_data = self.join_task(pid, tid, timestamp, 'scheduler_pop_from_queue->scheduler_fly', args)
            id = call_data['id']
            if id in self.relations:
                self.add_relation(call_data, self.relations[id])
            self.relations[id] = call_data
        elif 'i915_scheduler_destroy' == name:  # ring=1, uniq=246526, seqno=308228
            pass
        elif 'i915_vma_bind' == name:  # obj=ffff8800a1d70240, offset=00000000ff3e0000 size=8000 vm=ffff88044426c000
            pass
        elif 'i915_va_alloc' == name:  # vm=ffff88044426c000 (P), 0xff3e0000-0xff3e7fff
            pass
        elif 'i915_page_table_entry_map' == name:  # vm=ffff88044426c000, pde=505, updating 487:480	ffffffff,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000
            pass
        elif 'i915_gem_ring_dispatch' == name:  # dev=0, ring=0, uniq=246537, seqno=308221, flags=0
            self.start_task(args, locals())
            args = self.parse_args(args)
            lane = self.callbacks.process(-1 - int(args['dev']), 'GPU').thread(-1 - int(args['ring']))
            id = self.get_id(args)
            task = lane.task(id, 'I915', True)
            task.begin(timestamp, id, args)
            lane.task_pool[id] = task
        elif 'i915_gem_request_add' in name:
            call_data = self.join_task(pid, tid, timestamp, 'gem_ring_dispatch->gem_request_add', args)
            if call_data:
                id = call_data['id']
                if id in self.relations:
                    self.add_relation(call_data, self.relations[id])
                self.relations[id] = call_data
                self.relations_add[id] = call_data
        elif 'i915_scheduler_remove' == name:  # ring=0, do_submit=1
            pass
        elif 'i915_scheduler_landing' == name:  # ring=4, uniq=246869, seqno=308717, status=3
            self.start_task(args, locals())
        elif name in ['i915_gem_request_complete', 'i915_gem_request_retire']:  # dev=0, ring=4, uniq=246869, seqno=308717
            prev_name = self.state.get(self.get_id(args), {'name': None})['name']
            if prev_name == 'i915_scheduler_landing':
                call_data = self.join_task(pid, tid, timestamp, 'scheduler_landing->gem_request_complete', args)
                if not call_data:
                    return
                id = call_data['id']
                if id in self.gpu_relations:
                    self.add_relation(call_data, self.gpu_relations[id])
                    del self.gpu_relations[id]
                else:
                    self.gpu_relations[id] = call_data
                id = self.get_id(args)
                if id in self.state:
                    del self.state[id]
                return
            args = self.parse_args(args)
            lane = self.callbacks.process(-1 - int(args['dev']), 'GPU').thread(-1 - int(args['ring']))
            id = self.get_id(args)
            if id in lane.task_pool:
                lane.task_pool[id].end(timestamp)
                del lane.task_pool[id]
        elif 'i915_page_table_entry_alloc' == name:  # vm=ffff880444268000, pde=502 (0xfedfb000-0xfedfffff)
            pass
        elif 'i915_context_free' == name:  # dev=0, ctx=ffff880401fde000, ctx_vm=ffff88044426c000
            pass
        elif 'i915_vma_unbind' == name:  # obj=ffff8800a1d733c0, offset=00000000041bd000 size=4000 vm=ffff8804381889b0
            pass
        elif 'i915_ppgtt_release' == name:  # dev=0, vm=ffff88044426c000
            pass
        elif 'i915_flip_request' == name:  # plane=1, obj=ffff88002ea16600
            args = self.parse_args(args)
            self.state[args['obj']] = locals()
        elif 'i915_flip_complete' == name:  # plane=1, obj=ffff88002ea16600
            args = self.parse_args(args)
            id = args['obj']
            if id in self.state:
                start = self.state[id]
                lane = self.callbacks.process(pid).thread(tid)
                lane.task('Flip', 'i915').complete(start['timestamp'], timestamp - start['timestamp'])
        elif name == 'i915_gem_object_create':
            args = self.parse_args(args)
            obj = args['obj']
            thread = self.callbacks.process(pid).thread(tid)
            self.objects[obj] = thread.object(int(obj, 16), 'GemObj:' + obj, 'i915')
        elif name == 'i915_gem_object_destroy':
            args = self.parse_args(args)
            obj = args['obj']
            if obj in self.objects:
                del self.objects[obj]
        elif name == 'i915_gem_object_move_to_active':
            args = self.parse_args(args)
            obj = args['obj']
            if obj in self.objects:
                args.update({'state': 'ACTIVE'})
                self.objects[obj].create(timestamp).snapshot(timestamp, args)
        elif name == 'i915_gem_object_move_to_inactive':
            args = self.parse_args(args)
            obj = args['obj']
            if obj in self.objects:
                args.update({'state': 'inactive'})
                self.objects[obj].snapshot(timestamp, args).destroy(timestamp)
        elif name == 'i915_atomic_update_start':  # 'pipe B, frame=33785, scanline=1101, pf[N]:ctrl=0 size=4af077f'
            thread = self.callbacks.process(pid).thread(tid)
            args = self.parse_args(args)
            thread.task_pool[args['frame']] = locals()
        elif name == 'i915_atomic_update_end':  # 'pipe B, frame=33785, scanline=1120'
            thread = self.callbacks.process(pid).thread(tid)
            args = self.parse_args(args)
            start = thread.task_pool.get(args['frame'], None)
            if start:
                thread.task('i915_atomic_update').complete(start['timestamp'], timestamp - start['timestamp'], args={'frame': args['frame'], 'scanline_start': start['args']['scanline'], 'scanline_finish': args['scanline']})
        elif name in ['i915_gem_object_pwrite', 'i915_gem_ring_flush', 'i915_gem_object_clflush', 'i915_gem_obj_prealloc_start', 'i915_gem_obj_prealloc_end', 'i915_gem_object_fault', 'i915_gem_context_reference', 'i915_gem_request_unreference', 'i915_gem_request_reference', 'i915_gem_request_complete_begin', 'i915_gem_request_complete_loop', 'i915_plane_info', 'i915_gem_context_unreference', 'i915_maxfifo_update', 'i915_gem_retire_work_handler']:
            pass
        elif 'i915' in name:
            pass
        elif 'drm_vblank' in name:
            self.callbacks.vsync(timestamp)
        elif 'intel_gpu_freq_change' in name:
            pass
        elif 'switch_mm' in name:
            pass
        else:
            pass

    def finalize(self):
        if self.has_gpu_events:
            for callback in self.callbacks.callbacks:
                callback("metadata_add", {'domain': 'GPU', 'str': '__process__', 'pid': -1, 'tid': -1, 'data': 'GPU Engines', 'time': 0, 'delta': -2})
                for tid, name in enumerate(['GPGPU', 'VDBOX-1', 'BLITTER', 'VEBOX', 'VDBOX-2']):
                    callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__thread__', 'pid': -1, 'tid': tid, 'data': '%s (%d)' % (name, tid)})

DECODER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'decoder': I915
}]

import os
import sys
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'importers')))
from etw import GPUQueue


class SteamVR(GPUQueue):

    def __init__(self, parser, args, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.parser = parser
        self.steamvr = {}

    def handle_record(self, system, data, info):
        parts = data.split('] ')
        object = None
        if len(parts) > 1:
            object = parts[0].strip('[')
            data = parts[1]
        id = None
        if ':' in data:
            parts = data.split(':')
            id = parts[1].strip()
            data = parts[0].strip()
        hint = None
        if '(' in data:
            parts = data.split('(')
            hint, rest = parts[1].split(')')
            data = parts[0] + rest
        type = None

        if data.startswith('Begin'):
            type = 'begin'
            data = data.replace('Begin ', '')
        if data.startswith('End'):
            type = 'end'
            data = data.replace('End ', '')
        if data.endswith('Begin'):
            type = 'begin'
            data = data.replace(' Begin', '')
        if data.endswith('End'):
            type = 'end'
            data = data.replace(' End', '')
        if data.endswith('- begin'):
            type = 'begin'
            data = data.replace(' - begin', '')
        if data.endswith('- end'):
            type = 'end'
            data = data.replace(' - end', '')
        if data.startswith('Before'):
            type = 'begin'
            data = data.replace('Before ', '')
        if data.startswith('After'):
            type = 'end'
            data = data.replace('After ', '')

        self.on_steam_event(system, object, type, data, id, hint.strip() if hint else None)

    def on_steam_event(self, system, object, type, data, id, hint):
        call_data = {
            'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': 'SteamVR',
            'time': self.parser.convert_time(system['time']),
            'args': {'obj': object}
        }

        if type is not None:
            events = self.steamvr.setdefault(call_data['tid'], {}).setdefault(data, {})
            if type == 'begin':
                events[id] = system['time']
            else:
                self.finish_task(events, call_data, data, id)
        else:
            if data == 'TimeSinceLastVSync':
                call_data['type'] = 6
                call_data['str'] = 'TimeSinceLastVSync'
                call_data['delta'] = float(id)
                del call_data['args']
                self.callbacks.complete_task('counter', call_data, call_data)
            elif 'Predicting' in data or 'frameTimeout' in data:
                parts = hint.split()
                value = float(parts[0])
                units = parts[1]
                call_data['type'] = 6
                call_data['str'] = '%s(%s)' % (data, units)
                call_data['delta'] = value
                del call_data['args']
                self.callbacks.complete_task('counter', call_data, call_data)
            elif data == 'Clear BackBuffer':
                events = self.steamvr.setdefault(call_data['tid'], {}).setdefault('Clear BackBuffer', {})
                events[None] = system['time']
                return
            else:
                if 'Mark Timing Event' in data:
                    if 'Post-clear' in id:
                        events = self.steamvr.setdefault(call_data['tid'], {}).setdefault('Clear BackBuffer', {})
                        self.finish_task(events, call_data, 'Clear BackBuffer', None)
                        return
                    elif 'Begin' in id:
                        events = self.steamvr.setdefault(call_data['tid'], {}).setdefault('Warp', {})
                        events[None] = system['time']
                        return
                    elif 'End' in id:
                        events = self.steamvr.setdefault(call_data['tid'], {}).setdefault('Warp', {})
                        self.finish_task(events, call_data, 'Warp:R', None)
                        return
                elif 'Warp' in data:
                    events = self.steamvr.setdefault(call_data['tid'], {}).setdefault('Warp', {})
                    if events:
                        assert id == 'L'
                        self.finish_task(events, call_data, 'Warp:L', None)
                    else:
                        events[None] = system['time']
                    return
                elif any(phrase in data for phrase in ['Timed out', 'Detected dropped frames']):
                    call_data['args']['Error'] = data
                    call_data.update({'type': 10, 'args': {'snapshot': call_data['args'].copy()}, 'id': 0, 'str': 'SteamVR Error'})
                    self.callbacks.on_event("object_snapshot", call_data)
                    return
                call_data.update({'str': data, 'type': 5, 'data': 'track'})  # track_group
                if 'Got new frame' in data:
                    call_data['data'] = 'task'
                call_data['args']['id'] = id
                self.callbacks.on_event("marker", call_data)

    def finish_task(self, events, call_data, data, id):
        if id not in events:
            return
        end_data = call_data.copy()
        call_data.update({'str': data, 'type': 0})
        call_data['time'] = self.parser.convert_time(events[id])
        end_data['type'] = 1

        lane_task = self.callbacks.process(call_data['pid']).\
            thread(call_data['tid']).lane(call_data['str'], call_data['domain']).\
            frame_begin(call_data['time'], call_data['str'])
        lane_task.end(end_data['time'])

        del events[id]

    @classmethod
    def get_providers(cls):
        return ['{8C8F13B1-60EB-4B6A-A433-DE86104115AC}']

    def finalize(self):
        pass

DECODER_DESCRIPTORS = [{
    'format': 'etw',
    'available': True,
    'decoder': SteamVR
}]

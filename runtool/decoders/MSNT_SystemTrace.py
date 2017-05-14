import sys
import socket

def resolve_host(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except:
        return None

def convert_numbers(obj):
    if isinstance(obj, dict):
        for k, v in obj.iteritems():
            obj[k] = convert_numbers(v)
    elif isinstance(obj, list):
        new = [convert_numbers(v) for v in obj]
        del obj[:]
        obj.extend(new)
    elif hasattr(obj, '__iter__'):
        for v in obj:
            convert_numbers(v)
    elif isinstance(obj, basestring):
        if obj.isdigit():
            return int(obj)
    return obj


class MSNT_SystemTraceDecoder:
    def __init__(self, parser, args, callbacks):
        self.parser, self.args, self.callbacks = parser, args, callbacks
        self.tcpip = {}

    @staticmethod
    def resolve_host(data, field):
        host = resolve_host(data[field])
        if host:
            data['%s_resolved' % field] = host

    def handle_record(self, system, data, info):
        if info['EventName'] in ['TcpIp', 'UdpIp']:
            if info['Opcode'] in ['Fail']:
                return
            pid = data['PID']
            now = self.parser.convert_time(system['time'])
            if info['Opcode'] in ['ConnectIPV4', 'ReconnectIPV4', 'DisconnectIPV4', 'AcceptIPV4', 'TCPCopyIPV4']:
                target_thread = self.callbacks.process(pid).thread(0, 'TcpIp/UDP')
                self.resolve_host(data, 'daddr')
                self.resolve_host(data, 'saddr')
                target_thread.object(id(data), info['Opcode']).snapshot(now, args=data)
                return
            target = data['daddr'] + ':' + data['dport']
            source = data['saddr'] + ':' + data['sport']
            if info['Opcode'] in ['SendIPV4', 'SendIPV6']:  # gather all sends by target
                receiver = self.tcpip.setdefault(target, {'packets':[], 'started': None})
                receiver['packets'].append({'pid': pid, 'size': data['size'], 'source': source, 'time': system['time'], 'type': info['EventName']})
                self.end_receiver(receiver)
                self.callbacks.process(pid).thread(0, 'TcpIp/UDP').marker('thread', 'SendIPV4').set(now, args=data)
            elif info['Opcode'] in ['RecvIPV4', 'RecvIPV6']:  # on each receive take all ready packets for this 'source'
                self.callbacks.process(pid).thread(0, 'TcpIp/UDP').marker('thread', 'RecvIPV4').set(now, args=data)
                self.on_receive(data['size'], now, pid, source, target)
        elif info['EventName'] == 'SystemConfig':
            if info['Opcode'] in ['Video', 'NIC', 'PhyDisk', 'LogDisk', 'CPU', 'Platform']:
                self.callbacks.add_metadata(info['Opcode'], convert_numbers(data))
        elif sys.gettrace():
            print 'EventName:', info['EventName'], 'Opcode:', info['Opcode']

    def on_receive(self, size, now, pid, source, target):
        receiver = self.tcpip.setdefault(source, {'packets': [], 'started': None})
        if receiver['packets']:
            if 'pid' in receiver:
                assert (receiver['pid'] == pid)
            else:
                receiver['pid'] = pid
            start_time = min(packet['time'] for packet in receiver['packets'])
            end_time = max(packet['time'] for packet in receiver['packets']) + 1000
            sent = [int(packet['size']) for packet in receiver['packets']]
            target_thread = self.callbacks.process(pid).thread(0, 'TcpIp/UDP')
            packet = receiver['packets'][0]  # all packets to this target are considered to be from the same source
            target_task = target_thread.task('Recv').begin(now, args={'from': target, 'own': source})
            source_thread = self.callbacks.process(packet['pid']).thread(0, 'TcpIp/UDP')
            source_task = source_thread.task(packet['type']).begin(
                self.parser.convert_time(start_time),
                args={'sent': sent, 'to': packet['source'], 'own': target}
            )
            source_task.relate(target_task)
            source_task.end(end_time)
            assert (not receiver['started'])
            target_task.sizes = []
            receiver['started'] = target_task
            receiver['packets'] = []
        if receiver['started']:
            receiver['started'].sizes.append(int(size))
            receiver['started'].end_time = now + 1000

    @classmethod
    def get_providers(cls):
        return ['MSNT_SYSTEMTRACE']

    @staticmethod
    def end_receiver(receiver):
        if receiver['started']:
            target_task = receiver['started']
            target_task.add_args({'received': target_task.sizes})
            target_task.end(target_task.end_time)
            receiver['started'] = None

    def finalize(self):
        for target, receiver in self.tcpip.iteritems():
            self.end_receiver(receiver)
            packets = receiver['packets']
            if packets:
                if 'pid' in receiver:
                    pid = receiver['pid']
                    now = self.parser.convert_time(max(packet['time'] for packet in packets)) + 1000
                    packet = receiver['packets'][0]  # all packets to this target are considered to be from the same source
                    self.on_receive(0, now, pid, target, packet['source'])
                    self.end_receiver(receiver)
                else:
                    pass  # not sure what to do with these remnants yet...


DECODER_DESCRIPTORS = [{
    'format': 'etw',
    'available': True,
    'decoder': MSNT_SystemTraceDecoder
}]

from __future__ import print_function
import os
import sys
import json
import sqlite3
import contextlib

if __name__ == "__main__":
    sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
from sea_runtool import TaskCombiner, default_tree, Callbacks, Progress, get_decoders, parse_args, get_args
from python_compat import func_code, func_globals, func_name


def debugprint(fn):
    def wrapper(*args, **kwargs):
        if get_args().debug:
            print('%s:%s' % (func_globals(fn)['__name__'], func_name(fn)), args, kwargs)
        return fn(*args, **kwargs)
    return wrapper


class SQLiteWrapper(object):
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute('pragma journal_mode=wal')
        self.tables = []

    def has_table(self, name):
        with self.select('sqlite_master', 'name', **{'WHERE': "type='table'"}) as cursor:
            table_names = [tpl[0] for tpl in cursor]
        return (name in self.tables) or (name in table_names)

    def new_table(self, name, fields):
        if self.has_table(name):
            return False
        assert all(type in ['TEXT', 'JSON', 'INTEGER'] for type, _ in fields)
        cmd = 'CREATE TABLE "%s" (%s)' % (name, ', '.join([key + ' ' + type for type, key in fields]))
        self.conn.execute(cmd).close()
        self.tables.append(name)

    def insert(self, where, *values):
        cmd = 'INSERT INTO "%s" VALUES(%s)' % (where, ','.join(['?' for _ in range(len(values))]))
        self.conn.execute(cmd, values).close()

    def select(self, from_table, what='*', **kwargs):
        cmd = 'SELECT %s FROM "%s" %s' % (what, from_table, ' '.join(key.upper() + ' ' + val for key, val in kwargs.items()))
        cur = self.conn.cursor()
        cur.execute(cmd)
        return contextlib.closing(cur)

    def finish(self):
        self.conn.commit()
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.finish()
        return False


class AutoSort:
    def __init__(self, parent, table):
        self.parent = parent
        self.table = table
        self.db_fill = parent.args.sqlite  # not sys.gettrace() or parent.args.debug
        if self.db_fill:
            # TODO: consider for debugging: os.path.join(self.parent.args.user_input, 'transform', 'sortby.db')
            self.db = SQLiteWrapper(':memory:')
            self.db.new_table(self.table, [('TEXT', 'name'), ('INTEGER', 'time'), ('JSON', 'args')])
        self.size = 0

    def handle(self, what, fn, args):
        if not self.db_fill:
            return fn(*args)
        self.index = func_code(fn).co_varnames.index(what)
        key_field = args[self.index]
        self.db.insert(self.table, func_name(fn), key_field, json.dumps(args[1:], default=lambda o: ''))
        self.size += 1

    def read_db(self):
        if self.db_fill:
            self.db_fill = False
            with self.db.select(self.table, **{'ORDER BY': 'time'}) as data, Progress(self.size, 50, self.table) as progress:
                i = 0
                for record in data:
                    progress.tick(i)
                    i += 1
                    name, time, args = record
                    fn = getattr(self.parent, name)
                    fn(*json.loads(args))

    @classmethod
    def finalize(cls, parent):
        autosorts = getattr(parent, 'autosort__', None)
        if not autosorts:
            return
        keys = sorted(autosorts.keys())
        for key in keys:
            autosort = autosorts[key]
            for instance in autosort.values():
                instance.read_db()
        parent.autosort__ = {}


def sortby(what, step=None, table=None):
    def real_decorator(fn):
        table_name = ('sortby__%s__%s' % (func_globals(fn)['__name__'], table or func_name(fn))).replace('.','_')
        def wrapper(*args, **kwargs):
            assert not kwargs
            parent = args[0]
            if not hasattr(parent, 'autosort__'):
                setattr(parent, 'autosort__', {})
            autosorts = parent.autosort__.setdefault(step, {})
            if table_name in autosorts:
                autosort = autosorts[table_name]
            else:
                autosort = autosorts[table_name] = AutoSort(parent, table_name)
            return autosort.handle(what, fn, args)
        return wrapper
    return real_decorator
sortby.finalize = AutoSort.finalize

class SQLite(TaskCombiner):
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, args, tree)

        file = self.get_targets()[0]
        if os.path.exists(file):
            os.remove(file)

        self.conn = sqlite3.connect(file)
        self.cursor = self.conn.cursor()

        self.cursor.execute('CREATE TABLE tasks (type TEXT, begin JSON, end JSON)')
        self.cursor.execute('CREATE TABLE meta (data JSON)')
        self.cursor.execute('CREATE TABLE relation (data JSON, head JSON, tail JSON)')
        self.cursor.execute('CREATE TABLE context_switch (time INTEGER, cpu INTEGER, prev JSON, next JSON)')
        #self.cursor.execute('CREATE TABLE stack (task, stack, name text)')

    def get_targets(self):
        return [self.args.output + ".db"]

    def complete_task(self, type, begin, end):
        self.cursor.execute("INSERT INTO tasks VALUES(?,?,?)", (type, json.dumps(begin), json.dumps(end)))

    def global_metadata(self, data):
        self.cursor.execute("INSERT INTO meta VALUES(?)", (json.dumps(data),))

    def relation(self, data, head, tail):
        self.cursor.execute("INSERT INTO relation VALUES(?,?,?)", (json.dumps(data), json.dumps(head), json.dumps(tail)))

    def handle_stack(self, task, stack, name='stack'):
        pass

    def context_switch(self, time, cpu, prev, next):
        self.cursor.execute("INSERT INTO context_switch VALUES(?,?,?,?)", (time, cpu, json.dumps(prev), json.dumps(next)))


    def finish(self):
        self.conn.commit()
        self.conn.close()

    @staticmethod
    def join_traces(traces, output, args):
        by_size = sorted([(os.path.getsize(trace), trace) for trace in traces], key=lambda size_name: size_name[0], reverse=True)
        outputs = []
        with sqlite3.connect(by_size[0][1]) as conn:
            for (size, trace) in by_size[1:]:
                conn.execute("ATTACH '%s' as dba" % trace)
                conn.execute("BEGIN")
                for row in conn.execute("SELECT * FROM dba.sqlite_master WHERE type='table'"):
                    combine = "INSERT INTO " + row[1] + " SELECT * FROM dba." + row[1]
                    conn.execute(combine)
                conn.commit()
                conn.execute("DETACH DATABASE dba")
            conn.execute("CREATE VIEW by_begin_time AS SELECT json_extract(begin, '$.time') AS begin_time, * FROM tasks ORDER BY begin_time")
            outputs = SQLite.post_process(args, conn)
        return [by_size[0][1]] + outputs

    @staticmethod
    def post_process(args, conn):
        decoders = get_decoders().get('db', [])
        if not decoders:
            return []
        tree = default_tree(args)
        tree['ring_buffer'] = True
        args.no_left_overs = True
        with Callbacks(args, tree) as callbacks:
            if callbacks.is_empty():
                return callbacks.get_result()

            for decoder in get_decoders().get('db', []):
                decoder(args, callbacks).handle_db(conn)

        return callbacks.get_result()


EXPORTER_DESCRIPTORS = [{
    'format': 'db',
    'available': True,
    'exporter': SQLite
}]

if __name__ == "__main__":
    args, _ = parse_args(sys.argv[1:])
    with sqlite3.connect(args.input) as conn:
        SQLite.post_process(args, conn)
#*********************************************************************************************************************************************************************************************************************************************************************************************
#   Intel(R) Single Event API
#
#   This file is provided under the BSD 3-Clause license.
#   Copyright (c) 2015, Intel Corporation
#   All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#       Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#       Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#       Neither the name of the Intel Corporation nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
#   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#   IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
#   HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#**********************************************************************************************************************************************************************************************************************************************************************************************

import os
import sys
import shutil
import fnmatch
import subprocess


install_dest = r"./../installer"


def get_share_folder():
    import datetime
    folder_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(install_dest, folder_name)


def run_shell(cmd):
    print "\n>>", cmd
    os.system(cmd)


def replace_in_file(file, what_by):
    import fileinput
    for line in fileinput.input(file, inplace=True):
        for (what, by) in what_by:
            if what in line:
                line = line.replace(what, by)
        sys.stdout.write(line)


def get_yocto():
    if not os.environ.has_key('CXX'):
        return None
    cxx = os.environ['CXX']
    if '-poky' not in cxx:
        return None
    if '-m32' in cxx:
        return {'bits':'32'}
    return {'bits':'64'}


def GetJDKPath():
    if sys.platform == 'win32':
        import _winreg
        path = "SOFTWARE\\JavaSoft\\Java Development Kit"
        try:
            aKey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, path, 0, _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY)
        except WindowsError:
            print "No key:", path
            return None
        subkeys = []
        try:
            i = 0
            while True:
                subkeys.append(_winreg.EnumKey(aKey, i))
                i += 1
        except WindowsError:
            pass
        if not subkeys:
            print "No subkeys for:", path
            return None
        subkeys.sort()
        path += "\\" + subkeys[-1]
        try:
            aKey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, path, 0, _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY)
            return _winreg.QueryValueEx(aKey, "JavaHome")[0]
        except WindowsError:
            print "No value for:", path
            return None
    else:
        path, err = subprocess.Popen("which javah", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if err or not path:
            return None
        if sys.platform == 'darwin':
            path = subprocess.check_output("/usr/libexec/java_home").split('\n')[0]
            return (path if os.path.exists(path) else None)
        else:
            matches = []
            for root, dirnames, filenames in os.walk('/usr/lib/jvm'):
                for filename in fnmatch.filter(filenames, 'jni.h'):
                    matches.append(os.path.join(root, filename))
            if not matches:
                return None
            return os.path.split(matches[0])[0]

if sys.platform == 'win32':
    def read_registry(path, depth=0xFFFFFFFF, statics={}):
        import _winreg
        parts = path.split('\\')
        hub = parts[0]
        path = '\\'.join(parts[1:])
        if not statics:
            statics['hubs'] = {'HKLM': _winreg.HKEY_LOCAL_MACHINE}

        def enum_nodes(curpath, level):
            if level < 1:
                return {}
            res = {}
            try:
                aKey = _winreg.OpenKey(statics['hubs'][hub], curpath, 0, _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY)
            except WindowsError:
                return res

            try:
                i = 0
                while True:
                    name, value, _ = _winreg.EnumValue(aKey, i)
                    i += 1
                    res[name] = value
            except WindowsError:
                pass

            keys = []
            try:
                i = 0
                while True:
                    key = _winreg.EnumKey(aKey, i)
                    i += 1
                    keys.append(key)
            except WindowsError:
                pass

            _winreg.CloseKey(aKey)

            for key in keys:
                res[key] = enum_nodes(curpath + '\\' + key, level - 1)

            return res

        return enum_nodes(path, depth)


def get_vs_versions():
    if sys.platform != 'win32':
        return []
    bush = read_registry(r'HKLM\SOFTWARE\Microsoft\VisualStudio', 2)

    versions = []
    for key, val in bush.iteritems():
        if '.' not in key:
            continue
        version = key.split('.')[0]
        if int(version) >= 12 and 'VC' in val:
            versions.append(version)
    if not versions:
        print "No Visual Studio version found"
    return sorted(versions)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    vs_versions = get_vs_versions()
    parser.add_argument("-i", "--install", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("--force_bits", choices=["32", "64"])
    parser.add_argument("-a", "--android", action="store_true")
    parser.add_argument("-c", "--clean", action="store_true")
    if sys.platform == 'win32' and vs_versions:
        parser.add_argument("--vs", choices=vs_versions, default=vs_versions[0])
    args = parser.parse_args()

    yocto = get_yocto()
    if args.force_bits:
        target_bits = [args.force_bits]
    else:
        if not yocto:
            target_bits = ['64']
            if (sys.platform != 'darwin') or args.android: #on MAC OSX we produce FAT library including both 32 and 64 bits
                target_bits.append('32')
        else:
            target_bits = [yocto['bits']]

    print "target_bits", target_bits

    jdk_path = GetJDKPath()
    print "Found JDK:", jdk_path

    work_dir = os.getcwd()
    print work_dir
    for bits in target_bits: #create separate build dirs
        work_folder = os.path.join(work_dir, "build_" + ("android" if args.android else "yocto" if yocto else sys.platform.replace('32', "")), bits)
        already_there = os.path.exists(work_folder)
        if already_there and args.clean:
            shutil.rmtree(work_folder)
            already_there = False
        if not already_there:
            os.makedirs(work_folder)
        print work_folder
        os.chdir(work_folder)

        if args.android:
            if os.environ.has_key('ANDROID_NDK'):
                run_shell('cmake "%s" -G"%s" %s' % (work_dir, ("Ninja" if sys.platform == 'win32' else "Unix Makefiles"), " ".join([
                    ("-DFORCE_32=ON" if bits == '32' else ""),
                    ("-DCMAKE_BUILD_TYPE=Debug" if args.debug else ""),
                    ("-DCMAKE_TOOLCHAIN_FILE=./android.toolchain.cmake"),
                    ("-DANDROID_NDK=%s" % (os.environ['ANDROID_NDK'])),
                    ("-DCMAKE_BUILD_TYPE=%s" % ("Debug" if args.debug else "Release")),
                    ('-DANDROID_ABI="%s"' % ('x86' if bits == '32' else 'x86_64')),
                    (('-DJDK="%s"' % jdk_path) if jdk_path else "")
                ])))
                run_shell('cmake --build .')
            else:
                print "Set ANDROID_NDK environment to build Android!"
            continue
        if sys.platform == 'win32':
            if vs_versions:
                generator = ('Visual Studio %s' % args.vs) + (' Win64' if bits == '64' else '')
            else:
                generator = 'Ninja'
        else:
            generator = 'Unix Makefiles'
        run_shell('cmake "%s" -G"%s" %s' % (work_dir, generator, " ".join([
            ("-DFORCE_32=ON" if bits == '32' else ""),
            ("-DCMAKE_BUILD_TYPE=Debug" if args.debug else ""),
            ("-DYOCTO=1" if yocto else ""),
            (('-DJDK="%s"' % jdk_path) if jdk_path else "")
        ])))
        if sys.platform == 'win32':
            install = args.install and bits == target_bits[-1]
            target_project = 'PACKAGE' if install else 'ALL_BUILD' #making install only on last config, to pack them all
            run_shell('cmake --build . --config %s --target %s' % ('Debug' if args.debug else 'Release', target_project))
            if install:
                run_shell(r'echo f | xcopy "IntelSEAPI*.exe" "%s\IntelSEAPI.exe" /F' % get_share_folder())
        else:
            import glob
            run_shell('make -j4')
            if not args.install or ('linux' in sys.platform and bits == '64'):
                continue #don't pack on first round, instead on the second pass collect all
            run_shell('cpack "%s"' % work_dir)
            installer = glob.glob(os.path.join(work_folder, "IntelSEAPI*.sh"))[0]
            print installer
            if sys.platform == 'darwin':
                replace_in_file(installer, [
                    ('toplevel="`pwd`"', 'toplevel="/Applications"'),
                    ('exit 0', 'open "${toplevel}/ReadMe.txt"; mkdir -p ~/"Library/Application Support/Instruments/PlugIns/Instruments"; ln -F -s "${toplevel}/dtrace/IntelSEAPI.instrument" ~/"Library/Application Support/Instruments/PlugIns/Instruments/IntelSEAPI.instrument"; exit 0')
                ])
            elif 'linux' in sys.platform:
                replace_in_file(installer, [
                    ('toplevel="`pwd`"', 'toplevel="/opt/intel"'),
                    ('exit 0', 'open "${toplevel}/ReadMe.txt"; exit 0')
                ])

if __name__== "__main__":
    main()


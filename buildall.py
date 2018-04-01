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

from __future__ import print_function
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
    print("\n>>", cmd)
    os.system(cmd)


def replace_in_file(file, what_by):
    import fileinput
    for line in fileinput.input(file, inplace=True):
        for (what, by) in what_by:
            if what in line:
                line = line.replace(what, by)
        sys.stdout.write(line)


def get_yocto():
    if 'CXX' not in os.environ:
        return None
    cxx = os.environ['CXX']
    if '-poky' not in cxx:
        return None
    if '-m32' in cxx:
        return {'bits': '32'}
    return {'bits': '64'}

if sys.platform == 'win32':
    def read_registry(path, depth=0xFFFFFFFF, statics={}):
        try:
            import _winreg
        except ImportError:
            import winreg as _winreg
        parts = path.split('\\')
        hub = parts[0]
        path = '\\'.join(parts[1:])
        if not statics:
            statics['hubs'] = {'HKLM': _winreg.HKEY_LOCAL_MACHINE, 'HKCL': _winreg.HKEY_CLASSES_ROOT}

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


def locate_exact(what):
    try:
        items = subprocess.check_output(['locate', what]).decode("utf-8").split('\n')
    except Exception:
        return []
    return [item for item in items if item.endswith(what)]

def find_in(locations, what):
    try:
        items = subprocess.check_output(['find'] + locations + ['-name', what]).decode("utf-8").split('\n')
    except Exception:
        return []
    return [item for item in items if item.endswith(what)]

def GetJDKPath():
    if sys.platform == 'win32':
        bush = read_registry(r'HKLM\SOFTWARE\JavaSoft\Java Development Kit')
        subkeys = sorted([key for key in bush if 'JavaHome' in bush[key]])
        if subkeys:
            return bush[subkeys[-1]]['JavaHome']
        return None
    else:
        path, err = subprocess.Popen("which javah", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if err or not path:
            return None
        if sys.platform == 'darwin':
            javacs = locate_exact('javac')
            if not javacs:
                return None
            jnis = locate_exact('jni.h')
            if jnis:
                longest = {'prefix': '', 'jni': '', 'java': ''}
                for jni in jnis:
                    if '/Volumes' in jni:
                        continue
                    for java in javacs:
                        if '/Volumes' in java:
                            continue
                        prefix = os.path.commonprefix([jni, java])
                        if len(prefix) > len(longest['prefix']):
                            longest = {'prefix': prefix, 'jni': jni, 'java': java}
                return longest['prefix'].rstrip('/')
            else:
                path = subprocess.check_output("/usr/libexec/java_home").decode("utf-8").split('\n')[0]
                return path if os.path.exists(path) else None
        else:
            matches = []
            for root, dirnames, filenames in os.walk('/usr/lib/jvm'):
                for filename in fnmatch.filter(filenames, 'jni.h'):
                    matches.append(os.path.join(root, filename))
            if not matches:
                return None
            return os.path.split(matches[0])[0]


def get_vs_versions():  # https://www.mztools.com/articles/2008/MZ2008003.aspx
    if sys.platform != 'win32':
        return []
    versions = []
    """
    bush = read_registry(r'HKLM\SOFTWARE\Microsoft\VisualStudio', 2)
    print(bush)

    for key in bush:
        if '.' not in key:
            continue
        version = key.split('.')[0]
        if int(version) >= 12:
            versions.append(version)
    """
    hkcl = read_registry(r'HKCL', 1)
    for key in hkcl:
        if 'VisualStudio.DTE.' in key:
            version = key.split('.')[2]
            if int(version) >= 12:
                versions.append(version)

    if not versions:
        print("No Visual Studio version found")
    return sorted(versions)


def detect_cmake():
    if sys.platform == 'darwin':
        path, err = subprocess.Popen("which cmake", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if not path.strip():
            path, err = subprocess.Popen("which xcrun", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            if not path.strip():
                print("No cmake and no XCode found...")
                return None
            return 'xcrun cmake'
    return 'cmake'


def main():
    import argparse
    parser = argparse.ArgumentParser()
    vs_versions = get_vs_versions()
    parser.add_argument("-i", "--install", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("--force_bits", choices=["32", "64"])
    parser.add_argument("-a", "--android", action="store_true")
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("-c", "--clean", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--no_java", action="store_true")
    if sys.platform == 'win32' and vs_versions:
        parser.add_argument("--vs", choices=vs_versions, default=vs_versions[0])
    args = parser.parse_args()

    yocto = get_yocto()
    if args.force_bits:
        target_bits = [args.force_bits]
    else:
        if not yocto:
            target_bits = ['64']
            if (sys.platform != 'darwin') or args.android:  # on MAC OSX we produce FAT library including both 32 and 64 bits
                target_bits.append('32')
        else:
            target_bits = [yocto['bits']]

    print("target_bits", target_bits)

    jdk_path = GetJDKPath() if not args.no_java else None
    print("Found JDK:", jdk_path)

    perf_co_pilot = find_in(['/usr/lib', '/usr/local/lib'], 'libpcp_mmv.a') if sys.platform != 'win32' else None
    print("Found co-pilot:", perf_co_pilot)

    work_dir = os.getcwd()
    print(work_dir)
    if args.clean:
        bin_dir = os.path.join(work_dir, 'bin')
        if os.path.exists(bin_dir):
            shutil.rmtree(bin_dir)
    for bits in target_bits:  # create separate build dirs
        work_folder = os.path.join(work_dir, "build_" + ("android" if args.android else "yocto" if yocto else sys.platform.replace('32', "")), bits)
        already_there = os.path.exists(work_folder)
        if already_there and args.clean:
            shutil.rmtree(work_folder)
            already_there = False
        if not already_there:
            os.makedirs(work_folder)
        print("work_folder: ", work_folder)
        os.chdir(work_folder)

        cmake = detect_cmake()
        if not cmake:
            print("Error: cmake is not found")
            return

        if args.android:
            if args.arm:
                abi = 'armeabi' if bits == '32' else 'arm64-v8a'
            else:
                abi = 'x86' if bits == '32' else 'x86_64'
            if os.environ.has_key('ANDROID_NDK'):
                run_shell('%s "%s" -G"%s" %s' % (cmake, work_dir, ("Ninja" if sys.platform == 'win32' else "Unix Makefiles"), " ".join([
                    ("-DFORCE_32=ON" if bits == '32' else ""),
                    ("-DCMAKE_BUILD_TYPE=Debug" if args.debug else ""),
                    ("-DCMAKE_TOOLCHAIN_FILE=./android.toolchain.cmake"),
                    ("-DANDROID_NDK=%s" % (os.environ['ANDROID_NDK'])),
                    ("-DCMAKE_BUILD_TYPE=%s" % ("Debug" if args.debug else "Release")),
                    ('-DANDROID_ABI="%s"' % abi),
                    (('-DJDK="%s"' % jdk_path) if jdk_path else ""),
                    ('-DCO_PILOT=1' if perf_co_pilot else ""),
                    ('-DCMAKE_VERBOSE_MAKEFILE:BOOL=ON' if args.verbose else '')
                ])))
                run_shell('%s --build .' % cmake)
            else:
                print("Set ANDROID_NDK environment to build Android!")
            continue
        if sys.platform == 'win32':
            if vs_versions:
                generator = ('Visual Studio %s' % args.vs) + (' Win64' if bits == '64' else '')
            else:
                generator = 'Ninja'
        else:
            generator = 'Unix Makefiles'
        run_shell('%s "%s" -G"%s" %s' % (cmake, work_dir, generator, " ".join([
            ("-DFORCE_32=ON" if bits == '32' else ""),
            ("-DCMAKE_BUILD_TYPE=Debug" if args.debug else ""),
            ("-DYOCTO=1" if yocto else ""),
            (('-DJDK="%s"' % jdk_path) if jdk_path else ""),
            ('-DCO_PILOT=1' if perf_co_pilot else ""),
            ('-DCMAKE_VERBOSE_MAKEFILE:BOOL=ON' if args.verbose else '')
        ])))
        if sys.platform == 'win32':
            install = args.install and bits == target_bits[-1]
            target_project = 'PACKAGE' if install else 'ALL_BUILD'  # making install only on last config, to pack them all
            run_shell('%s --build . --config %s --target %s' % (cmake, ('Debug' if args.debug else 'Release'), target_project))
            if install:
                run_shell(r'echo f | xcopy "IntelSEAPI*.exe" "%s\IntelSEAPI.exe" /F' % get_share_folder())
        else:
            import glob
            run_shell('%s --build . --config %s' % (cmake, ('Debug' if args.debug else 'Release')))
            if not args.install or ('linux' in sys.platform and bits == '64'):
                continue  # don't pack on first round, instead on the second pass collect all
            run_shell('%s --build . --config %s --target package' % (cmake, ('Debug' if args.debug else 'Release')))

            installer = glob.glob(os.path.join(work_folder, "IntelSEAPI*.sh"))[0]
            print(installer)
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


#!/bin/sh
SCRIPT_NAME=$(perl -e 'use Cwd "abs_path"; print abs_path(@ARGV[0])' -- "$0")
BASEDIR=$(dirname ${SCRIPT_NAME})
python ${BASEDIR}/runtool/sea_runtool.py "$@"

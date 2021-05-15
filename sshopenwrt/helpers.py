#!/usr/bin/env python3
"""
run command and capture output (and other helpers)
"""
import sys
import shlex
import re
import subprocess
import concurrent.futures as futures

def grep(s, regex):
    regex = f".*({regex}).*"
    lines = s.split("\n")
    for line in lines:
        line = line.strip()
        if re.match(regex, line):
            yield line

def run_command(cmdline, cwd=None, files=(sys.stdout,), readline=False):
    """
    Run commandline while writing to all file objects in `files`.
    If `files` contains `sys.stdout`, command output will be printed
    on-the-fly.
    `files` can also contain an `open("some.log", "a")` object thus
    resulting in all output being appended to that log file too.

    :param cmdline:  Command line to run
    :param cwd:      Working directory or None
    :param files:    List of file objects to write output to
    :param readline: Use readline() instead of read().
                     This should be False if user input prompts are expected
    :return:         exitstatus, stdout, stderr
    """
    def popen_pipe(proc, ioreader):
        s = ""
        while proc.poll() is None:
            if readline:
                data = ioreader.readline().decode("utf8", "backslashreplace")
            else:
                data = ioreader.read().decode("utf8", "backslashreplace")
            s += data
            for file in files:
                file.write(data)
                file.flush()

        # execute_cap remaining buffer
        data = ioreader.read().decode("utf8", "backslashreplace")
        s += data
        for file in files:
            file.write(data)
            file.flush()

        return s

    stdout, stderr = "", ""
    args = shlex.split(cmdline)
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd) as proc:
        with futures.ThreadPoolExecutor(2) as pool:
            jobs = [
                pool.submit(popen_pipe, proc, proc.stdout),
                pool.submit(popen_pipe, proc, proc.stderr),
            ]
            futures.wait(jobs)
            try:
                stdout = jobs[0].result()
                stderr = jobs[1].result()
            except Exception as e:
                print("Exception in thread: ", e)

    return proc.returncode, stdout, stderr


def which(program):
    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

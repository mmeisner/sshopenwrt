#!/usr/bin/env python3
import os
import re
import sys
import time

from .helpers import run_command
from .log import Log


###############################################################################
# ssh
###############################################################################

class CommandFailed(Exception):
    def __init__(self, status, stderr="", cmd=None):
        msg = f"Command failed with exit status {status}\n{stderr.strip()}"
        super().__init__(msg)

class SshConn(object):
    def __init__(self, host, ssh_identity=None, dryrun=False, log=None):
        """
        :param host:  String of the form "user@hostname" where "user@" is optional
        """
        self.user_host = host
        if "@" in host:
            _, self.host = host.split("@")
        else:
            self.host = host

        # -q  Quiet mode. Causes most warning and diagnostic messages to be suppressed.
        self.args = "-q"
        if ssh_identity:
            self.args += f" -i {ssh_identity}"
        # suppress "Warning: Permanently added '192.168.1.1' (RSA) to the list of known hosts"
        self.args += " -oLogLevel=error"
        # -x  Disables X11 forwarding (in case it is on by default in .ssh/config)
        self.ssh_args = "-x"

        # avoid "REMOTE HOST IDENTIFICATION HAS CHANGED" error/warning
        args_nowarn = "-oUserKnownHostsFile=/dev/null -oStrictHostKeyChecking=no"
        # This option can also tbe useful if the IP changes frequently:
        args_nowarn_ip = "-oCheckHostIP=no"

        self.dryrun = dryrun

        # prepare SSH ControlMaster
        self.control_persist = 600
        path = os.path.expanduser(f"~/.ssh/openwrt-{self.user_host}")
        self.args += f" -oControlPath={path} -oControlPersist={self.control_persist} -oControlMaster=auto"

        self.log = log or Log()

    def cmdline(self, cmd, ssh_args=""):
        """
        Return full ssh command line

        :param cmd:
        :param ssh_args: additional ssh arguments
        :return:
        """
        return f"ssh -t {self.ssh_args} {self.args} {ssh_args} {self.user_host} '{cmd}'"

    def capture(self, cmd, with_stdout=False, ssh_args=""):
        """
        Execute `cmd` and capture stdout and stderr, optionally printing output on the fly

        :param cmd:         Command to run
        :param with_stdout: True to print output on the fly
        :param ssh_args: additional ssh arguments
        :return:            status, stdout, stderr
        """
        self.log.cmd(cmd)
        if self.dryrun:
            return 0, "", ""

        ssh_cmd = self.cmdline(cmd, ssh_args=ssh_args)
        files = [sys.stdout] if with_stdout else []
        return run_command(ssh_cmd, files=files)

    def scp_capture(self, cmd, with_stdout=False):
        """
        Same as ssh_cap but for scp

        :param cmd:         Command to run
        :param with_stdout: True to print output on the fly
        :return:            status, stdout, stderr
        """
        self.log.cmd(f"scp {cmd}")
        if self.dryrun:
            return 0, "", ""

        scp_cmd = f"scp {self.args} {cmd}"
        files = [sys.stdout] if with_stdout else []
        return run_command(scp_cmd, files=files)

    def capture_ok(self, cmd, with_stdout=False, ssh_args=""):
        """
        Execute `cmd` over SSH session and capture/return output
        Exit with error if command fails

        :param cmd: commandline
        :param with_stdout: True to print output on the fly
        :param ssh_args: additional ssh arguments
        :return:    stdout
        """
        status, stdout, stderr = self.capture(cmd, with_stdout=with_stdout, ssh_args=ssh_args)
        if status != 0:
            raise CommandFailed(status, stderr=stderr)
        return stdout

    def execute(self, cmd):
        """
        Execute `cmd` over SSH session, printing output while running
        Exit with error if command fails

        :param cmd: commandline
        :return:    stdout
        """
        return self.capture_ok(cmd, with_stdout=True)

    def copy_to(self, src, dest):
        cmd = f"-r {src} {self.user_host}:{dest}"
        status, stdout, stderr = self.scp_capture(cmd, with_stdout=True)
        if status != 0:
            raise CommandFailed(status, stderr=stderr)

    def copy_from(self, src, dest):
        cmd = f"-r {self.user_host}:{src} {dest}"
        status, stdout, stderr = self.scp_capture(cmd, with_stdout=True)
        if status != 0:
            raise CommandFailed(status, stderr=stderr)

    def ping_wait(self, host=None, timeout=10):
        """
        Ping host until it responds or timeout after `timeout` seconds.

        :param host:    host to ping (default is SSH connection IP)
        :param timeout: timeout in seconds
        :return:
        """
        started = time.time()
        deadline = started + timeout
        cmd = f"ping -n -q -c1 -w1 {host}"
        self.log.cmd(cmd)
        while time.time() < deadline:
            status, stdout, stderr = run_command(cmd, files=[])
            if status == 0:
                return
            elapsed = time.time() - started
            print(f"\rping {elapsed:.0f} of {timeout}s", end='')
        print()
        raise TimeoutError(f"Ping timeout after {timeout}s")

    def ping_wait_offline(self, host=None, timeout=10, min_offline_time=3):
        """
        Ping `host` for a total of max `timeout` seconds, returning
        successfully when no ping response has been received for
        `min_no_response_time` seconds.
        
        :param host:    host to ping (default is SSH connection IP)
        :param timeout: timeout in seconds
        :param min_offline_time: Minimum number of seconds to of no ping replies
        :return: 
        """
        host = host if host else self.host
        started = time.time()
        deadline = started + timeout
        cmd = f"ping -n -q -c1 -w1 {host}"
        self.log.cmd(cmd)
        started_to_fail = 0
        while time.time() < deadline:
            status, stdout, stderr = run_command(cmd, files=[])
            elapsed = time.time() - started
            if status == 0:
                print(f"\rping {elapsed:.0f} of {timeout}s, still responding", end='')
                continue

            if started_to_fail == 0:
                started_to_fail = time.time()

            elapsed_failed = time.time() - started_to_fail
            if elapsed_failed > min_offline_time:
                return

            print(f"\rping {elapsed:.0f} of {timeout}s, no response for {elapsed_failed:.0f}s", end='')
        print()
        raise TimeoutError(f"Ping timeout after {timeout}s")


###############################################################################
# openwrt
###############################################################################

class OpenWRT(SshConn):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _uci_cmd(self, cmd, names):
        if type(names) == str:
            names = [names]

        out = [self.capture_ok(f"uci {cmd} {name}") for name in names]
        return "".join(out).rstrip()

    def uci_get(self, name):
        return self._uci_cmd("get", name)

    def uci_show(self, name):
        return self._uci_cmd("show", name)

    def uci_commit(self, commit=False):
        cmd = "uci commit" if commit else "uci changes"
        return self.capture_ok(cmd).rstrip()

    def uci_set(self, key_values, commit=False):
        if type(key_values) == str:
            raise TypeError("bad argument type")
        if type(key_values) == dict:
            for k,v in key_values.items():
                cmd = f"uci set {k}={v}"
                self.capture_ok(cmd).rstrip()
        elif len(key_values) == 2 and type(key_values[0]) == str:
            k, v = key_values
            cmd = f"uci set {k}={v}"
            self.capture_ok(cmd).rstrip()
        else:
            for k,v in key_values:
                cmd = f"uci set {k}={v}"
                self.capture_ok(cmd).rstrip()
        self.uci_commit(commit=commit)

    def uci_add(self, config, section=None):
        if not section:
            config, section = config.split(".")
        cmd = f"uci add {config} {section}"
        return self.capture_ok(cmd).rstrip()

    #### config helpers #######################################################

    def configure_iface_ipv4(self, iface, proto, ipaddr, netmask, gw=None, commit=False):
        if not (iface and proto and ipaddr and netmask):
            raise ValueError("Bad argument/value(s)")
        config = {
            f"network.{iface}.proto": f"{proto}",
            f"network.{iface}.ipaddr": f"{ipaddr}",
            f"network.{iface}.netmask": f"{netmask}",
        }
        if gw is not None:
            config[f"network.{iface}.gateway"] = gw

        self.uci_set(config)
        return self.uci_commit(commit=commit)

    #### misc #################################################################

    def hostname(self):
        return self.uci_get("system.@system[0].hostname")

    def get_release(self, **kwargs):
        out = self.capture_ok("cat /etc/os-release", **kwargs)
        m = re.search(r'^[\w]+_RELEASE=\"([^\"]+)\"', out, re.MULTILINE)
        return m[1] if m else ""

    def service_restart(self, name):
        cmd = f"/etc/init.d/{name} restart"
        return self.execute(cmd)


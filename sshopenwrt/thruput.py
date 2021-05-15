import json
import ipaddress as ipa
import statistics as stats

from .openwrt import *
from .helpers import *

class ThruputTest(object):
    """
    Perform router throughput test WAN to LAN and/or WAN to LAN

    localhost starts iperf3 client that connects to iperf3 test server.
    iperf3 data goes through the router via its LAN interface.

    Localhost and router are automatically configured while the
    test server is semi-automatically configured: The script will
    print the network configuration commands that you have to execute
    manually on the test server: either at the console or via an
    SSH connection (on an alternate interface/IP such as WIFI).

    By default, iperf3 is executed twice: once for downlink direction
    (WAN to LAN) and once for uplink direction (LAN to WAN)

    +-----------+    +-----------+            +-------------+
    | localhost |    | router    |            | test server |
    | iperf3 -c |    |           |            | iperf3 -s   |
    |           |    |           |  test_net  |             |
    |           |    |       WAN +------------+ IFNAME      |
    |           |    |           |            |             |
    +-----+-----+    +----+------+            +----+--------+
          |               |                        | (opt)
          |               |                        |
    LAN --+---------------+------------------------+-- LAN
    """
    def __init__(self, openwrt:OpenWRT, localhost_run_command_ok,
                 test_server_ip, test_server_ifname=None, test_server_ssh_ip=None,
                 router_wan_ifname="eth1"):
        """
        
        :param openwrt: 
        :param localhost_run_command_ok: 
        :param test_server_ip: 
        :param test_server_ifname:
        :param test_server_ssh_ip:
        """
        self.localhost_run_command_ok = localhost_run_command_ok
        self.openwrt = openwrt
        self.log = openwrt.log

        self.router_wan_ifname = router_wan_ifname

        try:
            self.router_lan_ip = ipa.ip_address(self.openwrt.host)
        except ValueError:
            self.log.error(f"Invalid router IP supplied to {self.__class__.__name__}")
            raise

        self.server_ifname = test_server_ifname
        self.test_server_ssh_ip = test_server_ssh_ip
        if not "/" in test_server_ip:
            test_server_ip += "/24"
        try:
            self.server_iface = ipa.ip_interface(test_server_ip)
        except ValueError:
            self.log.error(f"Invalid test_server IP supplied to {self.__class__.__name__}")
            raise

        self.test_net = ipa.ip_network(self.server_iface, strict=False)
        self.test_netmask = self.test_net.netmask
        self.server_ip = self.server_iface.ip
        # set router WAN IP to first IP address in network
        self.router_wan_ip = self.test_net[1]

        self.log.info(f"""Using:
  router_lan={self.router_lan_ip}
  router_wan={self.router_wan_ip} network={self.test_net} test_host={self.server_ip}""")

    def setup_localhost(self):
        self.log.header("Setting up route on localhost")
        out = self.localhost_run_command_ok(f"ip route show exact {self.test_net}").strip()
        if f"{self.router_lan_ip}" in out:
            self.log.info(f"IP route to {self.server_ip} via router/{self.router_lan_ip} already exists on LOCALHOST, OK")
            self.log.info("    " + out)
        else:
            self.log.info(f"Adding IP route to {self.server_ip} via router/{self.router_lan_ip}, on LOCALHOST:")
            self.log.info("This will ask for your LOCALHOST sudo password...")
            self.localhost_run_command_ok(f"sudo ip route add {self.test_net} via {self.router_lan_ip}",
                                          accept_stderr="File exists")

    def setup_iperf_server_host(self):
        self.log.header("Setting up iperf3 test server")
        self.log.info(f"Pinging test host (iperf3 server): {self.server_ip}")
        try:
            self.openwrt.ping_wait(self.server_ip, 1)
            self.log.info(f"test host {self.server_ip} responds to ping, OK")
            return
        except TimeoutError:
            self.log.error(f"Failed to ping test host {self.server_ip}")
            self.log.note(f"""\
Please configure test host with following commands:")
  # tell network manager to stop managing this ethernet interface
  nmcli dev set {self.server_ifname} managed no
  sudo nmcli dev reapply {self.server_ifname}
  # this should show 'disconnected' for the '{self.server_ifname}' interface
  nmcli dev status
  sudo ip addr add {self.server_iface} dev {self.server_ifname}
  sudo ip link set {self.server_ifname} up
  iperf3 -s
where IFNAME is the ethernet interface name, e.g. enp31s0, eth0 or whatever""")
            sys.exit(1)

    def setup_router(self):
        self.log.header("Setting up router WAN")
        # check is WAN interface is defined, otherwise create it
        status, out, err = self.openwrt.capture("uci get network.wan", with_stdout=True)
        if status != 0 and any(["Entry not found" in x for x in (out, err)]):
            self.log.info("network.wan not found, will create it")
            self.openwrt.uci_add("network", "wan")
            config = {"network.wan": "interface", "network.wan.ifname": self.router_wan_ifname}
            self.openwrt.uci_set(config, commit=True)
        else:
            self.log.info("network.wan already configured on router, OK")

        # get current WAN IPv4 config:
        # get interface name for the WAN. Then get IP config for that interface.
        wan_iface = self.openwrt.uci_get("network.wan.ifname")
        out = self.openwrt.capture_ok(f"ip -4 -o addr show dev {wan_iface}").strip()
        if f"{self.router_wan_ip}" in out:
            self.log.info(f"router already has WAN iface configured with {self.router_wan_ip}, OK")
            self.log.info(f"  {out}")
        else:
            self.log.info("Configuring WAN iface with static ipaddr")
            self.openwrt.configure_iface_ipv4("wan", "static", self.router_wan_ip, self.test_netmask, commit=True)
            self.openwrt.service_restart("network")

        try:
            self.log.info(f"Pinging router WAN: {self.router_wan_ip}")
            self.openwrt.ping_wait(self.router_wan_ip, 5)
        except TimeoutError:
            raise

        out = self.openwrt.capture_ok("cat /etc/os-release")
        self.log.info("\n".join(grep(out, "_RELEASE")))

    def setup_all(self):
        # first setup route from localhost through router to iperf3 server
        self.setup_localhost()

        # setup router WAN interface
        self.setup_router()

        # setup iperf3 server after setting up router and localhost routing
        # otherwise we cannot ping the host to see if it already setup
        self.setup_iperf_server_host()

    def run_iperf3(self, num=1, duration=10, down=True, up=True, with_json=True):
        self.log.note(f"Running iperf3 to {self.server_ip}: {num} iteration(s) of {duration}s")
        cmd = f"iperf3 -t{duration}"
        with_stdout = not with_json
        if with_json:
            cmd += " --json"
        cmd += f" -c {self.server_ip}"

        try:
            self.localhost_run_command_ok(f"{cmd} -R -t1")
        except CommandFailed:
            self.log.error(f"Failed to connect to iperf3 on {self.server_ip}. Is iperf3 started?")
            sys.exit(1)

        def print_stats(prefix, data):
            stddev = stats.stdev(data) if len(data) > 1 else 0
            self.log.info(f"{prefix} stats of {num} runs of {duration}s:"
                          f" mean={stats.mean(data):.0f} min={min(data):.0f} max={max(data):.0f}"
                          f" stddev={stddev:.0f}")

        def iperf_json_summary(s):
            if not s:
                return 0, 0, 0
            j = json.loads(s)
            recv_bps = int(j['end']['sum_received']['bits_per_second'])
            retransmits = int(j['end']['streams'][0]['sender']['retransmits'])
            recv_mbps = int(recv_bps / 1000000)
            max_gpbs_with_tcp = 969
            pct_of_max = 100 * recv_mbps / max_gpbs_with_tcp
            return recv_mbps, pct_of_max, retransmits

        up_list = []
        up_retrans_list = []
        down_list = []
        down_retrans_list = []
        for i in range(num):
            self.log.info(f"Loop {i + 1} of {num}")
            dl, ul = "", ""
            if down:
                dl = self.localhost_run_command_ok(f"{cmd} -R", with_stdout=with_stdout)
            if up:
                ul = self.localhost_run_command_ok(cmd, with_stdout=with_stdout)

            if with_json and down:
                recv_mbps, pct_of_max, retransmits = iperf_json_summary(dl)
                self.log.info(
                    f"  WAN to LAN: {recv_mbps}Mbps (approx {pct_of_max:.1f}% of max, {retransmits} retransmits)")
                down_list.append(recv_mbps)
            if with_json and up:
                recv_mbps, pct_of_max, retransmits = iperf_json_summary(ul)
                self.log.info(
                    f"  LAN to WAN: {recv_mbps}Mbps (approx {pct_of_max:.1f}% of max, {retransmits} retransmits)")
                up_list.append(recv_mbps)

        if with_json:
            self.log.info("-" * 60)
            if down:
                print_stats("WAN to LAN", down_list)
            if up:
                print_stats("LAN to WAN", up_list)

    def setup_iperf_server_host_via_ssh(self, ssh_host):
        """
        This function is not really working because it needs sudo over the SSH
        connection and that fails miserably without prompting properly.
        Maybe we could propose the user to add an entry to the /etc/sudoers file?

        :param ssh_host:
        :return:
        """
        self.log.info(f"Trying SSH connection to {ssh_host}")
        ssh = SshConn(ssh_host, log=self.log)

        status, _, _ = ssh.capture("uname", with_stdout=True)
        if status != 0:
            self.log.die(f"ssh connection to {ssh_host} FAILED")
        self.log.good(f"ssh connection to {ssh_host} OK, proceeding with network setup...")

        cmd = "which nmcli"
        status, out, err = ssh.capture(cmd, with_stdout=True)
        if status != 0:
            self.log.error(f"nmcli command not found on {ssh_host}")
            self.log.die(f"You have to setup test server host manually")

        cmd = "nmcli conn show id thruput |grep ipv4.addr"
        status, out, err = ssh.capture(cmd, with_stdout=True)
        if status != 0 and "no such connection profile" in out:

            cmd = f"sudo -S nmcli conn add type ethernet con-name thruput ifname {self.server_ifname} ip4 {self.server_iface}"
            status, out, err = ssh.capture(cmd, with_stdout=True)
            if status != 0:
                self.log.die(f"network setup FAILED")
        else:
            self.log.good(f"{ssh_host} already has nmcli connection for thruput test, OK")

        cmd = "nmcli dev status | grep thruput"
        out = ssh.capture_ok(cmd, with_stdout=True)
        if "connected" in out:
            self.log.good(f"{ssh_host} already has nmcli connection active, OK")
        else:
            cmd = "sudo -S nmcli conn up id thruput"
            status, out, err = ssh.capture(cmd, with_stdout=True)
            if status != 0:
                self.log.die(f"FAILED to bring up nmcli 'thruput' connection")

        cmd = "pgrep iperf3"
        status, out, _ = ssh.capture(cmd, with_stdout=True)
        if status == 0:
            self.log.good(f"{ssh_host} already has iperf3 running, OK")
        else:
            self.log.note(f"Please launch command on {ssh_host}: iperf3 -s")
            sys.exit(0)


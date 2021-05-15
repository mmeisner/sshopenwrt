# Overview

This Python3 script/module can perform remote control of an OpenWRT
router. Currently, it has the following commands/procedures:

  - `info`: get and print some basic info from the router
  - `upgrade`: perform system firmware upgrade from file
  - `thruput`: setup and run WAN/LAN and LAN/WAN throughput test
  - and a few more...

The script should be fairly easy to extend with new commands/precedures.

## Command line help

```
usage: ssho [-c HOST] [-v] [-q] [-n] [-d] [-h] COMMAND ...

SSH OpenWRT Control Automatron: SSH to OpenWRT router and execute
various operations.

Script uses SSH control master connection for maximum SSH connection speed.
You should have a proper .ssh/config for the router device.  

positional arguments:
  COMMAND   Command to execute:
    info    Get overview info from host
    upgrade Perform firmware upgrade
    backup  Perform config backup and save the file locally
    iface   Configure network interface
    thruput Perform wired WAN/LAN thruput test using iperf3

Global Options:
  -c HOST  Host to connect to. REQUIRED argument.
  -v       Be more verbose
  -q       Be more quiet
  -n       Dry run
  -d       Show full backtrace on exception
  -h       Show usage. Give option twice to see usage examples
```

----
Convert this markdown doc to HTML with pandoc: 

`pandoc --toc --self-contained -t html -o README.html README.md`

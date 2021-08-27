#!/usr/bin/python

# datacola.py: a data collecting script
# this can be run out of cron

# Michael Stroucken <stroucki@andrew.cmu.edu> 2011-10-18
# based on shellscript by Isildur 2006-09-14

import os.path
import random
import time
import platform
import re
import subprocess

bufsizefilename = '/var/run/rten'
# filename to store number of records to buffer before writing
# to permanent storage
loadavgfilename = '/proc/loadavg'
# filename to read load average data from
netfilename = '/proc/net/dev'
# filename to read network interface stats from
netprevfilename = '/var/run/datacola-net'
# filename to store previous network stats in
diskfilename = '/proc/diskstats'
# filename to read disk stats from
diskprevfilename = '/var/run/datacola-disk'
# filename to store previous disk stats in
bufferfilename = '/var/run/datacola-data'
# filename to hold data rows until being moved out
storagefilebase = '/root/datacola/'
# directory to hold data row archives

def nonneg(value: int) -> int:
    # Force value to be 0 or greater, in case of overflow
    # or other problem
    if value < 0:
        return 0
    else:
        return value

# determine number of rows to buffer before moving them
# over the network. This value is chosen to be a random integer
# between 20 and 30. This will spread out archivings. NFS access
# is lock-heavy
bufsize = 0

if os.path.exists(bufsizefilename):
    if os.path.isfile(bufsizefilename):
        try:
            bufsizefile = open(bufsizefilename, 'r')
            bufsize = int(bufsizefile.read())
            bufsizefile.close()
        except:
            pass
    else:
        raise

if bufsize == 0:
    bufsize = random.randint(20, 30)
    bufsizefile = open(bufsizefilename, 'w')
    bufsizefile.write(str(bufsize))
    bufsizefile.close()

# obtain timestamp.
now = int(time.time())

# obtain hostname
hostname = platform.node()

# derive data archive file name
storagefilename = "%s/%s" % (storagefilebase, hostname)

# obtain load1 and number of processes
fh = open(loadavgfilename, 'r')
loadavgline = fh.read()
fh.close()

loadavgdata = loadavgline.split()
load1 = loadavgdata[0]
totalprocs = loadavgdata[3].split('/')[1]

loadavgout = "AN %s %s" % (load1, totalprocs)

# obtain network statistics
# We want the difference over the previous measurement of the following:-
# rxb: received bytes
# txb: transmitted bytes
# rxp: received packets
# txp: transmitted packets
# values are summed over interfaces named "eth*". this should avoid double-
# counting of tuntap and bridge interfaces. though inter-host traffic is
# not counted this way.

fh = open(netfilename, 'r')
lines = fh.readlines()
fh.close()

(currrxp, currtxp, currrxb, currtxb) = (0, 0, 0, 0)
for line in lines[2:]:
    interface = line[:line.index(":")].strip()
    if re.match("eth", interface):
        ifdata = line[line.index(":")+1:].split()
        currrxb += int(ifdata[0])
        currrxp += int(ifdata[1])
        currtxb += int(ifdata[8])
        currtxp += int(ifdata[9])

# try to read previous values
gotnetprevdata = False

if os.path.isfile(netprevfilename):
    try:
        fh = open(netprevfilename, "r")
        netprevline = fh.read()
        fh.close()

        netprevdata = [int(x) for x in netprevline.split()]
        prevrxb, prevrxp, prevtxb, prevtxp = netprevdata
        gotnetprevdata = True
    except:
        os.unlink(netprevfilename)


if gotnetprevdata == True:
    fh = open(netprevfilename, "w")
    fh.write("%s %s %s %s" % (currrxb, currrxp, currtxb, currtxp))
    fh.close()

    rxb = nonneg(currrxb - prevrxb)
    rxp = nonneg(currrxp - prevrxp)
    txb = nonneg(currtxb - prevtxb)
    txp = nonneg(currtxp - prevtxp)

else:
    fh = open(netprevfilename, "w")
    fh.write("%s %s %s %s" % (currrxb, currrxp, currtxb, currtxp))
    fh.close()

    rxb, rxp, txb, txp = (0, 0, 0, 0)

netdata = "NET %s %s %s %s" % (rxb, txb, rxp, txp)

# obtain disk statistics
# We want the difference over the previous measurement of the following:-
# diskreadc: Count of reads issued
# diskreads: Count of sectors read
# diskreadt: ms of read time
# diskwritec: Count of writes issued
# diskwrites: Count of sectors written
# diskwritet: ms of write time
# diskioq: Count of items in disk IO queue
# values are summed over whole disk devices (lower 4 bits of minor == 0).
# this should avoid double-counting of partitions.
fh = open(diskfilename, 'r')
lines = fh.readlines()
fh.close()

currdiskreadc, currdiskreads, currdiskreadt, \
    currdiskwritec, currdiskwrites, currdiskwritet, \
    currdiskioq = (0, 0, 0, 0, 0, 0, 0)

for line in lines:
    major, minor, name, data = line.split(4)
    diskreadc, diskreadm, diskreads, diskreadt, \
        diskwritec, diskwritem, diskwrites, diskwritet, \
        diskioq, diskiot, diskiotw, \
        _, _, _, _ = [int(x) for x in data.split()]

    # I think empty 4 least significant bits signify whole-disk
    if int(minor) & 15 == 0:
        currdiskreadc += int(diskreadc)
        currdiskreads += int(diskreads)
        currdiskreadt += int(diskreadt)
        currdiskwritec += int(diskwritec)
        currdiskwrites += int(diskwrites)
        currdiskwritet += int(diskwritet)
        currdiskioq += int(diskioq)

# try to read previous values
gotdiskprevdata = False

if os.path.isfile(diskprevfilename):
    try:
        fh = open(diskprevfilename, "r")
        diskprevline = fh.read()
        fh.close()

        diskprevdata = [int(x) for x in diskprevline.split()]

        prevdiskreadc, prevdiskreads, prevdiskreadt, \
            prevdiskwritec, prevdiskwrites, prevdiskwritet, \
            prevdiskioq = [int(x) for x in diskprevdata]
        gotdiskprevdata = True

    except:
        os.unlink(diskprevfilename)

if gotdiskprevdata == True:
    fh = open(diskprevfilename, "w")
    fh.write("%s %s %s %s %s %s %s" % \
                 (currdiskreadc, currdiskreads, currdiskreadt,
                  currdiskwritec, currdiskwrites, currdiskwritet,
                  currdiskioq))
    fh.close()

    diskreadc = nonneg(currdiskreadc - prevdiskreadc)
    diskreads = nonneg(currdiskreads - prevdiskreads)
    diskreadt = nonneg(currdiskreadt - prevdiskreadt)
    diskwritec = nonneg(currdiskwritec - prevdiskwritec)
    diskwrites = nonneg(currdiskwrites - prevdiskwrites)
    diskwritet = nonneg(currdiskwritet - prevdiskwritet)
    # diskioq shows rate of change of disk IO queue length, so
    # negative values are appropriate here
    diskioq = currdiskioq - prevdiskioq

else:
    fh = open(diskprevfilename, "w")
    fh.write("%s %s %s %s %s %s %s" % \
                 (currdiskreadc, currdiskreads, currdiskreadt,
                  currdiskwritec, currdiskwrites, currdiskwritet,
                  currdiskioq))
    fh.close()

    diskreadc, diskreads, diskreadt, diskwritec, diskwrites, diskwritet, diskioq = [str(x) for x in (0, 0, 0, 0, 0, 0, 0)]

diskdata = "DISK %s %s %s %s %s %s %s" % \
    (diskreadc, diskreads, diskreadt,
     diskwritec, diskwrites, diskwritet,
     diskioq)

# obtain memory data
# free memory = MemTotal - MemFree - Buffers - Cached
fh = open("/proc/meminfo", "r")
lines = fh.readlines()
fh.close()

core = 0
for line in lines:
    data = line.split()
    if re.match("MemTotal", data[0]):
        core += int(data[1])
    if re.match("MemFree", data[0]):
        core -= int(data[1])
    if re.match("Buffers", data[0]):
        core -= int(data[1])
    if re.match("Cached", data[0]):
        core -= int(data[1])

memdata = "CORE %s" % (core)

# obtain count of logged in uses. Unfortunately I have to fork processes here
users = subprocess.Popen(["/usr/bin/who", "-q"], stdout=subprocess.PIPE).communicate()[0]
usersdata = users.decode('utf8').strip().split()
userscount = usersdata[-1].split("=")[1]

userdata = "US %s" % (userscount)

# generate this row of data
dataline = "host %s dat %s %s %s %s %s %s END\n" % (hostname, now, loadavgout, netdata, diskdata, memdata, userdata)

# read in the buffer of data rows
linecount = 0
if os.path.isfile(bufferfilename):
    fh = open(bufferfilename, "r")
    lines = fh.readlines();
    fh.close()
    linecount = len(lines)

# if the new data row would put it over the limit of lines to buffer,
# append the data to the archive file and truncate the buffer file
if linecount > bufsize:
    try:
        fh = open(storagefilename, "a")
        for line in lines:
            fh.write(line)

        fh.write(dataline)
        fh.close()
            
        fh = open(bufferfilename, "w")
        fh.close()
    except:
        raise
# otherwise add the data to the buffer file
else:
    try:
        fh = open(bufferfilename, "a")
        fh.write(dataline)
        fh.close()
    except:
        raise

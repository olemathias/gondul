import time
import threading
import schedule
import queue
import json
import redis
import os

import pynetbox
import random
import netaddr
import logging
from dotenv import load_dotenv

from prometheus import getPing, getSnmp, getSnmpPorts, getLastTime

logger = logging.getLogger(__name__)

load_dotenv()

cache = redis.Redis(
    connection_pool=redis.ConnectionPool(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=os.environ.get("REDIS_PORT", 6379),
        db=os.environ.get("REDIS_DB", 0),
        decode_responses=True,
    )
)

nb = pynetbox.api(
    os.environ.get("NETBOX_URL"), token=os.environ.get("NETBOX_TOKEN"), threading=True
)


def get_devices():
    devices = {}
    for device in nb.dcim.devices.filter(
        role=[
            "access-switch",
            "distro",
            "firewall",
            "internett-ruter",
            "leaf",
            "oob-switch",
            "spine",
            "utskutt-distro"
        ]
    ):
        if device.status.value in ["decommissioning", "offline"]:
            continue
        # tmp hack to remove vc members
        if device.name in ["d1-ring-tele", "d1-ring-south", "d1-ring-swing", "d1-ring-north", "d1-ring-log", "r2-tele"]:
            continue
        # print(device.name)
        distro = None
        uplink = None
        distro_lag = None
        mgmt_vlan = None
        traffic_vlan = None

        lag = None
        if device.role.slug in ["access-switch", "utskutt-distro"]:
            lag = nb.dcim.interfaces.get(device_id=device.id, name="ae0")
            uplink_interfaces = nb.dcim.interfaces.filter(device_id=device.id, lag_id=lag.id)
            if len(uplink_interfaces) > 0:
                uplink_interface = next(uplink_interfaces)
                uplink_device = uplink_interface.connected_endpoints
                if len(uplink_device) > 0:
                    uplink = uplink_device[0].name
                    distro_lag = uplink_device[0].lag.name
                    distro = uplink_device[0].device.name
            if lag.untagged_vlan is not None:
                mgmt_vlan = lag.untagged_vlan.name
            if device.role.slug == "access-switch" and len(lag.tagged_vlans) > 0:
                traffic_vlan = lag.tagged_vlans[0].name

        if device.custom_fields["gondul_placement"] is None:
            placement = {
                "height": 16,
                "x": random.randrange(50, 1400, 20),
                "y": random.randrange(50, 600, 20),
                "width": 120,
            }
        else:
            placement = device.custom_fields["gondul_placement"]
            if "x" not in placement or placement["x"] is None:
                placement["x"] = random.randrange(50, 1400, 20)
            if "y" not in placement or placement["y"] is None:
                placement["y"] = random.randrange(50, 600, 20)
            if "height" not in placement or placement["height"] is None:
                placement["height"] = 16
            if "width" not in placement or placement["width"] is None:
                placement["width"] = 120

        devices.update(
            {
                device.name: {
                    "sysname": device.name,
                    "netbox_id": device.id,
                    "mgmt_v4_addr": (
                        str(netaddr.IPNetwork(device.primary_ip4.address).ip)
                        if device.primary_ip4 is not None
                        else None
                    ),
                    "mgmt_v6_addr": (
                        str(netaddr.IPNetwork(device.primary_ip6.address).ip)
                        if device.primary_ip6 is not None
                        else None
                    ),
                    "mgmt_vlan": mgmt_vlan,
                    "traffic_vlan": traffic_vlan,
                    "last_updated": device.last_updated,
                    "distro_name": distro,
                    "distro_phy_port": uplink,
                    "distro_lag": distro_lag,
                    "tags": [tag.slug for tag in list(device.tags)],
                    "placement": placement,
                    "serial": device.serial,
                    "platform": (
                        device.platform.slug if device.platform is not None else None
                    ),
                }
            }
        )

    return devices


def generateDevices():
    try:
        start_time = time.time()
        logger.debug("Updating device cache")
        cache.set("devices:updated", round(time.time()))
        cache.set("devices:data", json.dumps(get_devices()))
        logger.debug("Device cache updated")
        logger.debug("--- %s seconds ---" % (time.time() - start_time))
    except Exception as e:
        logger.error(e)

def generatePing():
    try:
        start_time = time.time()
        logger.debug("Updating ping cache")
        cache.set("ping:data", json.dumps(getPing()))
        cache.set("ping:updated", round(float(getLastTime("probe_icmp_duration_seconds", "1m"))))
        logger.debug("Device ping updated")
        logger.debug("--- %s seconds ---" % (time.time() - start_time))
    except Exception as e:
        logger.error(e)

def generateSnmp():
    try:
        start_time = time.time()
        logger.debug("Updating snmp cache")
        cache.set("snmp:data:data", json.dumps(getSnmp()))
        cache.set("snmp:ports:data", json.dumps(getSnmpPorts()))
        cache.set("snmp:updated", round(float(getLastTime("sysName", "5m"))))
        logger.debug("Device snmp updated")
        logger.debug("--- %s seconds ---" % (time.time() - start_time))
    except Exception as e:
        logger.error(e)


# DCIM
def dcim_main():
    while 1:
        job_func = dcim_jobqueue.get()
        job_func()
        dcim_jobqueue.task_done()


dcim_jobqueue = queue.Queue()
dcim_scheduler = schedule.Scheduler()
dcim_scheduler.every(30).seconds.do(dcim_jobqueue.put, generateDevices)
dcim_worker_thread = threading.Thread(daemon=True, target=dcim_main)
dcim_worker_thread.start()


# Ping
def ping_main():
    while 1:
        job_func = ping_jobqueue.get()
        job_func()
        ping_jobqueue.task_done()


ping_jobqueue = queue.Queue()
ping_scheduler = schedule.Scheduler()
ping_scheduler.every(1).seconds.do(ping_jobqueue.put, generatePing)
ping_worker_thread = threading.Thread(daemon=True, target=ping_main)
ping_worker_thread.start()

# Snmp
def snmp_main():
    while 1:
        job_func = snmp_jobqueue.get()
        job_func()
        snmp_jobqueue.task_done()


snmp_jobqueue = queue.Queue()
snmp_scheduler = schedule.Scheduler()
snmp_scheduler.every(15).seconds.do(snmp_jobqueue.put, generateSnmp)
snmp_worker_thread = threading.Thread(daemon=True, target=snmp_main)
snmp_worker_thread.start()

# Main loop
while 1:
    dcim_scheduler.run_pending()
    ping_scheduler.run_pending()
    snmp_scheduler.run_pending()
    time.sleep(1)

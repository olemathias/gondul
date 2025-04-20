import time
import json
import os
import logging

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

def reqProm(endpoint, params):
    basic = HTTPBasicAuth(os.environ.get("PROM_USER"), os.environ.get("PROM_PASSWORD"))
    prom_url = os.environ.get("PROM_URL")

    response =  requests.get(
        f"{prom_url}/api/v1/{endpoint}",
        params=params,
        auth=basic,
    )

    if response.ok is False or response.json()["status"] != "success" or 'json' not in response.headers.get('Content-Type', ''):
         logger.error(f"request '{endpoint}' with {json.dumps(params)} not ok, got: {response.status_code} with content-type: {response.headers.get('Content-Type', '')}")
         return None

    return response.json()

def getPromMetric(query, step="5m", uniq_label=""):
    output = {}
    metric_resp = reqProm("query",
        params={
            "query": query,
            "latency_offset": "5ms",
            "step": step,
        }
    )
    timestamp_resp = reqProm("query",
        params={
            "query": f"timestamp({query})",
            "latency_offset": "5ms",
            "step": step,
        }
    )

    if metric_resp is None or timestamp_resp is None:
        return None

    timestamps = {}
    for m in timestamp_resp["data"]["result"]:
        if uniq_label == "":
            timestamps.update({m['metric']['sysname']: m["value"][1]})
            continue
        if uniq_label not in m['metric']:
            logger.warning(f"{m['metric']} not found in metric")
            continue
        timestamps.update({f"{m['metric'][uniq_label]}{m['metric']['sysname']}": m["value"][1]})

    for m in metric_resp["data"]["result"]:
        label = ""
        if uniq_label != "":
            label = m["metric"][uniq_label]
        if f"{label}{m['metric']['sysname']}" in timestamps:
            time = timestamps[f"{label}{m['metric']['sysname']}"]
        else:
            logger.warning(f"Failed to get time for query {query}")
            time = m["value"][0]
        output.update({f"{label}{m['metric']['sysname']}": {"metric": m["metric"], "value": m["value"][1], "time": time}})

    return output

def getPing():
    data = {}
    metrics = getPromMetric('probe_icmp_duration_seconds{phase="rtt"}', "1m", 'type')
    if metrics is None:
        logger.error(f"Ping metrics failed")
        return None
    for metric in metrics.values():
        if metric["metric"]["sysname"] not in data:
            data[metric["metric"]["sysname"]] = {}
        value = float(metric["value"]) if metric["value"] != "0" else None
        data[metric["metric"]["sysname"]].update({metric["metric"]["type"]: { "latency": value, "time": int(float(metric["time"])) }})

    logger.debug(f"Ping fetched {len(data)} devices")
    return {"updated": round(time.time()), "data": data}

def getSnmp():
    data = {}
    metrics = {
        "sysUpTime": {"value": "value"},
        "sysName": {"value": "meta"},
        "sysDescr": {"value": "meta"},
        "entPhysicalSerialNum": {"value": "meta"},
        "sysContact": {"value": "meta"}
    }

    for key, options in metrics.items():
        prom_met = getPromMetric(key, "5m")
        if "value" not in options:
            options["value"] = "value"

        for sysname, met in prom_met.items():
            if sysname not in data:
                data[sysname] = {"time": float(met["time"])}
            if options["value"] == "value":
                data[sysname].update({key: met["value"]})
            elif options["value"] == "meta":
                data[sysname].update({key: met["metric"][key]})

    return data

def getSnmpPorts():
    data = {}
    metrics = {
        "ifType_info": {
            "key": "ifType",
            "value": "metadata",
            "fields": ["ifAlias", "ifDescr", "ifIndex", "ifName", "ifType"]
        },
        "ifPhysAddress": {"value": "metadata"},
        "ifAdminStatus": {"value": "value", "mapping": {"1": "up", "2": "down"}},
        "ifOperStatus": {"value": "value", "mapping": {"1": "up", "2": "down", "3": "testing", "4": "unknown", "5": "dormant", "6": "notPresent", "7": "lowerLayerDown"}},
        "ifHighSpeed": {"value": "value"},
        "ifLastChange": {"value": "value"},
        "ifHCInOctets": {"value": "value"},
        "ifHCOutOctets": {"value": "value"},
        "ifInDiscards": {"value": "value"},
        "ifOutDiscards": {"value": "value"},
        "ifInErrors": {"value": "value"},
        "ifOutErrors": {"value": "value"},
        "ifInUnknownProtos": {"value": "value"},
        "ifOutQLen": {"value": "value"},
    }

    for key, options in metrics.items():
        prom_met = getPromMetric(key, "15m", "ifName")
        if "key" in options:
            key = options["key"]
        if "value" not in options:
            options["value"] = "value"

        for met in prom_met.values():
            sysname = met["metric"]["sysname"]
            if sysname not in data:
                data[sysname] = {"time": float(met["time"])}
            ifname = met["metric"]["ifName"]
            if ifname not in data[sysname]:
                data[sysname][ifname] = {}
            if options["value"] == "value":
                value = options["mapping"][met["value"]] if "mapping" in options and met["value"] in options["mapping"] else met["value"]
                data[sysname][ifname].update({key: value})
            if options["value"] == "metadata":
                if "fields" not in options:
                    options["fields"] = [key]
                for field in options["fields"]:
                    if field in met["metric"]:
                        data[sysname][ifname].update({field: met["metric"][field]})
                    else:
                        logger.debug(f"Failed to get {field} for {sysname}:{ifname}")

    return data


def getLastTime(query, step):
    timestamp_resp = reqProm("query",
        params={
            "query": f"timestamp({query})",
            "latency_offset": "5ms",
            "step": step,
            "limit": 1
        }
    )
    if timestamp_resp is None:
        return time.time()
    return timestamp_resp["data"]["result"][0]["value"][1]
import pynetbox
import re

nb = pynetbox.api(
    "https://netbox.tg25.tg.no", "cbfb26859fc42da2b61928cba0333ebd462d4fb2", threading=True
)

# role=access-switch&location=floor
devices = nb.dcim.devices.filter(role = "access-switch", location = "floor")

for device in devices:
    reg = re.search("^e([0-9]{1,3})-([0-9])$", device.name)
    if reg is not None:
        row = int(reg[1])
        sw = int(reg[2])
        x = int(572 + ((row-1)/2) * 31.1)
        y = 0
        #if ((row-1/2)>9): x += 140
        if (sw > 2): y = 405 - 120 * (sw-2)
        else: y = 689 - 120 * (sw)
        if (row >= 11): x += 50
        if (row >= 27): x += 50
            
        device["custom_fields"]["gondul_placement"] = {"width": 20, "height": 120, "x": x, "y": y}
        nb.dcim.devices.update([device])
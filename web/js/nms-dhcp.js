"use strict";

var nmsDhcp = nmsDhcp || {};

nmsDhcp.init = function () {
  nmsData.addHandler("dhcpsummary", "nmsDhcpHandler", nmsDhcp.updateSummary);
};

nmsDhcp.updateSummary = function () {
  var e = document.getElementById("dhcp-summary");
  if (e == undefined) {
    return;
  }
  e.innerHTML = "";
  if (nmsData.mactable.arp_count_total != undefined) {
    e.innerHTML = e.innerHTML + nmsData.dhcpsummary.mactable.arp_count_total + " IPv4 clients";
  }
  if (
    nmsData.dhcpsummary.mactable.arp_count_total != undefined &&
    nmsData.dhcpsummary.mactable.ndp_count_total != undefined
  ) {
    e.innerHTML = e.innerHTML + " | ";
  }
  if (nmsData.mactable.ndp_count_total != undefined) {
    e.innerHTML = e.innerHTML + nmsData.dhcpsummary.mactable.ndp_count_total + " IPv6 clients";
  }
};

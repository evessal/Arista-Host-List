# The purpose of this script is to determine the IP addresses of hosts connected to a switch and their corresponding hostnames and write it out to file. 
# The script achieves this task by capturing all locally-resolving MAC addresses and using ARP to determine what their corresponding IP address is. 
# MAC addresses which do not resolve to an IP address are written out to a separate file for further analysis. The script will also point out IP
# addresses which do not resolve in DNS. Certain assumptions are made with this script, including:
# 
# 1) Script is being run against Arista devices (hence use of the Pyeapi library)
# 2) Script is being run against devices in a VRF-Lite environment. 
# 3) The switch is part of an MLAG pair (though script should not need modification for non-MLAG switches)
# 4) Only one device in the MLAG pair is required for entry, single-homed hosts on the partner device should register their MAC addresses across
#    the MLAG peerlink.
# 5) There is the presence of both locally-routed and non-locally routed VLANs. This script was created for use in a VxLAN-bridging environment
#    with the idea that a set of routers handle routing for VLANs being flooded via VxLAN, hence the presence of the router_param variable in this
#    script.
# 
# In order to run this script simply replace the values 'YOUR SWITCH HOSTNAME HERE' and 'YOUR ROUTER HOSTNAME HERE' with relevant names. 
#
# This script has been written by Ehsan Vessal. You may contact me at ehsan.vessal@gmail.com

# Importing necessary modules, however the credentials module is a locally-defined module used for storing devices credentials. 

import pyeapi
import re
import ipaddress
import socket
from credentials import username, password

# These are the parameters required by EAPI to connect to devices. Hostnames are automatically resolved in DNS
# You only need to look into one switch in a MLAG pair to get the host list. You also only need to input one of 
# the routers in a high-availabiliy pair. 

leaf_param = pyeapi.client.connect(
    transport='https',
    host = 'YOUR SWITCH HOSTNAME HERE',
    username = username,
    password = password
)

router_param = pyeapi.client.connect(
    transport='https',
    host = 'YOUR ROUTER HOSTNAME HERE',
    username = username,
    password = password
)

leaf = pyeapi.client.Node(leaf_param)
router = pyeapi.client.Node(router_param)

# These methods allow us to access enable mode in the devices

leaf.enable_authentication(password)
router.enable_authentication(password)

# Command output that is grabbed and analyzed. Data returned in JSON format.  

show_macs = leaf.run_commands('show mac address-table')
interfaces = leaf.run_commands('show ip interface')
leaf_arp = leaf.run_commands('show arp')
show_vlans = leaf.run_commands('show vlan brief')
hostname = leaf.run_commands('show hostname')[0]['hostname']
ip_addrs = []
router_arp_dict = {}

# MAC addresses of all hosts on the leaf pair are filtered and stored. MAC addresses
# which are learned via VXLAN, are static entries, or are router entries for the VARP
# addresses are filtered out. 

macadds = [
            macs 
            for macs 
            in show_macs[0]['unicastTable']['tableEntries'] 
            if re.match(pattern=r'^((?!Vx|Ro).)*$', string=macs['interface']) 
            and re.match(pattern=r'^((?!st).)*$', string=macs['entryType'])
]

# VLAN layer-3 interfaces that are local to the leaf pair are filtered and stored. The regex
# filters out unnecessary VLANs, such as VLAN 1 and MLAG peering VLANs. 

vlan_ints = [
            vlan for 
            vlan in interfaces[0]['interfaces'].keys()
            if re.match(pattern=r'^Vlan\d{1,4}(?<!409(3|4))$', string=vlan) 
            and interfaces[0]['interfaces'][vlan]['lineProtocolStatus'] == 'up'
]

# VLANs configured on the leaf pair are captured and compared to the Layer-3 interfaces that were previously grabbed
# This determined whether they are locally routed VLANs or are learned via VXLAN. 

leaf_vlans = [
        vlan 
        for vlan 
        in show_vlans[0]['vlans'].keys() 
        if re.match(pattern=r'^(?!1$)\d{1,4}(?<!409(3|4))$', string=vlan)
]


local_vlans = [
        vlan 
        for vlan 
        in leaf_vlans 
        if f'Vlan{vlan}' 
        in vlan_ints
]

router_vlans = [
        vlan for 
        vlan in 
        leaf_vlans 
        if f'Vlan{vlan}' 
        not in vlan_ints 
]

# These next two variables create dictionary values that format the MAC address and map it to its VLAN # and 
# the interface it was learned from. These values will be used later for further analysis. 

local_macs = {
                '{}{}.{}{}.{}{}'.format(*mac['macAddress'].split(':')):   
                {
                    'interface': mac['interface'], 'vlanId': mac['vlanId']
            }
            for mac
            in macadds
            if 'Vlan'+ str(mac['vlanId']) 
            in vlan_ints
}
    
routed_macs = {
                '{}{}.{}{}.{}{}'.format(*mac['macAddress'].split(':')):
                {
                    'interface':mac['interface'], 'vlanId': mac['vlanId']
            }
            for mac
            in macadds
            if 'Vlan'+ str(mac['vlanId']) 
            not in vlan_ints
}

# ARP entries are captured from the leaf pair for locally routed VLANs.

arp_elem = leaf_arp[0]['ipV4Neighbors']

arp_dict = {
            entry['address']: entry['hwAddress'] 
            for entry in arp_elem
}

# MAC addresses learned from locally routed VLANs are compared to the ARP entries obtained from the previous
# method. If ARP entry is found for the MAC address, the IP address is appended to a list. If no IP address is
# found the MAC address is written out to a file tracking non-resolving MAC addresses

for mac in local_macs:
    if mac not in arp_dict.values():
        with open(f'{hostname}-noip.txt', 'a') as f:
            f.write(f'MAC Address: {mac} in VLAN: {local_macs[mac]["vlanId"]} on port ' 
            + f'{local_macs[mac]["interface"]} does not resolve to an IP address' + '\n')
    else:
        ipadd = [key for key, value in arp_dict.items() if value == mac]
        ip_addrs += ipadd

# This loop captures ARP entries on the router for non-locally routed VLANs. Notice that this section is assuming a VRF-lite
# routing environment. Edit the command to run for the show_arp variable if necessary for non-VRF-lite environments. 

for vlan in router_vlans:
    show_arp = router.run_commands(f'show arp vrf all interface vlan{vlan}')
    for vrf in show_arp[0]['vrfs']:
        if show_arp[0]['vrfs'][vrf]['dynamicEntries'] > 0:
            for arp_entry in show_arp[0]['vrfs'][vrf]['ipV4Neighbors']:
                router_arp_dict[arp_entry['address']] = arp_entry['hwAddress']

# MAC addresses learned from non-locally routed VLANs are compared to the ARP entries obtained from the previous
# loop. If ARP entry is found for the MAC address, the IP address is appended to a list. If no IP address is
# found the MAC address is written out to a file tracking non-resolving MAC addresses

for mac in routed_macs:
    if mac not in router_arp_dict.values():
        with open(f'{hostname}-noip.txt', 'a') as f:
            f.write(f'MAC Address: {mac} in VLAN: {routed_macs[mac]["vlanId"]} on port ' 
            + f'{routed_macs[mac]["interface"]} does not resolve to an IP address' + '\n')
    else:
         ipadd = [key for key, value in router_arp_dict.items() if value == mac]
         ip_addrs += ipadd

# IP addresses are sorted and written out to a second file that lists the IP address with its corresponding hostname

sorted_ips = sorted(ip_addrs, key=ipaddress.IPv4Address)

with open(f'{hostname}-ip.txt', 'a') as f:
    for ip in sorted_ips:
        try:
            f.write(f'{ip}  {socket.gethostbyaddr(ip)[0]} \n')
        except Exception as e:
            f.write(f'{ip} does not resolve in DNS\n')

# Arista-Host-List
This is a script I created to find IP addresses and hostnames of end-hosts connected to an Arista switch. 

This script was created with the intent of being used in a VXLAN-bridging environment, where in addition to VLANs being locally routed on a leaf pair a router exists which hosts gateways for VLANs that are being stretched to leaf pairs via VXLAN flooding. This script also assumes that leaves are connected in MLAG pairs. As such to run this script it is only necessary to grab information from one switch in the leaf pair. You may wish to modify this script to suite your own specific environmental needs. 

In order to successfully run this script, you will need to create your own credentials.py file to store the username and password variables, or you may choose to place the credentials directly in your script on lines 34-35 and 41-42 when setting the pyeapi call. You will also need to provide the hostname of your switch on lines 33 and 40. The script will create two text files; one which will append a list of IP addresses and their hostnames (if found); another which will input mac-addresses of hosts which did not resolve to an IP address and need further investigation (their default gateways maybe on a firewall or load-balancer, etc.). 

You may contact me at ehsan.vessal@gmail.com. 

#!/bin/bash
# Make wlan1 permanently unmanaged by NetworkManager.
# This uses the newer NM config format (NetworkManager 1.46+).
cat > /etc/NetworkManager/conf.d/unmanage-wlan1.conf << 'EOF'
[device]
wlan1-device=interface-name:wlan1

[connection]
wlan1-connection=interface-name:wlan1
EOF
chmod 644 /etc/NetworkManager/conf.d/unmanage-wlan1.conf
nmcli connection reload
nmcli device set wlan1 managed no
echo "Done - wlan1 is permanently unmanaged"
nmcli device status | grep wlan1

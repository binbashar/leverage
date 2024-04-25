#!/bin/bash
# Configure docker daemon to listen through socket
mkdir /etc/docker
echo '{"tls": false, "hosts": ["unix:///var/run/docker.sock"]}' > /etc/docker/daemon.json
# Start daemon silently                                                                    
dockerd > /dev/null 2>&1 &
exec "$@"                                                                                  

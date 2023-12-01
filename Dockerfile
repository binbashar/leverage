FROM docker:latest

LABEL vendor="Binbash Leverage (leverage@binbash.com.ar)"

RUN apk update &&\
    apk add --no-cache bash bash-completion ncurses git curl gcc musl-dev python3 python3-dev py3-pip

# Install bats from source
RUN git clone https://github.com/bats-core/bats-core.git && ./bats-core/install.sh /usr/local
# Install other bats modules
RUN git clone https://github.com/bats-core/bats-support.git
RUN git clone https://github.com/bats-core/bats-assert.git

# Needed as is mounted later on
RUN mkdir /root/.ssh
# Needed for git to run propertly
RUN touch /root/.gitconfig

WORKDIR /leverage
RUN git config --global --add safe.directory /leverage
# Install requirements for running unit tests
COPY ./dev-requirements.txt .
RUN pip install -r dev-requirements.txt

# Make script to configure and start docker daemon the default entrypoint
RUN echo $'#!/bin/bash                                                                     \n\
# Configure docker daemon to listen through socket                                         \n\
mkdir /etc/docker                                                                          \n\
echo \'{"tls": false, "hosts": ["unix:///var/run/docker.sock"]}\' > /etc/docker/daemon.json\n\
# Start daemon silently                                                                    \n\
dockerd > /dev/null 2>&1 &                                                                 \n\
exec "$@"                                                                                  \n' >> /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT [ "/entrypoint.sh" ]

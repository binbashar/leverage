FROM docker:24.0.7-dind-alpine3.18

LABEL vendor="Binbash Leverage (leverage@binbash.com.ar)"

RUN apk update &&\
    apk add --no-cache bash bash-completion ncurses git curl gcc musl-dev python3 python3-dev py3-pip

ENV POETRY_VIRTUALENVS_CREATE=false
ENV PATH="${PATH}:/opt/home/.poetry/bin"

# Install bats from source
RUN git clone https://github.com/bats-core/bats-core.git && ./bats-core/install.sh /usr/local
# Install other bats modules
RUN git clone https://github.com/bats-core/bats-support.git
RUN git clone https://github.com/bats-core/bats-assert.git

# Needed as is mounted later on
RUN mkdir /opt/home/.ssh
# Needed for git to run propertly
RUN touch /opt/home/.gitconfig

RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/usr/local POETRY_VERSION=1.8.2 python3 -

RUN git config --global --add safe.directory /workdir

# Copying all necessary files to /workdir directory
COPY . /workdir
WORKDIR /workdir

RUN poetry install --with=dev --with=main

COPY entrypoint.sh /
# Make script to configure and start docker daemon the default entrypoint
ENTRYPOINT [ "/entrypoint.sh" ]

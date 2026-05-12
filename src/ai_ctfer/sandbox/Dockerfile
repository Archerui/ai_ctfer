FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        binutils \
        build-essential \
        bzip2 \
        ca-certificates \
        curl \
        file \
        flintqs \
        gdb \
        git \
        gmp-ecm \
        gzip \
        jq \
        libimage-exiftool-perl \
        ltrace \
        make \
        nano \
        ncurses-term \
        netcat-openbsd \
        nmap \
        p7zip-full \
        python3 \
        python3-dev \
        python3-gmpy2 \
        python3-pip \
        python3-sympy \
        python3-venv \
        strace \
        tar \
        unzip \
        wget \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir \
        pwntools \
        pycryptodome \
        requests \
        z3-solver \
    && printf '#!/usr/bin/env bash\npython3 -m pwnlib.commandline.checksec "$@"\n' > /usr/local/bin/checksec \
    && chmod +x /usr/local/bin/checksec

COPY rsa_factordb.py /usr/local/bin/rsa_factordb
RUN chmod +x /usr/local/bin/rsa_factordb

RUN useradd -m -s /bin/bash ctf

USER ctf
WORKDIR /work

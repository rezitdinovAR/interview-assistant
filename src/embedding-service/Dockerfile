FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04


RUN apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false update \
    && apt-get -o Acquire::https::Verify-Peer=false -o Acquire::https::Verify-Host=false -y install \
    wget \
    python3.10 \
    python3-pip \
    python3.10-dev \
    python3.10-venv \
    ffmpeg \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* && update-ca-certificates


RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1


COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt


COPY entrypoint.sh /workspace/
RUN chmod +x /workspace/entrypoint.sh


EXPOSE 8000


WORKDIR /workspace


ENTRYPOINT ["/workspace/entrypoint.sh"]
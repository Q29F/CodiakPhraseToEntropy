FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS python-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates wget xz-utils libssl-dev zlib1g-dev \
       libbz2-dev libffi-dev liblzma-dev libreadline-dev libsqlite3-dev \
       libncursesw5-dev libgdbm-dev uuid-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/python-source
RUN wget -q -O /tmp/python.tar.xz https://www.python.org/ftp/python/3.12.16/Python-3.12.16.tar.xz \
    && echo 'b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c  /tmp/python.tar.xz' | sha256sum -c - \
    && tar -xJf /tmp/python.tar.xz --strip-components=1 \
    && ./configure --enable-shared --with-ensurepip=install LDFLAGS='-Wl,-rpath=/usr/local/lib' \
    && make -j2 \
    && rm -rf /usr/local/lib/python3.12 /usr/local/include/python3.12 \
    && make install \
    && ldconfig

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates libbz2-1.0 libffi8 liblzma5 libreadline8 libsqlite3-0 \
       libssl3 libncursesw6 libtinfo6 libgdbm6 libgdbm-compat4 libuuid1 zlib1g \
    && rm -rf /var/lib/apt/lists/* /usr/local/lib/python3.12 /usr/local/include/python3.12
COPY --from=python-build /usr/local/ /usr/local/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_VERSION=3.12.16 \
    PYTHON_SHA256=b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c

RUN ldconfig \
    && python -c 'import sys, ssl, _hashlib, sqlite3, bz2, lzma, zlib, ctypes, readline, pyexpat; assert sys.version_info[:3] == (3, 12, 16); assert pyexpat.version_info >= (2, 9, 0)'

COPY requirements-installer.txt /tmp/requirements-installer.txt
RUN python -m venv --without-pip /opt/codiak \
    && python -m pip --python /opt/codiak install --require-hashes --only-binary=:all: -r /tmp/requirements-installer.txt \
    && /opt/codiak/bin/python -m pip --python /usr/local/bin/python uninstall --yes pip

ENV PATH="/opt/codiak/bin:${PATH}"

COPY requirements-notebook.txt /tmp/requirements-notebook.txt
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements-notebook.txt \
    && python -m pip check \
    && python -c 'import sys, pip, sympy, jupyterlab; from importlib.metadata import version; assert sys.prefix == "/opt/codiak"; assert pip.__version__ == version("pip") == "26.2.2"' \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home app \
    && mkdir -p /home/app/project \
    && chown 1000:1000 /home/app/project

WORKDIR /home/app/project
COPY --chown=1000:1000 entropy.py simulation.py simulationV2.py CodiakPhraseToEntropySimulationV2.ipynb README.md ./
USER 1000:1000
EXPOSE 8888
CMD ["python", "-m", "jupyterlab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--ServerApp.root_dir=/home/app/project"]

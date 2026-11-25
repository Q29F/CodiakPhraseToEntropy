FROM python:3.12.16-slim-trixie@sha256:a0e2dd78cc679ddfffea960fe45ecfcff9ac2f68d67917a0edfcde5c2100151b

RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libzstd1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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

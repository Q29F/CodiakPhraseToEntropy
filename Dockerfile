FROM sagemath/sage:9.3

COPY . /home/sage
WORKDIR /home/sage

RUN sage -pip install ipywidgets pandas matplotlib

CMD ["sage", "-n", "jupyter", "--ip=0.0.0.0", "--no-browser", "--notebook-dir=/home/sage"]

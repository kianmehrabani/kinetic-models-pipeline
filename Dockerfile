FROM mambaorg/micromamba:git-4427b19-focal

USER root
RUN apt update && apt -y install \
  g++ \
  gcc \
  git \
  make
USER $MAMBA_USER

WORKDIR /rmg
RUN git clone https://github.com/ReactionMechanismGenerator/RMG-Py.git /rmg
ENV PYTHONUNBUFFERED=1
RUN micromamba install --yes --name base --file environment.yml && \
    micromamba clean --all --yes

ARG MAMBA_DOCKERFILE_ACTIVATE=1
RUN make

ENV PYTHONPATH="/rmg/rmgpy:$PYTHONPATH"

WORKDIR /app
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/env.yaml
RUN micromamba install -y -n base -f /tmp/env.yaml && \
    micromamba clean --all --yes
USER root
RUN apt update && apt -y install libxrender1
USER $MAMBA_USER
COPY . .

CMD [ "python", "main.py" ]

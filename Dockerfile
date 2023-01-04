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
RUN make minimal

ARG MAMBA_DOCKERFILE_ACTIVATE=1
ENV PYTHONPATH="/rmg/rmgpy:$PYTHONPATH"

WORKDIR /app
COPY . .

CMD [ "python", "import_kinetic_models.py" ]

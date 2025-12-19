# partially based on the desc-python dockerfile:
# https://github.com/LSSTDESC/desc-python/blob/main/Dockerfile

FROM ubuntu:plucky

# image configuration
ARG LSST_GROUP=lsst
ARG LSST_USER=lsst
ARG RAIL_CONDA=mamba
ARG RAIL_ENV=rail

# git not required, but nice to have
RUN apt update --yes && \
    apt install python3 gcc gfortran g++ make wget git --yes

# change user so we don't do conda init for root
# user and group IDs 1000 are taken in this version of ubuntu (25.04)
# found out with docker run --rm ubuntu:plucky grep 1000 /etc/group
RUN groupadd --system --gid 999 $LSST_GROUP
RUN useradd --no-log-init --create-home --system --uid 999 --gid $LSST_GROUP $LSST_USER
USER $LSST_USER
WORKDIR /home/$LSST_USER

# prepare to run the installation script
ENV SHELL=/bin/bash
COPY install_rail.py install_rail.py
COPY conda-linux-64.lock conda-linux-64.lock
COPY conda-osx-arm64.lock conda-osx-arm64.lock

# run the rail install script
RUN ./install_rail.py \
    --install-conda $RAIL_CONDA \
    --env-name $RAIL_ENV \
    --rail-packages all \
    --install-devtools yes \
    --verbose --clean --local-lockfiles

# cleanup after running
RUN rm install_rail.py
RUN rm conda-linux-64.lock
RUN rm conda-osx-arm64.lock


# Adding python bin directory to the path
ENV PATH="/home/lsst/miniforge3/envs/rail/bin/:${PATH}"

# prepare for interactive use
RUN echo "\n\n$RAIL_CONDA activate base\n$RAIL_CONDA activate $RAIL_ENV" >> ~/.bashrc

# Running Jupyter Notebook Automatically
EXPOSE 8888
CMD ["jupyter", "notebook", "--port=8888"]

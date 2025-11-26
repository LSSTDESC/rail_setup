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

# run the rail install script
# The installation script will always try to pull the lockfiles from github, need to
# change this
# ENV SHELL=/bin/bash
# RUN --mount=type=bind,source=install_rail.py,target=install_rail.py \
#     --mount=type=bind,source=conda-linux-64.lock,target=conda-linux-64.lock.yml \
#     --mount=type=bind,source=conda-osx-arm64.lock,target=conda-osx-arm64.lock.yml \
#     ./install_rail.py --install-conda $RAIL_CONDA --env-name $RAIL_ENV --rail-packages all --install-devtools yes --verbose --clean

# prepare for interactive use
WORKDIR /home/$LSST_USER
RUN echo "\n\n$RAIL_CONDA activate base\n$RAIL_CONDA activate $RAIL_ENV" >> ~/.bashrc
CMD ["/bin/bash"]

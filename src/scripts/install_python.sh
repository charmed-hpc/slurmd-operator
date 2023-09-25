#!/bin/bash

yum -y install epel-release wget gcc make tar zlib-devel openssl-devel libffi-devel sqlite-devel		

export PYTHON_VERSION=3.8.16
wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz -P /tmp
tar xvf /tmp/Python-${PYTHON_VERSION}.tar.xz -C /tmp/
cd /tmp/Python-${PYTHON_VERSION}
./configure --enable-optimizations --prefix=/opt/python/${PYTHON_VERSION}
make altinstall
cd /tmp
rm -rf ./Python*
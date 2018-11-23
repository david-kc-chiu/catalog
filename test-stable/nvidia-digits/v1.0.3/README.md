# DIGITS

[![Build Status](https://travis-ci.org/NVIDIA/DIGITS.svg?branch=master)](https://travis-ci.org/NVIDIA/DIGITS)

DIGITS (the **D**eep Learning **G**PU **T**raining **S**ystem) is a webapp for training deep learning models.
The currently supported frameworks are: Caffe, Torch, and Tensorflow.

# Installation
* To install the chart with the release name `notebook`:

  ```bash
  $ helm install --name digits ./nvidia-digits
  ```

* To install with custom values via file :
  
  ```
  $ helm install  --values values.yaml  --name digits ./nvidia-digits
  ```
  
# Usage

Once you have installed DIGITS, visit [docs/GettingStarted.md](https://github.com/NVIDIA/DIGITS/blob/master/docs/GettingStarted.md) for an introductory walkthrough.

Then, take a look at some of the other documentation at [docs/](https://github.com/NVIDIA/DIGITS/blob/master/docs) and [examples/](https://github.com/NVIDIA/DIGITS/blob/master/examples):

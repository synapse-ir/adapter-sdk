# Installation

## Requirements

- Python 3.11 or higher
- pip or uv

## Install from PyPI


```bash
pip install synapse-adapter-sdk
```



Or with uv:


```bash
uv add synapse-adapter-sdk
```



## Verify the installation


```python
import synapse_sdk
print(synapse_sdk.__version__)
```



## Local development mode

To develop adapters without running a registry:


```bash
export SYNAPSE_LOCAL_MODE=true
export SYNAPSE_LOCAL_MANIFEST_PATH=./manifests.json
```



This lets you develop and test adapters entirely locally with no
external dependencies.

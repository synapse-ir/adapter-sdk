# AdapterValidator

Validates an adapter against all 13 conformance rules.

## Usage


```python
from synapse_sdk import AdapterValidator
from my_module import MyAdapter

validator = AdapterValidator(MyAdapter())
result = validator.run()
print(result.passed)
print(result.errors)

validator.assert_valid()
```



## CLI


```bash
synapse-validate --adapter my_module.MyAdapter
synapse-validate --adapter my_module.MyAdapter --all-fixtures
synapse-validate --adapter my_module.MyAdapter --fixture path/to/fixture.json
```


